# airdrop-wifi-linux

Goal: make AirDrop from an iPhone to a Linux PC **easy**, using the Wi-Fi card the PC already has,
and without losing the Internet connection while it runs.

This repo is a lab notebook plus the scripts and patches that came out of it. Every new finding is committed.
Tested so far on one machine only: Intel AX211 (Meteor Lake CNVi, PCI `8086:7e40`, `iwlwifi`/`iwlmvm`,
firmware 89), CachyOS, kernel 7.3.4, iPhone 16 Pro on iOS 27.

## Status

| What | Status |
|---|---|
| Radio hears AWDL **while the station stays connected** to the router | **Works** with the experimental driver patch: 40/40 pings to the gateway, 46 AWDL frames in 20 s |
| Receive a file **while Wi-Fi stays connected** | **Works, always on**: patched driver via DKMS plus `desktop/install-coex`. AirDrop is on from boot until turned off in the tray, consent as a GNOME notification; received across a reboot with no Wi-Fi disconnect. Gateway latency rises while the AWDL engine shares the radio |
| Send PC → iPhone, large files, long-term stability | Not tested |
| Original Owly demo panel on GNOME | Available in [desktop/](desktop/README.md); shows "Wi-Fi + AirDrop insieme" with the patched driver |

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

**Other Wi-Fi chips:** [docs/PORTING.md](docs/PORTING.md) explains, for humans and AI agents, what a driver
must provide; the rest of this repository works unchanged with any driver that meets it.

## What is in here

- `packaging/arch/` — the pacman package `airdrop-wifi-coex` (install section above).
- `dkms/` — the patched `iwlwifi` source (GPL-2.0) and its `dkms.conf`; `patches/` has the same change as a diff.
- `owly/` — the Owly patch and the `coex-radio` adapter the package builds (MIT).
- `desktop/` — services, the root helper `coex-session`, the receiver with GNOME consent, the suspend hook,
  and the original Omdrop panel hosted on GNOME (`desktop/README.md`).
- `scripts/awdl-coex-test` — lab test for driver work: loads a patched driver for one run, puts a monitor
  next to the connected station, measures ping and AWDL frames, `AIRDROP=owly` also receives; restores the
  stock modules afterwards (rollback timer included). Used by the porting test protocol.
- `docs/` — [FINDINGS.md](docs/FINDINGS.md) (what was measured, including dead ends) and
  [PORTING.md](docs/PORTING.md) (other Wi-Fi chips).

Script messages are in Italian.

## Warnings

- The driver experiment can crash the Wi-Fi firmware or panic the kernel. It happened here. Save your work,
  and enable EFI pstore (`efi_pstore.pstore_disable=0`) if you want the trace.
- This package doesn't install Owly's own daemon. The tray's exclusive fallback (stock driver) uses a full
  Owly install, which adds a root D-Bus service and a polkit rule letting any program in your local session
  take the Wi-Fi radio without a password. Read it before you keep it.
- Never run `sudo` in a context without a TTY in a loop: three failures lock the account for 10 minutes (`pam_faillock`).

## Credits

[seemoo-lab/owl](https://github.com/seemoo-lab/owl) and [opendrop](https://github.com/seemoo-lab/opendrop),
[jedbillyb/airdrop-mt7921](https://github.com/jedbillyb/airdrop-mt7921) (iOS 26 fixes),
[1raad1/airdrop-linux](https://github.com/1raad1/airdrop-linux), [t4t5/owly](https://github.com/t4t5/owly),
[ForbiddenItlwm](https://github.com/retropineaple/ForbiddenItlwm) (the listener-context idea).

Scripts and docs: MIT. Kernel patch: GPL-2.0. Owly patch and adapter: MIT; see `owly/README.md`.
