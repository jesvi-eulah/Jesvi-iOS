package main

import (
	"strings"
	"testing"
	"time"
)

func TestConfirmationTimeoutPolicy(t *testing.T) {
	for _, auto := range []bool{false, true} {
		timeout := make(chan time.Time, 1)
		timeout <- time.Now()
		err := waitForConfirmation(make(chan [2]int), timeout, auto, func(string) {})
		if auto && err != nil || !auto && (err == nil || !strings.Contains(err.Error(), "timed out")) {
			t.Fatalf("auto=%v error=%v", auto, err)
		}
	}
}

func TestCancelWinsAtDeadline(t *testing.T) {
	for _, key := range []int{114, 116} {
		events := make(chan [2]int, 2)
		events <- [2]int{115, 0}
		events <- [2]int{key, 1}
		timeout := make(chan time.Time, 1)
		timeout <- time.Now()
		if err := waitForConfirmation(events, timeout, true, func(string) {}); err == nil || !strings.Contains(err.Error(), "cancelled") {
			t.Fatalf("key=%d error=%v", key, err)
		}
	}
}

func TestLostKeyInputDoesNotAuthorizeWrites(t *testing.T) {
	events := make(chan [2]int)
	close(events)
	timeout := make(chan time.Time, 1)
	timeout <- time.Now()
	if err := waitForConfirmation(events, timeout, true, func(string) {}); err == nil {
		t.Fatal("lost cancellation controls must stop installation")
	}
}
