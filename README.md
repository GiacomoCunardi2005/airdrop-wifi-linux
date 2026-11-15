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
| Receive a file **while Wi-Fi stays connected** | **Works, always on**: patched driver via DKMS plus `desktop/install-coex`. AirDrop is on from boot until turned off in the tray, consent as a GNOME notification; received across a reboot with no Wi-Fi disconnect. Gateway latency rises while the AWDL engine shares the radio |
| Send PC → iPhone, large files, long-term stability | Not tested |
| Original Owly demo panel on GNOME | Available in [desktop/](desktop/README.md); simultaneous Wi-Fi remains unproven |

## Install on a PC like this one

ThinkPad-class laptop with the **Intel AX211 (PCI `8086:7e40`)**, CachyOS with a **7.3.x** kernel, GNOME:

```bash
git clone https://github.com/GiacomoCunardi2005/airdrop-wifi-linux.git
cd airdrop-wifi-linux/packaging/arch
makepkg -si
sudo reboot
```

The package `airdrop-wifi-coex` builds the patched `iwlwifi` through DKMS (rebuilt for every 7.3.x kernel
update), Owly's AWDL engine and receiver, and enables the services: after the reboot AirDrop is on, visible
as the computer's host name, and the Wi-Fi stays connected. Files go to `~/Downloads`; each offer appears as
a GNOME notification with **Sì / No**. Turn it off until the next boot with
`systemctl --user stop omdrop-coex-receive`. Uninstall with `sudo pacman -R airdrop-wifi-coex` and reboot.

With an Omdrop panel already set up (`desktop/README.md`), `desktop/install-coex` does the same and also
updates the tray, without a reboot. Other Wi-Fi cards or kernel series: the stock driver loads and nothing
changes; see Warnings before trying.

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
- `desktop/` — the original Omdrop panel shown in Owly's demo, hosted on GNOME;
  receive/stop controls, duration, contacts, peer radar, sending and settings.

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
