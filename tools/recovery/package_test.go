// SPDX-License-Identifier: MIT
package main

import (
	"archive/zip"
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"testing"
)

func fullFixture(t *testing.T) (*zip.Reader, string) {
	t.Helper()
	boot := make([]byte, 4096)
	copy(boot, "ANDROID!")
	binary.LittleEndian.PutUint32(boot[36:40], 2048)
	binary.LittleEndian.PutUint32(boot[40:44], 2)
	binary.LittleEndian.PutUint32(boot[1648:1652], 4)
	copy(boot[2048:], []byte{0xd7, 0xb7, 0xab, 0x1e})
	apfs := func(h []byte) {
		copy(h[32:36], "NXSB")
		binary.LittleEndian.PutUint32(h[36:40], 4096)
		binary.LittleEndian.PutUint64(h[40:48], 1)
	}
	rec := make([]byte, capacities["recovery"])
	copy(rec, boot)
	copy(rec[32<<20:], []byte{0xcf, 0xfa, 0xed, 0xfe})
	apfs(rec[52<<20:])
	footer := rec[len(rec)-64:]
	copy(footer, "AVBf")
	binary.BigEndian.PutUint64(footer[12:20], 4096)
	binary.BigEndian.PutUint64(footer[20:28], 4096)
	binary.BigEndian.PutUint64(footer[28:36], 256)
	system := make([]byte, 4096)
	apfs(system)
	kit := testKit()
	ks := sha256.Sum256(kit)
	c := testConfig()
	c.Files, c.KitBytes, c.KitSHA256 = make(map[string]Image), int64(len(kit)), hex.EncodeToString(ks[:])
	payload := map[string][]byte{"boot.img": boot, "recovery.img": rec, "system.apfs": system, "hfs-kit.bin": kit, "candidate.json": []byte("{}"), "README.txt": []byte("test"), "META-INF/com/google/android/update-binary": []byte("test"), "META-INF/com/google/android/updater-script": []byte("#test")}
	for name, part := range imageParts {
		b := payload[name]
		h := sha256.Sum256(b)
		c.Files[name] = Image{Partition: part, Bytes: int64(len(b)), SHA256: hex.EncodeToString(h[:])}
	}
	raw, _ := json.Marshal(c)
	payload["installer.json"] = raw
	cs := sha256.Sum256(raw)
	var buf bytes.Buffer
	z := zip.NewWriter(&buf)
	for name, data := range payload {
		header := &zip.FileHeader{Name: name, Method: zip.Store}
		header.SetMode(0644)
		w, e := z.CreateHeader(header)
		if e != nil {
			t.Fatal(e)
		}
		if _, e = w.Write(data); e != nil {
			t.Fatal(e)
		}
	}
	if e := z.Close(); e != nil {
		t.Fatal(e)
	}
	r, e := zip.NewReader(bytes.NewReader(buf.Bytes()), int64(buf.Len()))
	if e != nil {
		t.Fatal(e)
	}
	return r, hex.EncodeToString(cs[:])
}
func TestCompleteBundleAndNegativeInventory(t *testing.T) {
	r, key := fullFixture(t)
	if _, e := loadBundle(r, key); e != nil {
		t.Fatal(e)
	}
	if _, e := loadBundle(r, "bad-key"); e == nil {
		t.Fatal("configuration mismatch accepted")
	}
	f := r.File[0]
	name := f.Name
	f.Name = "../../dev/block/efs"
	if _, e := loadBundle(r, key); e == nil {
		t.Fatal("unexpected destination accepted")
	}
	f.Name = name
	saved := r.File
	r.File = append(r.File, r.File[0])
	if _, e := loadBundle(r, key); e == nil {
		t.Fatal("duplicate entry accepted")
	}
	r.File = saved
	old := f.Method
	f.Method = zip.Deflate
	if _, e := loadBundle(r, key); e == nil {
		t.Fatal("unexpected compression accepted")
	}
	f.Method = old
	for _, image := range r.File {
		if image.Name == "boot.img" {
			image.CRC32 ^= 1
			if _, e := loadBundle(r, key); e == nil {
				t.Fatal("corrupt payload CRC accepted")
			}
			image.CRC32 ^= 1
		}
	}
	f.SetMode(0644 | 01000000000)
	if _, e := loadBundle(r, key); e == nil {
		t.Fatal("symlink accepted")
	}
}
func TestImageValidationRejectsIncompatibleHeader(t *testing.T) {
	r, key := fullFixture(t)
	b, e := loadBundle(r, key)
	if e != nil {
		t.Fatal(e)
	}
	// The full verifier checks payload SHA/CRC. Also check the independent structural parser.
	b.Files["boot.img"].UncompressedSize64 = 2048
	if e = checkImages(b); e == nil {
		t.Fatal("truncated boot accepted")
	}
}

func TestCapacityFitsLargerUserdataOnly(t *testing.T) {
	const ud = 116253523968
	for _, tc := range []struct {
		name     string
		actual   uint64
		measured int64
		ok       bool
	}{
		{"userdata", ud, ud, true},
		{"userdata", 496000000000, ud, true}, // 512 GB model
		{"userdata", ud - 4096, ud, false},
		{"super", 9437184000, 9437184000, true},
		{"super", 9437184000 + 4096, 9437184000, false},
		{"boot", 61865984 - 4096, 61865984, false},
	} {
		if capacityFits(tc.name, tc.actual, tc.measured) != tc.ok {
			t.Errorf("%+v", tc)
		}
	}
}
