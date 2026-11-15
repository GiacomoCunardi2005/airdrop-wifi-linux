# airdrop-wifi-linux

Receive AirDrop from an iPhone on a Linux laptop, with the laptop's own Wi-Fi card, **while the Wi-Fi stays
connected to your network**. No extra adapter, no dongle. AirDrop is on from boot until you turn it off.

It works on one kind of machine so far: the **Intel AX211** Wi-Fi card (PCI `8086:7e40`, found in Intel
Meteor Lake laptops such as the ThinkPad E16 Gen 2) running **CachyOS** with a **7.3.x** kernel and GNOME.
Other cards: see [Other Wi-Fi cards](#other-wi-fi-cards).

## Does it work?

Verified on the test machine (kernel 7.3.4, firmware 89, iPhone 16 Pro on iOS 27), November 2026:

| | |
|---|---|
| Receive photos while connected to the router | ✅ Several photos received intact; no Wi-Fi disconnects during transfers |
| On at boot, without touching anything | ✅ After a reboot, a photo arrived with zero Wi-Fi disconnects since boot |
| Survives kernel updates | ✅ for 7.3.x: DKMS rebuilds the driver. A 7.4 kernel falls back to the stock driver |
| Suspend and resume with AirDrop on | ⚠️ A hook handles it; a full suspend → resume → receive cycle isn't verified yet |
| Sending from the PC to the iPhone, very large files | ❌ Not available / not tested |
| "Contacts Only" | ❌ Receives from **Everyone** only |

While AirDrop is on, the Wi-Fi card shares its time between your network and AirDrop: latency to the router
goes from a few ms to about 20 ms, and to about 250 ms during a transfer. Normal browsing is fine.

## Install

```bash
git clone https://github.com/GiacomoCunardi2005/airdrop-wifi-linux.git
cd airdrop-wifi-linux/packaging/arch
makepkg -si
sudo reboot
```

`makepkg -si` builds the package `airdrop-wifi-coex` and installs it with its dependencies (`dkms`, clang,
the CachyOS kernel headers, Rust to build Owly). It takes a few minutes. Installing it:

- puts the patched Wi-Fi driver under DKMS, which builds it now and after every kernel update;
- installs Owly's AWDL engine and receiver;
- enables the services, so after the reboot AirDrop is already on.

Before the reboot, save your work: the patched driver loads for the first time then.

## Use

On the iPhone: Control Center → AirDrop → **Everyone for 10 Minutes**. Then Share → AirDrop and pick the
laptop. It shows up under its host name.

On the laptop, a notification asks **"AirDrop: … vuole inviare"** with **Sì** / **No**. If you don't answer
within 13 seconds, the offer is declined. Accepted files go to `~/Downloads`.

| To | Run |
|---|---|
| Turn AirDrop off until the next boot | `systemctl --user stop omdrop-coex-receive` |
| Turn it back on | `systemctl --user start omdrop-coex-receive` |
| Never start it at login | `systemctl --user disable omdrop-coex-receive` |
| See what the receiver is doing | `journalctl --user -u omdrop-coex-receive -f` |
| See the radio | `journalctl -u awdl-coex-radio -f` |

If you use the GNOME tray panel from Owly's demo ([desktop/README.md](desktop/README.md)), it does the same
with buttons and also sets the name, the folder and a time limit. Install it with `desktop/install-coex`.

## How it works

AirDrop moves files over **AWDL**, Apple's peer-to-peer Wi-Fi link, here on channel 6. Linux has no AWDL,
so [Owly](https://github.com/t4t5/owly) implements it in user space through a Wi-Fi interface in monitor
mode. The hard part is doing that on the same card that's connected to your router:

- **A second listener on another channel.** The patched `iwlwifi` lets a monitor interface (`awdlmon`) live
  on channel 6 next to the connected station on the router's channel, and the firmware switches between
  them.
- **Its own address, so the card sends ACKs.** The monitor gets its own MAC address, which the card
  acknowledges in hardware. Without these ACKs the iPhone resends every frame and never lists the laptop.
  This was the missing piece.
- **Set up before the Wi-Fi connects.** Linux only lets a monitor change channel while nothing else uses the
  card, so `awdl-coex-boot.service` prepares `awdlmon` at boot, before NetworkManager connects.
- **Off during suspend.** A monitor left up across suspend broke Wi-Fi until the driver was reloaded, so
  a sleep hook removes it before suspend and restores it after.

[docs/FINDINGS.md](docs/FINDINGS.md) records every measurement in order, including the dead ends.

## If something goes wrong

**Wi-Fi doesn't connect.** Turning the radio off and on isn't enough. Reboot. If it keeps happening, remove the
package (below) to get the stock driver back, and open an issue with `journalctl -b | grep -E 'iwlwifi|wlan0'`.
Ethernet keeps working meanwhile.

**The laptop doesn't appear on the iPhone.** Check that the iPhone is set to *Everyone for 10 Minutes*,
that `systemctl is-active awdl-coex-radio` says `active`, and that `cat /sys/module/iwlwifi/parameters/awdl_coex`
says `Y`. If it says `N` or the file is missing, the stock driver is loaded. That's normal right after
installing without a reboot, or on a kernel other than 7.3.x (`dkms status` shows it).

**Secure Boot.** DKMS signs the module with its own key (`/var/lib/dkms/mok.pub`). If Secure Boot enforces
signatures, enroll that key with `mokutil --import` or the driver won't load.

## Uninstall

```bash
sudo pacman -R airdrop-wifi-coex
sudo reboot
```

The stock Wi-Fi driver comes back after the reboot.

## Other Wi-Fi cards

Everything except the kernel driver is independent of the card: user space looks for any driver that exposes
an `awdl_coex` module parameter. [docs/PORTING.md](docs/PORTING.md) explains, for people and AI agents,
what a driver has to provide, how the iwlwifi change does it, and how to test a port step by step. Driver
experiments can crash the Wi-Fi firmware or the kernel: read it before trying.

## What's in this repository

| Path | Contents |
|---|---|
| `packaging/arch/` | The pacman package (`PKGBUILD`, install script) |
| `dkms/` | Patched `iwlwifi` source (GPL-2.0) and `dkms.conf`; the same change as a diff in `patches/` |
| `owly/` | The Owly patch and the `coex-radio` adapter the package builds (MIT) |
| `desktop/` | Services, the root helper `coex-session`, the receiver with GNOME consent, the sleep hook, the optional tray panel |
| `scripts/awdl-coex-test` | Lab test for driver work: one bounded run with automatic rollback |
| `tests/` | `python3 -B -m unittest discover -s tests` (mocked; never touches the radio or runs `sudo`) |
| `docs/` | [FINDINGS.md](docs/FINDINGS.md) and [PORTING.md](docs/PORTING.md) |

Script messages are in Italian; code and docs are in English.

## Credits and licenses

Built on [t4t5/owly](https://github.com/t4t5/owly) (AWDL and AirDrop in Rust). The listener-context idea
comes from [ForbiddenItlwm](https://github.com/retropineaple/ForbiddenItlwm). Earlier work that showed the
way: [seemoo-lab/owl](https://github.com/seemoo-lab/owl), [opendrop](https://github.com/seemoo-lab/opendrop),
[jedbillyb/airdrop-mt7921](https://github.com/jedbillyb/airdrop-mt7921) and
[1raad1/airdrop-linux](https://github.com/1raad1/airdrop-linux).

Scripts and documentation: MIT ([LICENSE](LICENSE)). Driver code in `dkms/` and `patches/`: GPL-2.0, as part
of the Linux kernel. Owly changes in `owly/`: MIT, see [owly/README.md](owly/README.md).
