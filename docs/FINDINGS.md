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

## Open
- Receive a file while connected (`AIRDROP=1 awdl-coex-test`): expected to hit the missing-ACK problem again.
- Getting the firmware to ACK for the listener context (peer stations / IBSS-like context next to the station).
