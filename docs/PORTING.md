# Porting the driver change to another Wi-Fi chip

For humans and AI agents. The user-space side of this repository (services, Owly radio and receiver, tray,
package) is driver-independent. To bring "AirDrop while the Wi-Fi stays connected" to another card, only the
**kernel driver** has to change, so that it meets the contract below. iwlwifi on the Intel AX211 is the
working reference (`patches/iwlwifi-awdl-coex-7.3.patch`, source in `dkms/iwlwifi`).

Read [FINDINGS.md](FINDINGS.md) before you start. Every rule here comes from a measurement recorded there.

## How the pieces fit

```
iPhone ──AWDL, channel 6──► awdlmon (monitor vif, own MAC) ──► Owly AWDL engine ──► awdl0 (TAP, IPv6)
                                   │ same radio, firmware time-shares          └──► owly receive :8771
router ◄──── station wlan0 (channel of the router, e.g. 112) ────────────────────── normal traffic
```

- `coex-session` (root) creates `awdlmon` with `iw dev wlan0 interface add awdlmon type monitor`, gives it
  its own address, brings it up and sets channel 6 (2.4 GHz, 20 MHz).
- `coex-radio` is Owly's AWDL engine on `awdlmon`: radiotap RX, frame injection, and the `awdl0` TAP.
- `owly receive` serves AirDrop on `awdl0`. Consent arrives as a GNOME notification (`coex-receive.py`).
- `awdl-coex-boot.service` prepares `awdlmon` before NetworkManager connects. `awdl-coex-radio.service` and
  the user unit `omdrop-coex-receive.service` keep it on. The system-sleep hook removes `awdlmon` before
  suspend and restores it on resume.

## The contract a driver must meet

1. **Opt-in switch.** Add a boolean module parameter named exactly `awdl_coex`, default off, readable in
   sysfs (`0444`). User space detects a coexistence driver with
   `grep -qx Y /sys/module/*/parameters/awdl_coex`, so no other file needs to know the module's name.
   Restrict it to the chips you have actually tested (iwlwifi refuses anything except PCI `8086:7e40`).
2. **A monitor next to an associated station, on another channel.** Adding `awdlmon` and setting it to
   channel 6 must not disassociate the station or retune it. The firmware has to time-share two channels.
   Refuse a monitor on the station's own channel (`-EBUSY`): promiscuous reception there takes the
   station's frames away.
3. **The monitor is a real hardware context with its own address, and the hardware ACKs unicast frames
   sent to that address.** This is the part that makes discovery work. Without ACKs the iPhone retransmits
   every frame about 8 times, TLS takes seconds, and the PC never appears in the share sheet
   (FINDINGS §3, §8, §12). In mac80211 terms: no virtual monitor
   (`ieee80211_hw_set(hw, NO_VIRTUAL_MONITOR)` / `WANT_MONITOR_VIF`), and the monitor's `vif->addr` is
   programmed into the hardware as an address to receive and ACK for. Refuse a monitor whose address equals
   the station's (`-EADDRINUSE`): two contexts on one address leave the listener without ACKs of its own.
4. **Promiscuous reception on the monitor channel only.** AWDL action frames, group data and unicast data
   to the monitor address must reach the monitor, with radiotap metadata that includes real RSSI (Owly's
   peer handling needs it).
5. **Injection with TX status.** Frames Owly injects on the monitor go out on channel 6 at the given rate,
   and unicast frames report whether they were ACKed (`REPORTS_TX_ACK_STATUS`).
6. **The station keeps working.** Its RX path must not change while the monitor exists. In iwlwifi, keeping
   `RX_INCLUDES_FCS` (the monitor default) made WPA fail on the station (FINDINGS §7).
7. **Suspend/resume and firmware restart survive.** User space deletes the monitor before suspend. The
   driver must still come back cleanly if a monitor existed when the firmware restarted. Test it.

A chip whose firmware cannot keep two MAC contexts on two channels can't meet points 2 and 3. Then only
exclusive mode is possible: Owly's IBSS cell, which disconnects Wi-Fi.

## The iwlwifi implementation, piece by piece

| File | Change | Why |
|---|---|---|
| `iwl-modparams.h`, `iwl-drv.c` | `awdl_coex` parameter | Opt-in switch, contract point 1 |
| `pcie/gen1_2/trans.c` | Single RX queue when `awdl_coex` and PCI `0x7e40` | The firmware delivers the listener's RX notifications on queue 0. One queue keeps ordering and sync barriers simple |
| `mvm/mac80211.c` `iwl_mvm_mac_setup_register` | `NO_VIRTUAL_MONITOR`, refuse other devices or several RX queues | The monitor becomes a real firmware LISTENER context (point 3) |
| `mvm/mld-mac80211.c` `iwl_mvm_mld_mac_add_interface` | Refuse a monitor on the station's MAC; don't set `RX_INCLUDES_FCS` | Points 3 and 6 |
| `mvm/mld-mac80211.c` `__iwl_mvm_mld_assign_vif_chanctx` | Refuse the monitor's channel context on the station's channel | Point 2 |
| `mvm/mac80211.c`, `mvm/mac-ctxt.c` (legacy, non-MLD API) | Same rules; LISTENER with the AWDL BSSID `00:25:00:ff:94:73` and promiscuous filters only once a separate channel is bound | Older firmware APIs |

Firmware 89 on the AX211 uses the **MLD API inside iwlmvm**, so the live path is `mld-*.c`. Check which
API your firmware selects before you edit (iwlmvm logs `mld_api=`).

The approach follows [ForbiddenItlwm](https://github.com/retropineaple/ForbiddenItlwm)'s macOS driver
(`itlwm/hal_iwx/ItlIwx.cpp`, `awdlCoexMacSend` and `awdlCoexListener`): a LISTENER context with its own
address, PHY and binding. Its `docs/HOW-IT-WORKS.md` lists firmware behaviour learned the hard way.

## Hints for other drivers (unverified)

None of these has been tested here. Treat each one as a hypothesis to measure. The per-card status lives in
the README's [Supported Wi-Fi cards](../README.md#supported-wi-fi-cards) table: update it with every port.

- **mt76 (MediaTek mt7921/mt7922):** check `NL80211_MNTR_FLAG_ACTIVE` first. An *active* monitor ACKs in
  hardware and might already satisfy point 3. The open question is point 2: a monitor on another channel
  next to the station. [jedbillyb/airdrop-mt7921](https://github.com/jedbillyb/airdrop-mt7921) is prior
  art for AirDrop on that chip.
- **rtw89 (Realtek):** [FranciumOS-org/AirPort_RTW89](https://github.com/FranciumOS-org/AirPort_RTW89) did
  AWDL on a Realtek card for macOS, which shows how its firmware can be driven. Look for multi-port/MCC
  (multi-channel concurrency) support and per-port MAC addresses.
- **ath11k/ath12k (Qualcomm):** multiple vdevs with their own MAC and channel exist for AP+STA. A monitor
  vdev may need to be promoted to one of them.
- **brcmfmac and other FullMAC drivers:** monitor and injection live in the firmware. Usually not possible.

## What changes outside the driver when you port

- `dkms/`: the driver source and `dkms.conf` (`BUILT_MODULE_NAME`, `BUILD_EXCLUSIVE_KERNEL`, `LLVM=1` only
  for clang-built kernels).
- `packaging/arch/PKGBUILD`: `depends` (kernel headers package), the modprobe option in
  `dkms/awdl-coex.conf`.
- The user-space scripts reload `iwlmvm`/`iwlwifi` in two places: `install-coex` (`reload`) and
  `scripts/awdl-coex-test`. Use your module names there.
- `WLAN=wlan0` is the default in `coex-session`. Set the environment variable if your station interface has
  another name.

Nothing else should need to change: detection is the glob above, and the radio path is plain nl80211.

## Pitfalls already met

- cfg80211 sets a monitor's channel only while no other interface is running (`EBUSY`). Changing it at run
  time takes the station down for a few seconds, and that reconnection failed once (FINDINGS §13). That is
  why `awdl-coex-boot.service` sets channel 6 before NetworkManager starts.
- A monitor holding a channel context across suspend: mac80211 warned (`pm.c`, chanctx list not empty),
  D3 entry timed out, and on resume iwlmvm hit `Adding active MAC` (-EIO). Afterwards no authentication
  worked until the driver was reloaded (FINDINGS §14). The sleep hook avoids it; your driver may need the
  same, or a real fix.
- `modprobe --remove <op_mode>` also removes the now-unused base module you just inserted (`Unknown
  symbol` on the next `insmod`). Use `rmmod`.
- A monitor that receives only the host's own TX means the hardware isn't listening on the channel. Use a
  separate vif, not `set type monitor` on the station.
- With the station on 5 GHz DFS channels, latency rises from about 3 ms to 20 ms (idle) and about 250 ms
  (during a transfer) because of time sharing.

## Test protocol, in order (each gate must pass before the next)

Save your work and enable EFI pstore first: these experiments have crashed firmware and the kernel. Do one
radio experiment per boot. Never loop `sudo` without a TTY: `pam_faillock` locks the account.

1. **Station alone** with the patched module and `awdl_coex=1`: ping the gateway, no firmware errors.
2. **Monitor next to the station** (`scripts/awdl-coex-test`): zero packet loss to the gateway; the
   monitor captures AWDL frames (`wlan.bssid == 00:25:00:ff:94:73`) while an iPhone has the share sheet open.
3. **ACKs:** with `AIRDROP=owly scripts/awdl-coex-test`, the phone's unicast frames to the monitor address
   should not keep the retry bit set, and Owly's counters show `tx_unicast` and `delivered` growing.
4. **Receive** a photo: the size matches the offer and the image decodes. Pre-existing files don't count.
5. **Always on:** install the package, reboot, receive without touching anything, and check for zero
   `wlan0` disconnects in `journalctl -b`.
6. **Suspend and resume** with AirDrop on: the Wi-Fi reconnects and a second photo arrives.
7. **Recovery:** remove the package and check that the stock driver comes back after a reboot.

Record every result, including failures, in FINDINGS.md with absolute dates. Never commit captures, logs
with MAC addresses, SSIDs or host names.
