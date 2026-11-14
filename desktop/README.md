# GNOME tray for Owly / Omdrop

The Omarchy panel uses Quickshell-specific QML components. This small GTK3
indicator reuses the same `omdrop` commands, plus the installed Fdrop CLI runner
and status model. It does not implement AirDrop or replace the receiver.

Requirements: Owly, configured Omdrop and Fdrop, Python GObject bindings, GTK3,
AyatanaAppIndicator3, GNU timeout, and GNOME's
[AppIndicator extension](https://github.com/ubuntu/gnome-shell-extension-appindicator).
Fdrop's Python modules must be installed in `~/.local/share/fdrop/src`,
`/usr/share/fdrop`, or on Python's module path. This is tested with Fdrop 0.2.0,
Owly 0.4.3 and the Omdrop Python fallback on the lab machine.

From the repository root, install as your desktop user (no sudo):

```bash
install -Dm644 desktop/tray.py ~/.local/share/omdrop-tray/tray.py
install -Dm644 desktop/omdrop-tray.service ~/.config/systemd/user/omdrop-tray.service
systemctl --user daemon-reload
systemctl --user enable --now omdrop-tray.service
systemctl --user restart omdrop-tray.service
```

If replacing an existing `omdrop-tray` installation, back up those two files first.
Uninstall the indicator with `systemctl --user disable --now omdrop-tray.service`.
That stops only the indicator; use **Ferma AirDrop** to end a receive session.

The menu provides status, five-minute or continuous reception, stop, the full
Fdrop interface for sending/settings, and the configured download directory.
Opening the indicator or logging in only reads status; it never starts the radio.
Continuous reception lasts until Omdrop stops it; it is not automatically resumed
after a reboot or radio failure. Receive visibility and transfer acceptance remain
Omdrop's existing policy. The stop action preserves Omdrop's in-flight send check.

Before starting, the indicator reads `owly doctor --json`. A missing/failed report
blocks startup. Exclusive and active-monitor modes require an explicit confirmation
that Wi-Fi will disconnect; Cancel is the default. On this AX211 that warning applies.
The Fdrop window retains its own controls; this check covers the tray's start actions.

**An always-visible tray is not always-on AirDrop with Internet.** The latter remains
unproven on this card. A running receiver without a visible radio is shown as unavailable,
not as successful reception. Existing successful transfers used `owly receive` directly;
the Omdrop receive path launched by this tray still needs an end-to-end phone test.

Validation in a graphical session (backend calls mocked, radio untouched):

```bash
/usr/bin/python3 -B -m unittest discover -s tests -v
```

The tray tests skip when GTK, Ayatana, Fdrop or a display is missing. Headless GTK
tests can use `xvfb-run`. See [Fdrop](https://github.com/konstiu/fdrop),
[Omdrop](https://github.com/netmojo-systems/omdrop-plugin) and
[Owly](https://github.com/t4t5/owly) for the reused components.
