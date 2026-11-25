// SPDX-License-Identifier: MIT
package main

// Approval from the computer (A, 2026-11-20). tools/install/twrp-install.sh asks the person on the computer first
// ("yes" for an update that keeps the data, "ERASE" for anything that erases it), then leaves one line in TWRP's
// RAM: "<sha256 of this package's installer.json> keep|erase". With it the installer needs no key press; without
// it (TWRP's own Install button) the physical Volume Up press stays. The approval names this exact package, covers
// no more than what was typed, and is removed when the installer ends (TWRP's /tmp is gone at reboot anyway).

import (
	"errors"
	"os"
	"strings"
)

var approvalFile = "/tmp/jesvi.approve" // a var only for the tests

// approval reports the computer's approval for this package: "keep", "erase" or "" (none, or another package's).
func approval() string {
	raw, e := os.ReadFile(approvalFile)
	if e != nil {
		return ""
	}
	f := strings.Fields(string(raw))
	if len(f) != 2 || configSHA == "" || f[0] != configSHA || (f[1] != "keep" && f[1] != "erase") {
		return ""
	}
	return f[1]
}

func dropApproval() { os.Remove(approvalFile) }

// confirm: the computer's approval when it covers this step (erase covers keep), else the physical keys.
func confirm(prompt string, erases bool, log func(string), auto ...bool) error {
	switch a := approval(); {
	case a == "erase" || a == "keep" && !erases:
		log(prompt)
		log("Approved on the computer.")
		return nil
	case a == "keep":
		return errors.New("this would ERASE the phone's data, but the computer approved only an update that keeps it: run twrp-install.sh with --erase if that is what you want")
	}
	return confirmKeys(prompt, log, len(auto) > 0 && auto[0])
}
