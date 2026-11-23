// SPDX-License-Identifier: MIT
package main

import (
	"bytes"
	"os"
	"testing"
)

// JESVI_SUPER_HEAD points at a real 1 MiB super head dump (private, not committed).
func TestRealSamsungSuperHeadRoundTripsByteForByte(t *testing.T) {
	path := os.Getenv("JESVI_SUPER_HEAD")
	if path == "" {
		t.Skip("set JESVI_SUPER_HEAD to a real super head dump")
	}
	raw, e := os.ReadFile(path)
	if e != nil || len(raw) < lpRegion {
		t.Fatal("super head unreadable", e)
	}
	m, e := parseLP(raw[:lpRegion])
	if e != nil {
		t.Fatal(e)
	}
	out, e := m.encode()
	if e != nil {
		t.Fatal(e)
	}
	// Reserved area, both geometries and slot 0 (primary and backup) must be
	// identical. Samsung leaves an older copy in slot 1; liblp reads slot 0.
	slot := int(m.MaxSize)
	start := lpReserved + 2*lpGeometrySize
	backup := start + int(m.Slots)*slot
	for _, r := range [][2]int{{0, start + slot}, {backup, backup + slot}} {
		if !bytes.Equal(out[r[0]:r[1]], raw[r[0]:r[1]]) {
			t.Fatalf("encoder differs from liblp bytes in [%d,%d)", r[0], r[1])
		}
	}
	if !bytes.Equal(raw[len(out):lpRegion], make([]byte, lpRegion-len(out))) {
		t.Fatal("unexpected bytes after metadata in real head")
	}
	empty, e := m.emptied().encode()
	if e != nil {
		t.Fatal(e)
	}
	if back, e := parseLP(empty); e != nil || len(back.Partitions) != 0 || !bytes.Equal(back.Reserved, raw[:lpReserved]) {
		t.Fatal("emptied real layout does not parse", e)
	}
	t.Logf("partitions=%d groups=%v", len(m.Partitions), m.Groups)
}

func s20Android() AndroidSuper {
	return AndroidSuper{MetadataMaxSize: 65536, MetadataSlots: 2, LogicalBlockSize: 4096, Alignment: 524288, FirstLogicalSector: 2048,
		Groups: []AndroidGroup{{"group_basic", 9432989696}}}
}

func TestGeneratedEmptyMetadataParsesAndStashRoundTrips(t *testing.T) {
	m := s20Android().metadata(9437184000)
	out, e := m.encode()
	if e != nil || len(out) != lpRegion {
		t.Fatal(e, len(out))
	}
	back, e := parseLP(out)
	if e != nil || len(back.Partitions) != 0 || len(back.Groups) != 2 || back.Groups[1].Name != "group_basic" || back.Devices[0].Size != 9437184000 {
		t.Fatal("generated metadata did not parse back", e)
	}
	full := append(append([]byte{}, out...), make([]byte, lpRegion-len(out))...)
	st := encodeStash(full, 9437184000)
	got, e := decodeStash(st, 9437184000)
	if e != nil || got.Groups[1].Max != 9432989696 {
		t.Fatal(e)
	}
	if _, e = decodeStash(st, 9437184001); e == nil {
		t.Fatal("stash accepted for another super size")
	}
	st[5000] ^= 1
	if _, e = decodeStash(st, 9437184000); e == nil {
		t.Fatal("corrupt stash accepted")
	}
	bad := append([]byte{}, out...)
	bad[lpReserved+2*lpGeometrySize+200] ^= 1
	if _, e = parseLP(bad); e == nil {
		t.Fatal("corrupt tables accepted")
	}
	if _, e = parseLP(make([]byte, lpRegion)); e == nil {
		t.Fatal("zeros accepted as LP")
	}
}

// testConfig is the measured x1slte profile as the builder binds it.
func testConfig() Config {
	parts := map[string]int64{"boot": 61865984, "recovery": 69009408, "super": 9437184000, "userdata": 116253523968}
	return Config{Schema: 2, Action: "install", Device: "x1slte", Mode: "choose", Models: []string{"SM-G980F"}, Bootloaders: []string{"G980FXXSNHYB7"},
		Products: []string{"x1s", "x1slte"}, Partitions: parts, SystemMaxBytes: 4 << 30, StashOffset: 9437184000 - 2<<20, AndroidSuper: s20Android()}
}

func TestProfileFromRealHeadMatchesGeneratedFallback(t *testing.T) {
	path := os.Getenv("JESVI_SUPER_HEAD")
	if path == "" {
		t.Skip("set JESVI_SUPER_HEAD")
	}
	raw, _ := os.ReadFile(path)
	m, e := parseLP(raw[:lpRegion])
	if e != nil {
		t.Fatal(e)
	}
	real, _ := m.emptied().encode()
	gen, e := s20Android().metadata(9437184000).encode()
	if e != nil || !bytes.Equal(real[lpReserved:], gen[lpReserved:]) {
		t.Fatal("profile fallback differs from the phone's own empty layout", e)
	}
}

func TestConfigRejectsUnsafeProfiles(t *testing.T) {
	ok := testConfig()
	ok.Files = map[string]Image{"a": {}, "b": {}, "c": {}}
	ok.KitBytes = 1
	if e := checkConfig(ok); e != nil {
		t.Fatal(e)
	}
	for i, mutate := range []func(*Config){
		func(c *Config) { c.Device = "../x" },
		func(c *Config) { c.Schema = 1 },
		func(c *Config) { c.InstallerValidated = true },
		func(c *Config) { c.Action = "flash" },
		func(c *Config) { c.Partitions["efs"] = 1 << 24 },
		func(c *Config) { delete(c.Partitions, "boot"); c.Partitions["dtbo"] = 1 << 24 },
		func(c *Config) { c.StashOffset = 1 << 20 },
		func(c *Config) { c.StashOffset = c.Partitions["super"] - 4096 },
		func(c *Config) { c.SystemMaxBytes = 5 << 30 },
		func(c *Config) { c.Products = nil },
		func(c *Config) { c.AndroidSuper.Groups = nil },
		func(c *Config) { c.Action, c.Mode = "restore", "restore" },
	} {
		c := testConfig()
		c.Files = map[string]Image{"a": {}, "b": {}, "c": {}}
		c.KitBytes = 1
		mutate(&c)
		if checkConfig(c) == nil {
			t.Fatal("unsafe profile accepted", i)
		}
	}
	r := testConfig()
	r.Action, r.Mode = "restore", "restore"
	if e := checkConfig(r); e != nil {
		t.Fatal(e)
	}
}

func TestY2SInstallIsFreshOnlyAndUsesMeasuredSystemWindow(t *testing.T) {
	c := testConfig()
	c.Device, c.Mode = "y2s", "fresh"
	c.Models = []string{"SM-G986B"}
	c.Bootloaders = []string{"G986BXXSNHYB1"}
	c.Products = []string{"y2s"}
	c.SystemMaxBytes = y2sSystemMax
	c.Files = map[string]Image{"a": {}, "b": {}, "c": {}}
	c.KitBytes = 1
	if e := checkConfig(c); e != nil {
		t.Fatal(e)
	}
	c.Mode = "update"
	if checkConfig(c) == nil {
		t.Fatal("y2s update mode accepted; updates must go through the loader")
	}
	c.Mode, c.SystemMaxBytes = "fresh", y2sSystemMax+4096
	if checkConfig(c) == nil {
		t.Fatal("system window beyond measured y2s geometry accepted")
	}
}
