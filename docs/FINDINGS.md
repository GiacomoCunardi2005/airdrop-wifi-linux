# Findings, in order

Machine: Intel AX211 (PCI `8086:7e40`), `iwlmvm`, firmware `89.b20dcd1f.0 ma-b0-gf-a0-89`, kernel 7.3.4-1-cachyos,
router on 5 GHz channel 100 (DFS, 80 MHz). Phone: iPhone 16 Pro, iOS 27. All from 2026-11-14.

## 1. Monitor mode on iwlwifi
- `iw dev wlan0 set type monitor` reports monitor but receives nothing from the air (only the host's own TX).
  A separate monitor vif (`airmon-ng start`, or `iw ... interface add`) does receive.
- iwlwifi has no *active monitor* (`NL80211_MNTR_FLAG_ACTIVE` → `Operation not supported`), so no ACKs.
- Without a connection, only channel 6 allows transmit; 44 and 149 are `no IR`.

## 2. Stock OWL + OpenDrop (SEEMOO) vs iOS 27
- OWL joins the AWDL cluster, but stock OpenDrop is never contacted: it announces once and stays on channel 6.
- OpenDrop started before the `awdl0` link-local finishes DAD silently fails to bind mDNS.
- OWL's RSSI filter (-65 dBm) can hide peers; run with `-f`.

## 3. Forks (jedbillyb/owl + jedbillyb/opendrop)
- Diffed against upstream before use: radio logic and protocol fixes only.
- With `-S intersect` on channel 6 the iPhone does `POST /Discover` and gets `200` — but the PC never appears in
  the share sheet. Capture shows every phone frame ~8 times (no ACKs), TLS handshakes of ~4 s, resets.
- `-S verbatim` follows the phone to 44/149/100 where this card cannot transmit: nothing reaches the phone.

## 4. ACKs through a hidden AP next to the monitor
- `wpa_supplicant` AP on channel 6 (same MAC), with or without a separate vif: the monitor goes deaf
  (`rx_action 0`). Dead end on this card.

## 5. Stability
- One kernel panic and two firmware crashes (`Microcode SW error`), all around repeated monitor setup/teardown.
- Rule used since: one radio experiment per boot when possible; kernel log synced to disk; EFI pstore enabled.

## 6. Owly, exclusive mode — first real transfer
- Owly 0.4.3 (commit 21171d8) in exclusive mode (IBSS on channel 6, station released) received a 1.95 MB JPEG
  from the iPhone, decoded intact. IBSS gives the firmware a real MAC context, so frames are ACKed.
- Cost: no Wi-Fi Internet while the session runs.
- Targeted review of the root daemon: no network sockets, runs only `ip`/`nmcli`/`ping`/`mount`/`hostapd`,
  D-Bus callers pass only a duration, installed binaries match the local build. Not a full audit.

## 7. Coexistence experiment (patched iwlmvm, `awdl_coex=1`)
- Firmware 89 on this card uses the **MLD API inside iwlmvm** (`mld_api=1`): changes must go in
  `mvm/mld-mac80211.c` / `mvm/mld-mac.c`, not the legacy `mac-ctxt.c` path.
- The driver auto-loads the stock `iwlmvm` op mode after `insmod iwlwifi.ko`; unload it before inserting the patched one.
- A monitor vif can be added and brought up next to the station, but cfg80211 refuses to set its channel while
  another interface is running (`EBUSY`). Workaround: take the station down for a second, set channel 6, bring it back.
- With `RX_INCLUDES_FCS` set (stock monitor behaviour) the station re-associates but WPA never completes
  (`corrupt beacon and probe response`, auth loop). Not setting it in coex mode fixes that.
- Result: station on channel 100 with **40/40 pings, 0% loss** while the channel-6 monitor captured 705 frames,
  **46 of them AWDL** from the phone. Gateway latency rises from ~3 ms to ~20 ms average (time sharing).
- No firmware errors in that run.

## 8. First receive attempt with the station connected (2026-11-14, 21:39–21:41 CET)
- The PC did not appear in the phone's AirDrop list. OpenDrop announced its service but received **zero requests**.
- Gateway ping: **114/114 replies, 0% loss**, average 20.762 ms, maximum 198.026 ms. This measures gateway
  reachability during the receive attempt, not uninterrupted Internet connectivity throughout setup and teardown.
- Last OWL counters: `tx_action 2654`, `tx_data 54` (all multicast), `tx_unicast 0`, `rx_action 239`, `rx_data 2`.
- The `awdl0` capture contains 40 packets: 36 mDNS and 4 ICMPv6, **no TCP**. Only two mDNS packets come from
  the peer. This establishes reception of some AWDL traffic, not successful delivery of our announcements to the phone.
- The JPEG listed at the end predates this attempt. The successful 17:24 CET transfer is recorded in the Owly
  receive log; `airdrop-owly` selects that configuration without extra flags. Shell history also contains an
  `airdrop-ricevi` invocation at 17:21, but that is not the receiver named by the successful transfer log.
- The script printed `disconnected` after teardown; a later check showed the station connected again.
  The exact cause of the delayed recovery is unproven. Cleanup now waits for the interface, restores NetworkManager
  management, exposes reconnect errors, and keeps the rollback timer on failure. It no longer substitutes PID 0
  for missing background processes. The test aborts if the safety timer cannot be armed.
- Subsequent receive attempts also capture `awdlmon` locally to inspect radio traffic alongside `awdl0`.
  Neither raw captures nor identifying logs are committed. Missing ACKs remain a hypothesis for this attempt;
  the available capture alone cannot establish the cause of failed discovery.

## 9. Repeatable exclusive reception; prepare an Owly coexistence comparison
- A second photo was received with `airdrop-owly` on 2026-11-14 at about 21:50 CET: **1,492,343 bytes**,
  matching the offered size. It decodes completely as a 3840×2160 JPEG. This is a second exclusive-mode
  success, not evidence of simultaneous Internet access.
- The successful Owly sessions announce in bursts of 64 packets; the earlier coexistence test used OpenDrop
  announcements every five seconds. Both the AWDL engine and AirDrop implementation also differ.
- Prepared `AIRDROP=owly awdl-coex-test` to reuse Owly's native AWDL engine and its receiver on the existing
  coexistence monitor. The fixed-channel mDNS policy is selected explicitly. See `experiments/README.md`.
  No changes to the working installed Owly service or the driver patch are required for this comparison.
- The receive test now measures an external Internet host as well as the gateway. Radio captures remain local.
- Driver review: `nic_not_ack_enabled` in the MLD MAC configuration concerns reception of **ACK-enabled
  aggregates**, per `fw/api/mac-cfg.h`; it is not an ordinary unicast ACK on/off switch. Do not flip it on
  the assumption that it enables monitor ACKs.
- Station + IBSS is absent from this driver's advertised combinations. An [earlier AX211 report](https://github.com/t4t5/owly/issues/4)
  describes a firmware fatal error when forcing that combination on another device/firmware. It does not
  prove impossibility here, but supports measuring the existing listener before changing interface limits.
- The new Owly coexistence path has not yet been tested on the radio. It still uses a monitor without an
  ACKing cell, so it may improve discovery without producing reliable transfers.

## 10. Original Owly demo panel hosted on GNOME
- Inspected Owly's README video. It shows Omdrop's Omarchy panel. `desktop/qml` now reuses that
  original panel, radar, icon and Omarchy controls, with a standalone GNOME/XWayland popup host.
  The earlier Fdrop-based launcher was replaced. See `desktop/README.md` for pinned sources/licenses.
- Duration, audience, known senders, peer radar, sending, name and destination remain the original UI.
  Its CLI bridge probes Owly before starting reception/sending, with explicit confirmation for modes
  that disconnect Wi-Fi. A lost radio no longer spends 200 seconds described as "waking".
- The 22:27–22:29 Omdrop attempt brought up Owly's exclusive radio and heard the phone. Its Python
  receiver logged no requests. Periodic announcements succeeded locally; that doesn't establish
  delivery to the phone. The session ended by explicit lease release, not a firmware crash.
- Unlike `owly receive`, that fallback stack doesn't run an mDNS question responder. Added a controlled
  comparison using Owly's existing responder beside the same receiver (`experiments/owly-mdns.rs`).
  It uses the existing lease and Omdrop hostname; no radio acquisition. This is a discovery hypothesis,
  not a proven fix. The service is installed and enabled with the receiver; no new transfer is verified.
- Validated 12 Python tests, 10 native mDNS protocol tests and responder compilation. The original panel
  renders and opens on GNOME; its screenshot is in `desktop/panel.png`. The receiver remains off,
  Owly's state is idle, Wi-Fi stays connected and an external HTTPS request succeeds after UI installation.
  These are UI/installation checks, not simultaneous AirDrop/Internet or phone-transfer evidence.

## 11. Coexistence loader stopped before the radio test (22:51 CET)
- The first native Owly attempt stopped at `insmod iwlmvm.ko: File exists`, before creating a monitor
  or starting AirDrop. Under `pipefail`, `lsmod | grep -q` returned 141 even though the module existed:
  the early reader exit caused SIGPIPE in `lsmod` (reproduced in 20/20 read-only checks).
- Module presence now uses `/sys/module/iwlmvm`; removal retries for up to five seconds before insertion.
  A regression test models the failed pipeline and checks removal before insertion.
- Reconnection now activates the saved NetworkManager connection UUID, instead of relying on generic
  device activation. The failed attempt recovered Wi-Fi; the leftover rollback timer was stopped and
  external HTTPS worked. These changes fix test setup/recovery, not AirDrop coexistence itself.
- Validated 13 Python tests, shell syntax and patch whitespace after the loader/reconnection changes.

## 12. First AirDrop receive with the station connected (2026-11-15, 13:21–13:25 CET)
- Root cause of the failed discovery in §8: `awdlmon` inherited the station MAC, so the firmware LISTENER context
  had no address of its own to ACK. ForbiddenItlwm notes that ACKs must match the MAC context's address.
- Fix: the test gives `awdlmon` a locally administered address (first octet `| 0x02`, last octet `^ 0x5a`
  of the station MAC) before bringing it up. With `awdl_coex=1` the driver now refuses a monitor on the station
  address (`-EADDRINUSE`) and logs the listener address.
- Loader fix: `modprobe --remove iwlmvm` also removed the patched, now unused `iwlwifi`, so `insmod iwlmvm.ko`
  failed with `Unknown symbol` (00:28 attempt). Replaced by an `rmmod iwlmvm` retry and an `iwlwifi` presence check.
- Modules must be built with `LLVM=1`: the CachyOS kernel is built with clang.
- Result with `AIRDROP=owly awdl-coex-test`: the iPhone listed the PC and sent two photos, both **1,952,650 bytes**,
  both decoded completely as 4032×3024 JPEGs. Station on 5 GHz channel 112 (80 MHz), listener on channel 6.
- During the 170 s receive window: gateway 163/170 replies (4.1% loss), external host 163/170 (4.1% loss);
  average RTT about 250 ms with peaks of 2.3 s (time sharing between the two channels). No deauthentication
  of `wlan0` between the reconnect after the channel-6 setup and the final teardown. No firmware errors.
- Owly counters: `tx_unicast 1803`, `rx_data 3093`, `delivered 3068`, `gave up 0`.
- Not yet measured: setup still drops the station for a few seconds (cfg80211 `EBUSY` workaround, step 3b);
  latency under load; larger files; PC → iPhone; repeated runs.

## 13. Tray start with the station connected: Wi-Fi lost (2026-11-15, 13:38–13:40 CET)
- `coex-session start` (from the tray) had to take the station down to set channel 6 (cfg80211 `EBUSY`).
  After the station came back, NetworkManager's scan stayed pending for 25 s (`ssid-not-found`,
  `Reject scan trigger since one is already pending`). Wi-Fi only reconnected after the engine was
  stopped (13:40:41). The awdl-coex-test run of §12 reconnected in about 2 s on the same sequence.
- Meanwhile the panel ran `pkexec omdrop-discoverable peers` (the exclusive backend, root) every 2 s.
  Whether that blocks scans is unproven. In coex mode `peers` now answers `[]` without touching the card.
- Mitigation: `awdl-coex-boot.service` prepares awdlmon on channel 6 before NetworkManager connects, so
  starting never takes the station down; the fallback waits 2 s before reconnecting, as the test did.
- Open: whether the station can scan, roam and reconnect while the AWDL engine is running.

## 14. Suspend with the AWDL monitor up kills Wi-Fi until the driver is reloaded (2026-11-15, 14:00 CET)
- Boot with `awdl-coex-boot.service`: awdlmon prepared on channel 6 at 13:45:32, station associated at
  13:46:30. Preparing the monitor before NetworkManager works.
- Suspend at 14:00:39 with awdlmon up: `WARNING net/mac80211/pm.c:173` (chanctx list not empty),
  `Timeout entering D3`, `fast suspend: trans_d3_suspend failed -110`. On resume `ieee80211_reconfig` hit
  `WARNING mvm/mld-mac.c:257` (`Adding active MAC`, -EIO) for the monitor. Afterwards every
  authentication timed out and scans stayed pending, even with awdlmon down. Only a driver reload helps.
- Fix: `awdl-coex-sleep` (system-sleep hook) stops the engine and deletes awdlmon before sleep, prepares it
  again after resume and restarts the engine if it was running. Not yet tested across a suspend.

## 15. Broadcom BCM4352 (`14e4:43b1`): no driver can meet the contract (2026-11-15)
Checked on a second machine (Dell, BCM4352 802.11ac PCIe, Debian 13, kernel 6.12.74) without loading any
module or touching the radio. Result: not possible, neither coexistence nor Owly's exclusive mode.
- **`wl` (broadcom-sta 6.30.223.271, the driver in use):** `iw phy` lists only `IBSS` and `managed`, and
  "interface combinations are not supported". Its only monitor is the proprietary `/proc/brcm_monitor0`
  switch: receive-only, on the associated channel, no injection, no TX status, no second MAC. It fails
  contract points 2, 3 and 5. The driver is a closed binary blob, so it can't be patched.
- **`b43`:** the module has the alias for this 802.11 core (`bcma ... id0812rev2A`), but the chip uses the
  AC PHY, and `CONFIG_B43_PHY_AC` depends on `BROKEN` (absent from the distribution config). Even with it,
  b43 is a single-channel SoftMAC with no interface combinations and closed ucode, so points 2 and 3 fail.
- **`brcmsmac`:** no alias for this core revision. **`brcmfmac`:** no PCI ID for 43b1; the BCM4352 has no
  offload CPU, so there is no FullMAC firmware (and no Nexmon target) to patch.
- No existing Linux AirDrop/AWDL project (Owly, OWL, OpenDrop) supports it: all need monitor mode with
  injection.
- Way forward for such a laptop: swap the card (an Intel AX210 fits a non-CNVi M.2 slot; the AX211 is
  CNVi-only) or use a USB adapter in exclusive mode.

## Open
- Remove the short disconnect during setup (set the monitor channel without taking the station down).
- Reduce latency during sessions (channel time quotas); repeat runs; larger files; sending.
