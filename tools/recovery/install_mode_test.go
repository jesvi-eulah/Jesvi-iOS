package main

import (
	"strings"
	"testing"
)

func TestInstallMode(t *testing.T) {
	for _, tc := range []struct {
		name, requested     string
		valid, recognizable bool
		want, errorText     string
	}{
		{"Android first install", "choose", false, false, "fresh", ""},
		{"preserve existing iOS", "choose", true, true, "update", ""},
		{"damaged or resized iOS", "choose", false, true, "", "refusing to erase"},
		{"update on Android", "update", false, false, "", "--set MODE=fresh"},
		{"update damaged iOS", "update", false, true, "", "update-only package"},
		{"update existing iOS", "update", true, true, "update", ""},
		{"fresh on Android", "fresh", false, false, "fresh", ""},
		{"fresh over existing iOS", "fresh", true, true, "fresh", ""},
		{"fresh over damaged iOS", "fresh", false, true, "fresh", ""},
		{"invalid mode", "other", false, false, "", "unsupported"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			got, err := selectInstallMode(tc.requested, tc.valid, tc.recognizable)
			if got != tc.want {
				t.Fatalf("mode=%q, want %q", got, tc.want)
			}
			if tc.errorText == "" {
				if err != nil {
					t.Fatal(err)
				}
			} else if err == nil || !strings.Contains(err.Error(), tc.errorText) {
				t.Fatalf("error=%v, want %q", err, tc.errorText)
			}
		})
	}
}
