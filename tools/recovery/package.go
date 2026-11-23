// SPDX-License-Identifier: MIT
package main

import (
	"archive/zip"
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"hash/crc32"
	"io"
	"regexp"
	"strings"
)

type Image struct {
	Partition string `json:"partition"`
	Offset    int64  `json:"offset"`
	Bytes     int64  `json:"bytes"`
	SHA256    string `json:"sha256"`
}
type Config struct {
	Schema             int              `json:"schema"`
	Action             string           `json:"action"` // install | restore
	Device             string           `json:"device"`
	Mode               string           `json:"mode"`
	AllowWrites        bool             `json:"allow_writes"`
	InstallerValidated bool             `json:"installer_validated"`
	Models             []string         `json:"models"`
	Bootloaders        []string         `json:"bootloaders"`
	Products           []string         `json:"products"`
	Partitions         map[string]int64 `json:"partitions"`
	SystemMaxBytes     int64            `json:"system_max_bytes"`
	StashOffset        int64            `json:"stash_offset"`
	AndroidSuper       AndroidSuper     `json:"android_super"`
	Files              map[string]Image `json:"files"`
	KitSHA256          string           `json:"kit_sha256"`
	KitBytes           int64            `json:"kit_bytes"`
	DataBytes          int64            `json:"data_bytes"` // iOS's data volume (IOS_DATA_GB); 0: all of userdata
	Splash             SplashFile       `json:"splash"`     // the power-on splash (splash.go); zero: none
}
type SplashFile struct {
	Bytes  int64  `json:"bytes"`
	SHA256 string `json:"sha256"`
}
type Bundle struct {
	Config Config
	Files  map[string]*zip.File
	Kit    []byte
	Staged map[string][]byte
	Splash []byte
}

var imageParts = map[string]string{"boot.img": "boot", "recovery.img": "recovery", "system.apfs": "super"}

// Measured x1slte geometry; replaced by the device profile bound into each ZIP.
var capacities = map[string]int64{"boot": 61865984, "recovery": 69009408, "super": 9437184000, "userdata": 116253523968}
var systemMax int64 = 4 << 30

// y2s uses the measured stock system window; x1slte keeps its 4 GiB cap.
const y2sSystemMax int64 = 0x174200000

var deviceName = regexp.MustCompile(`^[a-z0-9]{2,16}$`)

// checkConfig accepts only the fixed four destinations, sizes from the bound
// device profile, and a stash window inside super's free tail.
func checkConfig(c Config) error {
	if c.Schema != 2 || !deviceName.MatchString(c.Device) || c.InstallerValidated {
		return errors.New("unsupported installer configuration")
	}
	switch c.Action {
	case "install":
		if c.Mode != "choose" && c.Mode != "fresh" && c.Mode != "update" {
			return errors.New("unsupported install mode")
		}
		// y2s's TWRP ZIP is first-install only. Updates are flashed from the
		// loader's Log access menu; accepting a y2s "update" here would let a
		// stale TWRP ZIP overwrite a booted iOS installation.
		if c.Device == "y2s" && c.Mode != "fresh" {
			return errors.New("y2s supports first install only; use the loader for updates")
		}
		if len(c.Files) != 3 || c.KitBytes <= 0 {
			return errors.New("install package needs system, recovery, boot and HFS kit")
		}
	case "restore":
		if c.Mode != "restore" || len(c.Files) != 0 || c.KitBytes != 0 || c.KitSHA256 != "" {
			return errors.New("restore package must not carry images")
		}
	default:
		return errors.New("unknown package action")
	}
	// the four fixed destinations, and optionally up_param (Samsung's splash pictures: splash.go)
	up, hasUp := c.Partitions["up_param"]
	if len(c.Models) == 0 || len(c.Bootloaders) == 0 || len(c.Products) == 0 || len(c.Partitions) != 4 && !(hasUp && len(c.Partitions) == 5) {
		return errors.New("unsupported device profile")
	}
	if hasUp && (up < 1<<20 || up > 64<<20 || up%4096 != 0) {
		return errors.New("unsupported up_param geometry")
	}
	if s := c.Splash; s.Bytes != 0 || s.SHA256 != "" {
		hash, e := hex.DecodeString(s.SHA256)
		if c.Action != "install" || !hasUp || s.Bytes <= 0 || s.Bytes > splashMax || e != nil || len(hash) != 32 {
			return errors.New("invalid splash: install packages for profiles with up_param only, at most 1 MiB")
		}
	}
	for _, p := range []string{"boot", "recovery", "super", "userdata"} {
		if n := c.Partitions[p]; n < 16<<20 || n%4096 != 0 {
			return errors.New("unsupported partition geometry")
		}
	}
	sup := c.Partitions["super"]
	if c.DataBytes != 0 && (c.DataBytes%4096 != 0 || c.DataBytes < 16e9 || c.DataBytes > c.Partitions["userdata"]) {
		return errors.New("iOS data size must be 4096-aligned, at least 16 GB and inside userdata")
	}
	maxSystem := int64(4 << 30)
	if c.Device == "y2s" {
		maxSystem = y2sSystemMax
	}
	if c.SystemMaxBytes < 64<<20 || c.SystemMaxBytes > maxSystem || c.SystemMaxBytes > sup {
		return errors.New("invalid system window")
	}
	if c.StashOffset < c.SystemMaxBytes || c.StashOffset%4096 != 0 || c.StashOffset+4096+lpRegion > sup {
		return errors.New("Android map stash must sit in super's free tail")
	}
	a := c.AndroidSuper
	if len(a.Groups) == 0 {
		return errors.New("Android super layout missing")
	}
	if _, e := a.metadata(sup).encode(); e != nil {
		return fmt.Errorf("Android super layout: %w", e)
	}
	return nil
}
func applyConfig(c Config) {
	capacities = make(map[string]int64, 4)
	for k, v := range c.Partitions {
		capacities[k] = v
	}
	systemMax = c.SystemMaxBytes
	dataBytes = capacities["userdata"]
	if c.DataBytes > 0 {
		dataBytes = c.DataBytes
	}
}

// dataBytes: the size of iOS's HFSX data volume at the start of userdata. Smaller than the partition when
// release.conf IOS_DATA_GB leaves the rest free (the kernel gets ufs_win=0:BLOCKS); the rest is never written.
var dataBytes = capacities["userdata"]

func sameSHA(got []byte, expected string) bool { return hex.EncodeToString(got) == expected }
func readSmall(f *zip.File, max int64) ([]byte, error) {
	if f == nil || f.UncompressedSize64 > uint64(max) {
		return nil, errors.New("missing/oversized package metadata")
	}
	r, e := f.Open()
	if e != nil {
		return nil, e
	}
	defer r.Close()
	data, e := io.ReadAll(io.LimitReader(r, max+1))
	if len(data) > int(max) {
		return nil, errors.New("metadata exceeds limit")
	}
	return data, e
}
func loadBundle(z *zip.Reader, configDigest string) (*Bundle, error) {
	files := make(map[string]*zip.File)
	meta := map[string]bool{"installer.json": true, "README.txt": true, "META-INF/com/google/android/update-binary": true, "META-INF/com/google/android/updater-script": true}
	payload := map[string]bool{"hfs-kit.bin": true, "candidate.json": true, "splash.jpg": true}
	for name := range imageParts {
		payload[name] = true
	}
	for _, f := range z.File {
		limit := uint64(64 << 10)
		if _, ok := imageParts[f.Name]; ok {
			limit = 4 << 30
		}
		if f.Name == "hfs-kit.bin" {
			limit = 16 << 20
		}
		if f.Name == "META-INF/com/google/android/update-binary" {
			limit = 32 << 20
		}
		if f.UncompressedSize64 > limit || f.Flags&1 != 0 {
			return nil, errors.New("oversized/encrypted ZIP entry")
		}
		if !(meta[f.Name] || payload[f.Name]) || files[f.Name] != nil || !f.Mode().IsRegular() || f.Method != zip.Store {
			return nil, fmt.Errorf("unexpected, duplicate or compressed ZIP entry: %s", f.Name)
		}
		files[f.Name] = f
	}
	data, e := readSmall(files["installer.json"], 64<<10)
	if e != nil {
		return nil, e
	}
	sum := sha256.Sum256(data)
	if !sameSHA(sum[:], configDigest) {
		return nil, errors.New("installer configuration does not match executable")
	}
	var c Config
	d := json.NewDecoder(bytes.NewReader(data))
	d.DisallowUnknownFields()
	if e = d.Decode(&c); e != nil {
		return nil, e
	}
	if e = d.Decode(new(any)); e != io.EOF {
		return nil, errors.New("trailing configuration data")
	}
	if e = checkConfig(c); e != nil {
		return nil, e
	}
	want := len(meta)
	if c.Action == "install" {
		want += len(payload)
		if c.Splash.Bytes == 0 {
			want-- // (splash.jpg only with a splash in the configuration)
		}
	}
	for name := range meta {
		if files[name] == nil {
			return nil, errors.New("incomplete installer ZIP")
		}
	}
	if len(files) != want {
		return nil, errors.New("installer ZIP inventory does not match its action")
	}
	applyConfig(c)
	if c.Action == "restore" {
		return &Bundle{Config: c, Files: files}, nil
	}
	staged := make(map[string][]byte)
	for name, p := range imageParts {
		meta, ok := c.Files[name]
		f := files[name]
		limit := capacities[p]
		if p == "super" {
			limit = systemMax
		}
		hash, e := hex.DecodeString(meta.SHA256)
		if !ok || meta.Partition != p || meta.Offset != 0 || meta.Bytes <= 0 || meta.Bytes > limit || uint64(meta.Bytes) != f.UncompressedSize64 || e != nil || len(hash) != 32 {
			return nil, fmt.Errorf("invalid image destination/size/hash: %s", name)
		}
		r, e := f.Open()
		if e != nil {
			return nil, e
		}
		h := sha256.New()
		var n int64
		if name == "boot.img" || name == "recovery.img" {
			var data []byte
			data, e = io.ReadAll(r)
			n = int64(len(data))
			if e == nil {
				h.Write(data)
				staged[name] = data
			}
		} else {
			n, e = io.Copy(h, r)
		}
		closeErr := r.Close()
		if e != nil || closeErr != nil || n != meta.Bytes || !sameSHA(h.Sum(nil), meta.SHA256) {
			return nil, fmt.Errorf("payload integrity failure: %s", name)
		}
	}
	kit, e := readSmall(files["hfs-kit.bin"], 16<<20)
	if e != nil {
		return nil, e
	}
	ksum := sha256.Sum256(kit)
	if c.KitBytes != int64(len(kit)) || !sameSHA(ksum[:], c.KitSHA256) {
		return nil, errors.New("HFS kit integrity failure")
	}
	if _, e = parseKit(kit, dataBytes); e != nil {
		return nil, e
	}
	var splash []byte
	if c.Splash.Bytes > 0 {
		if files["splash.jpg"] == nil {
			return nil, errors.New("splash.jpg missing")
		}
		if splash, e = readSmall(files["splash.jpg"], splashMax); e != nil {
			return nil, e
		}
		ssum := sha256.Sum256(splash)
		if int64(len(splash)) != c.Splash.Bytes || !sameSHA(ssum[:], c.Splash.SHA256) {
			return nil, errors.New("splash integrity failure")
		}
	}
	b := &Bundle{Config: c, Files: files, Kit: kit, Staged: staged, Splash: splash}
	if e = checkImages(b); e != nil {
		return nil, e
	}
	return b, nil
}
func readAt(f *zip.File, at int64, count int) ([]byte, error) {
	r, e := f.Open()
	if e != nil {
		return nil, e
	}
	defer r.Close()
	if _, e = io.CopyN(io.Discard, r, at); e != nil {
		return nil, e
	}
	b := make([]byte, count)
	_, e = io.ReadFull(r, b)
	return b, e
}
func androidHead(f *zip.File) (int64, error) {
	h, e := readAt(f, 0, 2048)
	if e != nil {
		return 0, e
	}
	u := func(at int) int64 { return int64(binary.LittleEndian.Uint32(h[at : at+4])) }
	if string(h[:8]) != "ANDROID!" || u(36) != 2048 || u(40) != 2 {
		return 0, errors.New("expected Android v2/page 2048")
	}
	align := func(n int64) int64 { return (n + 2047) / 2048 * 2048 }
	at := int64(2048) + align(u(8)) + align(u(16)) + align(u(24)) + align(u(1632))
	end := at + align(u(1648))
	if u(1648) < 4 || end >= 16<<20 || end > int64(f.UncompressedSize64) {
		return 0, errors.New("invalid boot head extent")
	}
	magic, e := readAt(f, at, 4)
	if e != nil || !bytes.Equal(magic, []byte{0xd7, 0xb7, 0xab, 0x1e}) {
		return 0, errors.New("Samsung DT table missing")
	}
	return end, nil
}
func checkAPFS(f *zip.File, at, maximum int64) error {
	h, e := readAt(f, at, 48)
	if e != nil {
		return e
	}
	if string(h[32:36]) != "NXSB" || binary.LittleEndian.Uint32(h[36:40]) != 4096 {
		return errors.New("APFS header/geometry invalid")
	}
	n := binary.LittleEndian.Uint64(h[40:48])
	if n == 0 || n > uint64(maximum)/4096 || uint64(at)+n*4096 > f.UncompressedSize64 {
		return errors.New("APFS exceeds device window")
	}
	return nil
}
func checkImages(b *Bundle) error {
	boot, rec := b.Files["boot.img"], b.Files["recovery.img"]
	end, e := androidHead(boot)
	if e != nil {
		return e
	}
	rend, e := androidHead(rec)
	if e != nil {
		return e
	}
	if int64(boot.UncompressedSize64) != end || rend != end || int64(rec.UncompressedSize64) != capacities["recovery"] {
		return errors.New("boot/recovery sizes do not match layout")
	}
	bh, e := readAt(boot, 0, int(end))
	if e != nil {
		return e
	}
	rh, e := readAt(rec, 0, int(end))
	if e != nil {
		return e
	}
	if !bytes.Equal(bh, rh) {
		return errors.New("boot head differs from recovery")
	}
	kernel, e := readAt(rec, 32<<20, 4)
	if e != nil || !bytes.Equal(kernel, []byte{0xcf, 0xfa, 0xed, 0xfe}) {
		return errors.New("kernel missing")
	}
	footer, e := readAt(rec, capacities["recovery"]-64, 64)
	if e != nil {
		return e
	}
	orig := binary.BigEndian.Uint64(footer[12:20])
	vb := binary.BigEndian.Uint64(footer[20:28])
	vs := binary.BigEndian.Uint64(footer[28:36])
	if string(footer[:4]) != "AVBf" || orig == 0 || orig > vb || vb >= 16<<20 || vs == 0 || vs > 16<<20-vb {
		return errors.New("invalid recovery AVB layout")
	}
	if e = checkAPFS(rec, 52<<20, capacities["recovery"]-(52<<20)-64); e != nil {
		return e
	}
	return checkAPFS(b.Files["system.apfs"], 0, systemMax)
}

type Extent struct {
	Offset int64
	Length int64
	Data   []byte
}

func validHFS(h []byte, size int64) bool {
	return len(h) >= 512 && string(h[:2]) == "HX" && binary.BigEndian.Uint16(h[2:4]) == 5 && binary.BigEndian.Uint32(h[40:44]) == 4096 && uint64(binary.BigEndian.Uint32(h[44:48]))*4096 == uint64(size)
}
func parseKit(data []byte, size int64) ([]Extent, error) {
	if len(data) < 32 || string(data[:8]) != "HFSKIT01" || binary.LittleEndian.Uint32(data[8:12]) != 4096 || binary.LittleEndian.Uint64(data[16:24]) != uint64(size) || crc32.ChecksumIEEE(data[32:]) != binary.LittleEndian.Uint32(data[24:28]) {
		return nil, errors.New("invalid HFS kit header/capacity/CRC")
	}
	n := uint64(binary.LittleEndian.Uint32(data[12:16]))
	if n == 0 || n > 4096 || 32+n*16 > uint64(len(data)) {
		return nil, errors.New("invalid HFS extent table")
	}
	pos := int64(32 + n*16)
	end := int64(0)
	extents := make([]Extent, 0, n)
	for i := uint64(0); i < n; i++ {
		entry := data[32+i*16 : 48+i*16]
		block := binary.LittleEndian.Uint64(entry[:8])
		count := uint64(binary.LittleEndian.Uint32(entry[8:12]))
		kind := binary.LittleEndian.Uint32(entry[12:16])
		if count == 0 || block > uint64(size)/4096 || count > uint64(size)/4096-block || int64(block*4096) < end || kind > 1 {
			return nil, errors.New("invalid HFS extent")
		}
		x := Extent{Offset: int64(block * 4096), Length: int64(count * 4096)}
		if kind == 1 {
			if x.Length > int64(len(data))-pos {
				return nil, errors.New("truncated HFS extent data")
			}
			x.Data = data[pos : pos+x.Length]
			pos += x.Length
		}
		end = x.Offset + x.Length
		extents = append(extents, x)
	}
	if pos != int64(len(data)) {
		return nil, errors.New("unexpected HFS kit trailing bytes")
	}
	header := func(at int64) []byte {
		for _, x := range extents {
			if at >= x.Offset && at+512 <= x.Offset+x.Length && len(x.Data) > 0 {
				return x.Data[at-x.Offset : at-x.Offset+512]
			}
		}
		return nil
	}
	if !validHFS(header(1024), size) || !validHFS(header(size-1024), size) {
		return nil, errors.New("HFS primary/alternate headers missing or wrong geometry")
	}
	return extents, nil
}
func hasModel(list []string, value string) bool {
	for _, s := range list {
		if s == strings.TrimSpace(value) {
			return true
		}
	}
	return false
}
