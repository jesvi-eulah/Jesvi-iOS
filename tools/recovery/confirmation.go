// SPDX-License-Identifier: MIT
package main

import (
	"errors"
	"time"
)

// installWindow: how long a write-enabled install waits for Volume Down/Power before it proceeds.
const installWindow = 10 * time.Second

// waitForConfirmation: a new Volume Up press confirms, Volume Down or Power cancels.
// Only key-down events count (value 1), so a key held from before the prompt does not confirm.
func waitForConfirmation(events <-chan [2]int, timeout <-chan time.Time, autoProceed bool, log func(string)) error {
	for {
		select {
		case <-timeout:
			// Prefer a cancellation already queued at the deadline.
			for {
				select {
				case ev, ok := <-events:
					if !ok {
						return errors.New("physical key input unavailable")
					}
					if (ev[0] == 114 || ev[0] == 116) && ev[1] == 1 {
						return errors.New("installation cancelled")
					}
				default:
					if autoProceed {
						log("10-second cancel window expired; proceeding with installation.")
						return nil
					}
					return errors.New("physical confirmation timed out; no writes authorized")
				}
			}
		case ev, ok := <-events:
			if !ok {
				return errors.New("physical key input unavailable")
			}
			if (ev[0] == 114 || ev[0] == 116) && ev[1] == 1 {
				return errors.New("installation cancelled")
			}
			if ev[0] == 115 && ev[1] == 1 {
				return nil
			}
		}
	}
}
