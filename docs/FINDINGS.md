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

## 10. GNOME tray using the existing Omdrop UI backend
- The Omarchy panel depends on Quickshell components. The installed Fdrop already provides a GTK
  interface and an asynchronous Omdrop CLI runner/status model, reused by `desktop/tray.py`.
- The indicator exposes receive windows, continuous reception, stop, the full interface and downloads.
  Starting it only queries status. Owly's probe gates each tray receive action; modes that take the
  station offline require explicit confirmation. A failed/unknown probe prevents startup.
- The current Omdrop status reports a running receiver with `visible=false` and `reason=radio-lost`.
  The indicator reports that unavailable radio, rather than claiming AirDrop is working.
- Validated 11 Python tests without radio access, the Owly announcement-policy test, and compilation
  of the coexistence adapter. The installed indicator is registered with GNOME's StatusNotifier watcher;
  its exported menu and state are readable over D-Bus. The tray service has no restarts in this check.
- After installation the station remains connected, Owly's radio state is `idle`, and an external
  HTTPS request succeeds. This checks that installing the UI did not take the radio; it is not a
  concurrent AirDrop/Internet test. The Omdrop receive path still needs a real phone transfer test.

## Open
- Receive a file while connected. First investigate discovery with the paired radio and `awdl0` captures
  from `AIRDROP=1 awdl-coex-test`; distinguish local announcements from radio transmission and peer responses.
- Getting the firmware to ACK for the listener context (peer stations / IBSS-like context next to the station).
