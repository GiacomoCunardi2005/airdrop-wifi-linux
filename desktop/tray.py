#!/usr/bin/python3
"""GNOME indicator opening the original Omdrop QML panel shown by Owly."""
from pathlib import Path
import signal
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3 as Indicator, Gio, GLib, Gtk


class Tray:
    def __init__(self):
        self.directory = Path(__file__).resolve().parent
        self.panel = Gio.Subprocess.new([str(self.directory / "panel")], Gio.SubprocessFlags.NONE)
        self.panel.wait_async(None, self.panel_exited)
        self.indicator = Indicator.Indicator.new(
            "omdrop", str(self.directory / "omdrop-symbolic.svg"),
            Indicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_title("AirDrop — Owly / Omdrop")
        self.menu = Gtk.Menu()
        self.item = Gtk.MenuItem(label="Apri AirDrop…")
        self.item.connect("activate", self.open_panel)
        self.menu.append(self.item)
        self.menu.show_all()
        self.indicator.set_menu(self.menu)
        self.indicator.set_secondary_activate_target(self.item)
        self.indicator.set_status(Indicator.IndicatorStatus.ACTIVE)

    def error(self, text):
        dialog = Gtk.MessageDialog(
            message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.CLOSE,
            text="AirDrop", secondary_text=text,
        )
        dialog.connect("response", lambda widget, _: widget.destroy())
        dialog.show()

    def panel_exited(self, proc, result):
        proc.wait_finish(result)
        # Let systemd restart the entire UI if its QML host exits.
        sys.exit(1)

    def open_panel(self, _item):
        proc = Gio.Subprocess.new(
            [str(self.directory / "panel"), "--show"],
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
        )

        def finished(process, result):
            try:
                _, out, err = process.communicate_utf8_finish(result)
                if not process.get_successful():
                    self.error(err or out or "Impossibile aprire il pannello AirDrop.")
            except GLib.Error as error:
                self.error(str(error))

        proc.communicate_utf8_async(None, None, finished)


if __name__ == "__main__":
    tray = Tray()
    for signum in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, lambda: Gtk.main_quit())
    try:
        Gtk.main()
    finally:
        tray.panel.send_signal(signal.SIGTERM)
