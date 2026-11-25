// SPDX-License-Identifier: MIT
package main

import (
	"fmt"
	"io"
	"strings"
)

// The TWRP screen: a plain title, numbered steps, TWRP's own progress bar and a text bar.
// TWRP's console is about 40 columns of plain ASCII, so everything stays inside that.

const uiWidth = 38

// screen writes to the recovery pipe; nil in tests and in --inspect.
type screen struct {
	pipe     io.Writer
	total    int64 // bytes of work in the whole plan (writes and readbacks)
	done     int64
	shown    int // last percent printed as text
	step     int
	steps    int
	stepName string
}

var ui = &screen{}

var releaseName string // set by the builder (-X main.releaseName=...), e.g. "v0.1.1 (2026-11-19)"

func releaseVersion() string {
	if releaseName == "" {
		return "development build"
	}
	return releaseName
}

func (s *screen) raw(cmd string) {
	if s.pipe != nil {
		fmt.Fprintf(s.pipe, "%s\n", cmd)
	}
}
func (s *screen) print(line string) {
	if s.pipe != nil {
		fmt.Fprintf(s.pipe, "ui_print %s\nui_print\n", uiText(line))
	}
}

func rule() string { return strings.Repeat("=", uiWidth) }

// header: the title, the product line and the release version.
func (s *screen) header(title, version, device string) {
	s.print(rule())
	s.print(center("J E S V I   i O S"))
	s.print(center(title))
	s.print(center(version + "  |  " + device))
	s.print(rule())
}

func center(t string) string {
	if len(t) >= uiWidth {
		return t
	}
	return strings.Repeat(" ", (uiWidth-len(t))/2) + t
}

// begin: a new numbered step, e.g. "[3/7] Writing iOS system".
func (s *screen) begin(name string) {
	s.step++
	s.stepName = name
	s.print("")
	s.print(fmt.Sprintf("[%d/%d] %s", s.step, max(s.steps, s.step), name))
}

// plan: how many bytes the writes will move, so the bar is the whole install, not one partition.
func (s *screen) plan(steps int, bytes int64) {
	s.steps, s.total, s.done, s.shown = steps, bytes, 0, -1
	s.raw("progress 1.0 0") // the whole bar is ours: set_progress fills the portion announced here (TWRP's bar)
	s.raw("set_progress 0.0")
}

// advance: called while copying; prints a bar at every 10 % of the whole install.
func (s *screen) advance(n int64) {
	if s.total <= 0 {
		return
	}
	s.done += n
	if s.done > s.total {
		s.done = s.total
	}
	pct := int(s.done * 100 / s.total)
	s.raw(fmt.Sprintf("set_progress %.3f", float64(s.done)/float64(s.total)))
	if pct/10 != s.shown/10 || (pct == 100 && s.shown != 100) {
		s.shown = pct
		s.print(bar(pct))
	}
}

func bar(pct int) string {
	const w = 26
	fill := pct * w / 100
	return fmt.Sprintf("  [%s%s] %3d%%", strings.Repeat("#", fill), strings.Repeat(".", w-fill), pct)
}

func (s *screen) finish(lines ...string) {
	s.raw("set_progress 1.0")
	s.print("")
	s.print(rule())
	for _, l := range lines {
		s.print(center(l))
	}
	s.print(rule())
}
