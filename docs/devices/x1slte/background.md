# What runs in the background, and the switches for it

`tools/bg-status.sh` (read-only) prints all of this from the phone: load, the processes above 2 % CPU, our launchd
services, the known iOS spinners, every debug switch below, and the last cellular health line.

## 2026-11-13: why it felt laggy

| Cause | Cost | Fix |
| --- | --- | --- |
| `aggregated` (powerlog's daily archiver) making one archive per day since 1970 | 92 % of a core all the time; 12,691 files, 596 MB | moved to /var/root/powerlog-backup-* and restarted (0 %); root cause: the clock |
| the clock starts every boot at 1970 (no RTC read) | iOS daemons date their records 1970 | `init` restores the later of saved UTC and image build time before iOS starts; native `clockd` obtains network UTC and saves time each minute |
| redwood-cellulard writing a line per modem doorbell / IPC message | 38 KB/min of log (~55 MB/day) | quiet by default, log cut back at 8 MB |

`aggregated` itself must stay allowed: Settings > Battery's power log runs inside it (userland/mkjobs.py DENY comment).
If it spins again: `ls /private/var/containers/Shared/SystemGroup/*/Library/BatteryLife/Archives | wc -l` -- hundreds of
`powerlog_19xx-*` files = the 1970 clock again.

## Our background services (launchd, /redwood/LaunchDaemons)

| Job | What | Needed for |
| --- | --- | --- |
| com.redwood.cellular | redwood-cellulard: modem, data, IMS PDN, starts redwood-ims | cellular |
| com.redwood.logd | rwlogd: the log/HTTP server on :8080 | development |
| com.redwood.clockd | native UTC bootstrap and persistent clock snapshots | clock |
| com.redwood.sshd | ssh | development |
| com.redwood.lpmd | low-power-mode helper | battery |
| com.redwood.finder-host | registers Jesvi Files, then exits | Files, Finder |
| com.redwood.demo | runs /redwood/etc/rc.jobs once at boot (self-tests, `cpu_test 240`: a short burst 4 min after boot) | boot checks; `RC_JOBS=` at build time picks another list |
| com.redwood.varstore, thermald, wifi | one-shot / on demand | |

## Clock restoration and network synchronization

The native clock service (`userland/src/clockd.c`) starts with launchd and retries
network time every minute until one valid reply sets system UTC, without rebooting.
It then leaves later manual corrections alone and saves the clock every minute,
using a monotonic timer so a backward manual correction does not stall saving.
Persistence is independent of the debug HTTP server. Both userland build paths
compile/install the service; a missing prebuilt is a build error.

On a fresh/offline boot, init uses the image's `/redwood/etc/build-time` if no newer
valid snapshot exists. That avoids 1970 records before networking starts, but is
only an estimate. This port still has no hardware RTC reader, so time spent powered
off cannot be recovered while offline. UTC synchronization does not determine the
user's timezone. The service bootstraps once per start; it is not a full NTP drift
discipline daemon or an implementation of Apple's timed XPC service.

Unicast SNTP uses a connected UDP socket, a random originate token, bounded receive
timeout and stratum/leap/version/mode checks per [RFC 4330 section 5](https://www.rfc-editor.org/rfc/rfc4330#section-5).
Replies with invalid timestamps are rejected; the 2036 NTP era rollover is handled.
SNTP is unauthenticated. It queries `time.apple.com`, then fallback servers
`time.cloudflare.com` and `pool.ntp.org`; UDP/123 and DNS must be reachable.

## Debug switches

| Switch | Default | How |
| --- | --- | --- |
| cellular per-message log | off | `echo "verbose on" > /var/tmp/redwood-cell/cmd` (until restart); `touch /var/root/cell-verbose` (from the next start) |
| cellular log size | cut at 8 MB | /var/tmp/redwood-cellular.log |
| VoLTE client | on | `touch /var/root/cell-noimsclient` = never started |
| IMS PDN | on | `touch /var/root/cell-noims` |
| mobile data | on | `echo nodata > /var/tmp/redwood-cell/cmd` (kept in /var/root/cell-nodata) |
| modem restart | - | `echo restart > /var/tmp/redwood-cell/cmd` |
| island pill | built-in 18pro-small | `tools/island-preset.sh NAME` (docs/devices/x1slte/dynamic-island.md) |
| kernel stats lines | on | `dvfs=2` prints clocks/temperatures every 10 s; the sensor hub (`shub=6`) relays its own debug text. Both go to the kernel ring only (cheap); a switch for them is a kernel change, not done yet |

Left on the phone, inert: old test libraries in /var/tmp (b-libredwood-*, codex-libredwood-als-*, libredwood-brightness*)
are not in the injection list (`kern.exec_inject`), so they cost nothing.

## Screen sleep (idle timer)

backboardd's library (`userland/src/inject.c`, `idle_thread`) presses the lock button for iOS, whose own idle timer
never fires on this phone. Three modes:

| Mode | What turns the screen off |
| --- | --- |
| 0 | nothing (iOS's own, broken, timer) |
| **1** (default since 2026-11-13) | only the lock screen: 10 s (`idle_lock_s=`) after a wake nobody touched. Unlocked, the screen stays on. |
| 2 (default 2026-11-12..13) | the lock screen as in 1, and Auto-Lock's time from Settings once unlocked (not while sound plays) |

Switch without a rebuild: `ssh s20 'echo mode=2 > /var/jb/etc/redwood-idle.conf'` (read at every wake; delete the file
for the default). Boot argument `idle_lock=` sets the default too. Check: the kernel log line
`redwood: idle timer (idle_lock=1): 10 s after a wake with no touch`.
