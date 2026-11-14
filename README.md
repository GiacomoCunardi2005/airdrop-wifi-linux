# easy-airdrop-linux

Goal: make AirDrop from an iPhone to a Linux PC **easy**, using the Wi-Fi card the PC already has,
and without losing the Internet connection while it runs.

This repo is a lab notebook plus the scripts and patches that came out of it. Every new finding is committed.
Tested so far on one machine only: Intel AX211 (Meteor Lake CNVi, PCI `8086:7e40`, `iwlwifi`/`iwlmvm`,
firmware 89), CachyOS, kernel 7.3.4, iPhone 16 Pro on iOS 27.

## Status

| What | Status |
|---|---|
| Receive a photo from an iPhone (iOS 27), Wi-Fi **disconnected** during the session | **Works** with [Owly](https://github.com/t4t5/owly) in exclusive mode (`scripts/airdrop-owly`) |
| Radio hears AWDL **while the station stays connected** to the router | **Works** with the experimental driver patch: 40/40 pings to the gateway, 46 AWDL frames in 20 s |
| Receive a file **while Wi-Fi stays connected** | **Failed first attempt:** PC absent from the phone's list, zero AirDrop requests; gateway ping 114/114 |
| Send PC → iPhone, large files, long-term stability | Not tested |
| GNOME tray with status and Omdrop controls | Available in [desktop/](desktop/README.md); continuous reception still requires a working radio |

## Why this is hard

AirDrop runs over AWDL, Apple's peer-to-peer Wi-Fi link, on channels 6 / 44 / 149. A Linux receiver has to:

1. speak AWDL (channel hopping, sync, election) — done in user space by OWL / Owly through a monitor interface;
2. **ACK** the iPhone's frames — without 802.11 ACKs the phone retransmits every frame ~8 times and never lists the PC;
3. speak the current AirDrop protocol — iOS 26/27 use chunked bodies, `dvzip` archives and repeated mDNS announces;
4. do all of that on one radio that is also the station connected to the router.

See [docs/FINDINGS.md](docs/FINDINGS.md) for what was measured, in order, including the dead ends.

## What is in here

- `scripts/airdrop-owly` — the receive path that works today (takes the Wi-Fi card for up to 5 minutes).
- `scripts/awdl-coex-test` — loads the patched driver, puts a monitor on channel 6 next to the connected station,
  measures ping + AWDL frames, then attempts to restore the stock modules and reconnect (plus a rollback timer).
  `AIRDROP=1` runs a real receive attempt with OWL/OpenDrop; `AIRDROP=owly` runs the
  [Owly comparison](experiments/README.md). Both capture `awdl0` and the monitor radio locally and measure
  gateway plus external Internet reachability.
- `scripts/airdrop-ricevi`, `scripts/airdrop-conferma`, `scripts/awdl-diag` — the earlier OWL + OpenDrop path and
  diagnostics (monitor-only, no ACKs: the phone contacts the PC but never lists it on this card).
- `patches/` — the experimental `iwlwifi` patch (GPL-2.0), see `patches/README.md`.
- `desktop/` — GNOME AppIndicator using the existing Omdrop backend and Fdrop components;
  status, receive/stop controls and an explicit Wi-Fi disconnect warning for exclusive mode.

Script messages are in Italian.

## Warnings

- The driver experiment can crash the Wi-Fi firmware or panic the kernel. It happened here. Save your work,
  and enable EFI pstore (`efi_pstore.pstore_disable=0`) if you want the trace.
- Owly installs a root D-Bus service and a polkit rule that lets any program in your local session take the
  Wi-Fi radio without a password. Read it before you keep it.
- Never run `sudo` in a context without a TTY in a loop: three failures lock the account for 10 minutes (`pam_faillock`).

## Credits

[seemoo-lab/owl](https://github.com/seemoo-lab/owl) and [opendrop](https://github.com/seemoo-lab/opendrop),
[jedbillyb/airdrop-mt7921](https://github.com/jedbillyb/airdrop-mt7921) (iOS 26 fixes),
[1raad1/airdrop-linux](https://github.com/1raad1/airdrop-linux), [t4t5/owly](https://github.com/t4t5/owly),
[ForbiddenItlwm](https://github.com/retropineaple/ForbiddenItlwm) (the listener-context idea).

Scripts and docs: MIT. Kernel patch: GPL-2.0. Owly patch: MIT; see `patches/README.md`.
