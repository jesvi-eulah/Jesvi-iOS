// SPDX-License-Identifier: MIT
package main

import (
	"archive/zip"
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

func uiText(s string) string {
	return strings.Map(func(r rune) rune {
		if r < 32 || r == 127 {
			return ' '
		}
		return r
	}, s)
}

var batteryTenthsC int // the battery temperature the device check read (platform_linux.go)
var configSHA string   // Bound by builder to exact metadata; no arbitrary destinations.
func selectInstallMode(requested string, valid, recognizable bool) (string, error) {
	switch requested {
	case "fresh":
		return "fresh", nil
	case "update":
		if !valid {
			return "", errors.New("this is an update-only package, but matching iOS userdata was not found; for a first install rebuild with --set MODE=fresh (erases userdata after confirmation), or MODE=choose for automatic detection; back up existing data first")
		}
		return "update", nil
	case "choose":
		if valid {
			return "update", nil
		}
		if recognizable {
			return "", errors.New("the iOS data here is damaged or a different size than this package (IOS_DATA_GB); refusing to erase it automatically: back it up, then rebuild with --set MODE=fresh")
		}
		return "fresh", nil
	default:
		return "", errors.New("unsupported install mode")
	}
}

func run() error {
	args := os.Args
	if len(args) == 3 && args[1] == "--inspect" {
		z, e := zip.OpenReader(args[2])
		if e != nil {
			return e
		}
		defer z.Close()
		b, e := loadBundle(&z.Reader, configSHA)
		if e != nil {
			return e
		}
		fmt.Printf("Verified TWRP payload: action=%s device=%s mode=%s writes=%v hardware-qualified=false\n", b.Config.Action, b.Config.Device, b.Config.Mode, b.Config.AllowWrites)
		return nil
	}
	if len(args) != 4 || (args[1] != "3" && args[1] != "2") {
		return errors.New("expected recovery updater API, output FD and ZIP path; or --inspect ZIP")
	}
	fd, e := strconv.Atoi(args[2])
	if e != nil || fd < 3 {
		return errors.New("invalid recovery output FD")
	}
	pipe := os.NewFile(uintptr(fd), "recovery-output")
	if pipe == nil {
		return errors.New("recovery output unavailable")
	}
	logFile, e := os.OpenFile("/tmp/jesvi-install.log", os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if e != nil {
		return e
	}
	defer logFile.Close()
	ui.pipe = pipe
	log := func(s string) {
		fmt.Fprintln(logFile, s)
		fmt.Fprintln(os.Stderr, s)
		if _, e := fmt.Fprintf(pipe, "ui_print   %s\nui_print\n", uiText(s)); e != nil {
			panic("recovery UI pipe failed; stopping installation")
		}
	}
	archive, e := os.Open(args[3])
	if e != nil {
		return e
	}
	defer archive.Close()
	stat, e := archive.Stat()
	if e != nil {
		return e
	}
	z, e := zip.NewReader(archive, stat.Size())
	if e != nil {
		return e
	}
	ui.steps = 9
	ui.begin("Checking the package")
	log("Verifying every file in the ZIP before anything is written...")
	b, e := loadBundle(z, configSHA)
	if e != nil {
		return e
	}
	headerName, headerModel := "Galaxy S20", "SM-G980F"
	if b.Config.Device == "y2s" {
		headerName, headerModel = "Galaxy S20+", "SM-G986B"
	} else if b.Config.Device == "z3s" {
		headerName, headerModel = "Galaxy S20 Ultra", "SM-G988B"
	} else if len(b.Config.Models) > 0 {
		headerModel = b.Config.Models[0]
	}
	ui.header("iOS 16.5 for the "+headerName, releaseVersion(), headerModel)
	if b.Config.Action == "restore" {
		ui.steps = 6
		log("Jesvi-iOS-Restore: back to Android.")
	} else {
		log("Package OK. Uses the existing partitions; the partition table is not changed.")
	}
	ui.begin("Checking the phone")
	d, e := openRecovery(b.Config, archive, log)
	if e != nil {
		return e
	}
	defer d.Close()
	if d.sibling {
		log("NOTE: this package was measured on " + strings.Join(b.Config.Models, "/") + "; your phone is the same board with the other modem.")
		log("Every partition size matched exactly. Untested model: if iOS does not start, flash Jesvi-iOS-Restore.")
	}
	log("Exact device, bootloader, partition sizes and battery checks passed.")
	if batteryTenthsC > 450 {
		log(fmt.Sprintf("Battery warm (%d.%d C): continuing in 5 s; Volume Down or Power cancels.", batteryTenthsC/10, batteryTenthsC%10))
		if e = warmPause(5 * time.Second); e != nil {
			return e
		}
	}
	if b.Config.Action == "restore" {
		head, e := d.readHead("super", lpRegion)
		if e != nil {
			return e
		}
		if _, e = restoreState(head); e != nil {
			return e
		}
	}
	held, e := d.plan()
	if e != nil {
		return e
	}
	if !held.empty() {
		log("Android ROM storage is in use; after confirmation the installer will:")
		for _, s := range held.describe() {
			log("  " + s)
		}
	}
	if !b.Config.AllowWrites {
		log("PREFLIGHT ONLY: no partitions opened for writing. No reboot.")
		return nil
	}
	if b.Config.Action == "restore" {
		ui.begin("Waiting for your confirmation")
	} else {
		ui.begin("Reviewing installation before the cancel window")
	}
	if b.Config.Action == "restore" {
		log("RESTORE: puts back Android's partition map and clears iOS data headers.")
		log("ALL iOS DATA WILL BE LOST. BOOT and TWRP stay as they are.")
		if e = confirmKeys("Erase iOS and prepare the phone for an Android ROM?", log, false); e != nil {
			return e
		}
		ui.begin("Freeing the storage")
		if e = d.release(log); e != nil {
			return e
		}
		ui.begin("Putting Android's partition map back")
		if e = restoreAndroid(b, d, log); e != nil {
			return e
		}
		ui.finish("Ready for Android", "", "Without rebooting: Wipe > Format Data,", "then flash your Android ROM ZIP.")
		return nil
	}
	valid, recognizable, e := d.dataState()
	if e != nil {
		return e
	}
	mode, e := selectInstallMode(b.Config.Mode, valid, recognizable)
	if e != nil {
		return e
	}
	log(fmt.Sprintf("Install mode: package=%s selected=%s", b.Config.Mode, mode))
	if mode == "update" {
		if e = d.CheckData(); e != nil {
			return e
		}
		log("UPDATE: your iOS data, apps and settings are kept.")
		log("TWRP is replaced by Jesvi iOS.")
		e = confirm("Install the update?", false, log, true)
	} else {
		log("FRESH INSTALL: this ERASES ALL DATA on the phone")
		log("(Android or iOS) and replaces TWRP.")
		log("Keep a backup off the phone if you need anything.")
		e = confirm("Erase the phone and install Jesvi iOS?", true, log, true) // one confirmation (2026-11-20)
	}
	if e != nil {
		return e
	}
	ui.begin("Freeing the storage")
	if e = d.release(log); e != nil {
		return e
	}
	if e = d.CheckSafe(); e != nil {
		return e
	}
	if e = perform(b, d, mode, log); e != nil {
		return e
	}
	log("Every written byte was read back and checked. Log: /tmp/jesvi-install.log")
	ui.finish("Jesvi iOS is installed", "", "Reboot > System", "First boot shows the Apple logo,", "then iOS setup.", "",
		"TWRP may now show 'Failed to mount'", "errors: expected, iOS replaced", "Android's partitions. Ignore them.")
	return nil
}
func reportFailure(message string) {
	fmt.Fprintln(os.Stderr, "INSTALL STOPPED:", message)
	if len(os.Args) == 4 && (os.Args[1] == "2" || os.Args[1] == "3") {
		if f, e := os.OpenFile("/tmp/jesvi-install.log", os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600); e == nil {
			fmt.Fprintln(f, "INSTALL STOPPED:", message)
			f.Close()
		}
		if fd, e := strconv.Atoi(os.Args[2]); e == nil && fd >= 3 {
			if p := os.NewFile(uintptr(fd), "recovery-output"); p != nil {
				fmt.Fprintf(p, "ui_print\nui_print %s\nui_print   INSTALL STOPPED\nui_print   %s\nui_print   Log: /tmp/jesvi-install.log\nui_print %s\nui_print\n", rule(), uiText(message), rule())
			}
		}
	}
}
func main() {
	defer func() {
		if r := recover(); r != nil {
			dropApproval()
			reportFailure(fmt.Sprint(r))
			os.Exit(1)
		}
	}()
	e := run()
	dropApproval() // one run only (approve.go)
	if e != nil {
		reportFailure(e.Error())
		os.Exit(1)
	}
}
