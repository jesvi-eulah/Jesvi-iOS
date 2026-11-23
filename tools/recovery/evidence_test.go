// SPDX-License-Identifier: MIT
package main

import (
	"testing"
)

func TestDeviceEvidenceRejectsWrongOrMissingIdentity(t *testing.T) {
	c := Config{Models: []string{"SM-G980F"}, Bootloaders: []string{"G980FXXSNHYB7"}, Products: []string{"x1s", "x1slte"}}
	base := []string{"SM-G980F", "G980FXXSNHYB7", "x1s", "exynos990", "0", "unlocked"}
	check := func(v []string) error { return verifyIdentity(c, v[0], v[1], v[2], v[3], v[4], v[5]) }
	if e := check(base); e != nil {
		t.Fatal(e)
	}
	for i := range base {
		v := append([]string(nil), base...)
		v[i] = "wrong"
		if e := check(v); e == nil {
			t.Fatal("bad identity evidence accepted", i)
		}
	}
	v := append([]string(nil), base...)
	v[4] = ""
	v[5] = ""
	if e := check(v); e == nil {
		t.Fatal("missing unlock evidence accepted")
	}
	v[4] = "1"
	v[5] = "unlocked"
	if e := check(v); e == nil {
		t.Fatal("conflicting unlock evidence accepted")
	}
}
func TestMountEvidenceIsParsedAndMissingEvidenceFails(t *testing.T) {
	mounted, e := mountedDevices("27 1 8:21 / /data rw,nosuid - ext4 /dev/block/sda21 rw\n28 1 253:0 / /system_root ro - ext4 /dev/block/dm-0 ro\n")
	if e != nil || !mounted["8:21"] || !mounted["253:0"] || mounted["8:1"] {
		t.Fatal(mounted, e)
	}
	for _, bad := range []string{"", "truncated", "27 1 bad / /data rw - ext4 /dev/block/sda21 rw", "27 1 8:999999999999999 / /data rw - ext4 /dev/block/sda21 rw"} {
		if _, e := mountedDevices(bad); e == nil {
			t.Fatal("missing/malformed mount evidence accepted")
		}
	}
}

func TestUntrustedErrorTextCannotInjectRecoveryCommands(t *testing.T) {
	if got := uiText("bad.zip\nwipe_cache\rreboot\x00"); got != "bad.zip wipe_cache reboot " {
		t.Fatal(got)
	}
}

func TestSamsungBootloaderPropertiesTakePrecedenceOverGenericRecoveryTemplate(t *testing.T) {
	c := Config{Models: []string{"SM-G980F"}, Bootloaders: []string{"G980FXXSNHYB7"}, Products: []string{"x1s", "x1slte"}}
	values := map[string]string{"ro.boot.em.model": "SM-G980F", "ro.product.model": "SM-G981B", "ro.bootloader": "G980FXXSNHYB7", "ro.product.device": "x1s", "ro.board.platform": "exynos990", "ro.boot.flash.locked": "0", "ro.boot.vbmeta.device_state": "unlocked"}
	get := func(key string) string { return values[key] }
	if e := verifyRecoveryIdentity(c, get); e != nil {
		t.Fatal(e)
	}
	values["ro.boot.em.model"] = "SM-G981B"
	values["ro.product.model"] = "SM-G980F"
	if e := verifyRecoveryIdentity(c, get); e == nil {
		t.Fatal("wrong hardware model accepted despite product template")
	}
	delete(values, "ro.boot.em.model")
	values["ro.boot.bootloader"] = "different"
	if e := verifyRecoveryIdentity(c, get); e == nil {
		t.Fatal("conflicting bootloaders accepted")
	}
	delete(values, "ro.bootloader")
	values["ro.boot.bootloader"] = "G980FXXSNHYB7"
	if e := verifyRecoveryIdentity(c, get); e != nil {
		t.Fatal("qualified fallback rejected", e)
	}
}

func TestUnifiedExynos990TWRPProductAcceptedOnlyWithExactIdentity(t *testing.T) {
	c := Config{Models: []string{"SM-G980F"}, Bootloaders: []string{"G980FXXSNHYB7"}, Products: []string{"x1s", "x1slte"}}
	if e := verifyIdentity(c, "SM-G980F", "G980FXXSNHYB7", "z3s", "exynos990", "0", "unlocked"); e != nil {
		t.Fatal("unified TWRP on the exact S20 refused:", e)
	}
	if e := verifyIdentity(c, "SM-G988B", "G980FXXSNHYB7", "z3s", "exynos990", "0", "unlocked"); e == nil {
		t.Fatal("unified TWRP on another model accepted")
	}
	if e := verifyIdentity(c, "SM-G980F", "G980FXXSNHYB7", "a52q", "exynos990", "0", "unlocked"); e == nil {
		t.Fatal("non-Exynos-990 product accepted")
	}
}

func TestRegionalFirmwareIdentity(t *testing.T) {
	c := Config{Models: []string{"SM-G986B"}, Bootloaders: []string{"G986BXXSNHYB1"}, Products: []string{"y2s"}}
	for _, tc := range []struct {
		model, firmware, soc string
		accepted             bool
	}{
		{"SM-G986B/DS", "G986BXXU1ABCD", "exynos990", true},
		{"SM-G986N", "G986NKSU1ABCD", "exynos9830", true},
		{"SM-G986N", "G986BXXU1ABCD", "exynos990", false},
		{"SM-G985F", "G985FXXU1ABCD", "exynos990", false},
		{"SM-G986U", "G986USQU1ABCD", "kona", false},
	} {
		err := verifyIdentity(c, tc.model, tc.firmware, "y2s", tc.soc, "0", "unlocked")
		if (err == nil) != tc.accepted {
			t.Errorf("%v: %v", tc, err)
		}
	}
}
