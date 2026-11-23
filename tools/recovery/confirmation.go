// SPDX-License-Identifier: MIT
package main

import (
	"errors"
	"time"
)

func waitForConfirmation(events <-chan [2]int, timeout <-chan time.Time, autoProceed bool, log func(string)) error {
	var hold *time.Timer
	var held <-chan time.Time
	defer func() {
		if hold != nil {
			hold.Stop()
		}
	}()
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
						log("45-second cancel window expired; proceeding with installation.")
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
			if ev[0] == 115 {
				if ev[1] == 1 {
					if hold != nil {
						hold.Stop()
					}
					hold = time.NewTimer(3 * time.Second)
					held = hold.C
				}
				if ev[1] == 0 && hold != nil {
					hold.Stop()
					held = nil
				}
			}
		case <-held:
			return nil
		}
	}
}
