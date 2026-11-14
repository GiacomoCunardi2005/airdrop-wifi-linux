#!/usr/bin/python3
"""GNOME indicator for Owly/Omdrop, reusing Fdrop's CLI and status model."""
import json
from pathlib import Path
import shutil
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3 as Indicator, Gio, GLib, Gtk

# Fdrop's source install and distro package locations.
for source in (Path.home() / ".local/share/fdrop/src", Path("/usr/share/fdrop")):
    if (source / "fdrop/cli.py").is_file():
        sys.path.insert(0, str(source))
        break
from fdrop.cli import Cli
from fdrop.model import Status, parse_status


class Tray:
    def __init__(self):
        self.cli = Cli()
        self.status = Status()
        self.busy = False
        self.polling = False
        self.indicator = Indicator.Indicator.new(
            "omdrop", "folder-download-symbolic",
            Indicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_title("AirDrop — Owly")
        self.menu = Gtk.Menu()
        self.state = self.item("Controllo AirDrop…")
        self.state.set_sensitive(False)
        self.start = self.item("Ricevi per 5 minuti…", lambda _: self.receive("5m"))
        self.forever = self.item("Ricevi fino allo spegnimento…", lambda _: self.receive("forever"))
        self.stop = self.item("Ferma AirDrop", lambda _: self.action(["off"]))
        self.item("Apri interfaccia / invia file…", self.open_app)
        self.folder = self.item("Apri cartella ricevuti", self.open_folder)
        self.menu.show_all()
        self.indicator.set_menu(self.menu)
        self.indicator.set_status(Indicator.IndicatorStatus.ACTIVE)
        self.render()

    def item(self, label, callback=None):
        item = Gtk.MenuItem(label=label)
        if callback:
            item.connect("activate", callback)
        self.menu.append(item)
        return item

    def error(self, text):
        dialog = Gtk.MessageDialog(
            message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.CLOSE,
            text="AirDrop", secondary_text=text,
        )
        dialog.connect("response", lambda widget, _: widget.destroy())
        dialog.show()

    def render(self):
        s = self.status
        if self.busy:
            label = "Operazione in corso…"
        elif not s.usable:
            label = "AirDrop non disponibile"
        elif s.receiving and s.visible:
            label = "Ricezione attiva"
            if s.remaining is not None:
                label += f" — {s.remaining // 60}:{s.remaining % 60:02d}"
        elif s.receiving:
            label = "Non visibile — radio non disponibile"
        elif s.visible:
            label = "Radio attiva — ricevitore spento"
        else:
            label = "AirDrop spento"
        self.state.set_label(label)
        icon = "network-transmit-receive-symbolic" if s.receiving and s.visible else "folder-download-symbolic"
        self.indicator.set_icon_full(icon, label)
        for item in (self.start, self.forever):
            item.set_sensitive(s.usable and not self.busy and not self.polling)
        self.stop.set_sensitive(self.cli.available and not self.busy and not self.polling)
        self.folder.set_sensitive(bool(s.dir))

    def refresh(self):
        if not self.busy and not self.polling:
            self.polling = True
            self.render()
            self.cli.run(["status", "--json"], self.refreshed)
        return True

    def refreshed(self, code, out, err):
        self.polling = False
        self.status = parse_status(out) if code == 0 else Status()
        self.render()

    def receive(self, duration):
        if self.busy or self.polling:
            return
        self.busy = True
        self.render()
        owly = shutil.which("owly")
        if not owly:
            self.finished(1, "", "Owly non installato.")
            return

        def checked(code, out, err):
            try:
                report = json.loads(out)
                mode = report["mode"]
                if code or mode not in ("shared", "exclusive", "active-monitor") or report["missing"]:
                    raise ValueError("Radio non pronta")
            except (ValueError, KeyError, TypeError):
                self.finished(1, "", err or out or "Impossibile verificare la radio.")
                return
            if mode == "shared":
                self.cli.run(["on", duration], self.finished)
                return
            dialog = Gtk.MessageDialog(
                message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK_CANCEL,
                text="AirDrop scollega il Wi-Fi",
                secondary_text="Questa modalità occupa la scheda Wi-Fi. Internet su questa scheda "
                "resterà scollegato durante la ricezione. Continuare?",
            )
            dialog.set_default_response(Gtk.ResponseType.CANCEL)

            def answered(widget, response):
                widget.destroy()
                if response == Gtk.ResponseType.OK:
                    self.cli.run(["on", duration], self.finished)
                else:
                    self.finished(0, "", "")

            dialog.connect("response", answered)
            dialog.show()

        Cli(path="/usr/bin/timeout").run(["10", owly, "doctor", "--json"], checked)

    def action(self, args):
        if self.busy or self.polling:
            return
        self.busy = True
        self.render()
        self.cli.run(args, self.finished)

    def finished(self, code, out, err):
        self.busy = False
        if code:
            self.error(err or out or "Operazione non riuscita.")
        self.refresh()

    def open_app(self, _item):
        app = Gio.DesktopAppInfo.new("io.github.konstiu.Fdrop.desktop")
        try:
            if app is None:
                raise RuntimeError("Installare Fdrop per aprire l'interfaccia.")
            app.launch([], None)
        except (GLib.Error, RuntimeError) as error:
            self.error(str(error))

    def open_folder(self, _item):
        try:
            Gio.AppInfo.launch_default_for_uri(Path(self.status.dir).as_uri(), None)
        except (GLib.Error, ValueError) as error:
            self.error(str(error))


if __name__ == "__main__":
    tray = Tray()
    tray.refresh()
    GLib.timeout_add_seconds(5, tray.refresh)
    Gtk.main()
