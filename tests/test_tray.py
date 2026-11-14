"""Exercise the GTK menu with fake backends; never acquire a radio lease."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch


spec = importlib.util.spec_from_file_location(
    "airdrop_tray", Path(__file__).resolve().parents[1] / "desktop/tray.py",
)
tray = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(tray)
except (ImportError, ValueError) as error:
    raise unittest.SkipTest(f"GTK3, Ayatana and Fdrop required: {error}")
if not tray.Gtk.init_check()[0]:
    raise unittest.SkipTest("GTK display required (or xvfb-run)")


class TrayTest(unittest.TestCase):
    def setUp(self):
        # No real indicator is registered and no real CLI is spawned.
        self.cli_patch = patch.object(tray, "Cli")
        self.cli_type = self.cli_patch.start()
        self.addCleanup(self.cli_patch.stop)
        self.indicator_patch = patch.object(tray.Indicator.Indicator, "new")
        self.indicator_patch.start()
        self.addCleanup(self.indicator_patch.stop)
        self.ui = tray.Tray()
        self.ui.error = MagicMock()
        self.cli = self.ui.cli
        self.addCleanup(self.ui.menu.destroy)

    def report(self, **fields):
        state = {"receiving": False, "visible": False, "dir": "/tmp/AirDrop"}
        state.update(fields)
        self.ui.refreshed(0, json.dumps(state), "")

    def check_radio(self, report, code=0):
        with patch.object(tray.shutil, "which", return_value="/usr/bin/owly"):
            self.ui.receive("forever")
        self.cli.run.call_args.args[1](code, json.dumps(report), "")

    def test_idle_startup_never_activates_radio(self):
        self.cli.run.assert_not_called()
        self.ui.refresh()
        self.assertEqual(self.cli.run.call_args.args[0], ["status", "--json"])
        self.ui.refresh()
        self.assertEqual(self.cli.run.call_count, 1)

    def test_receiver_without_radio_is_not_shown_active(self):
        self.report(receiving=True, visible=False, reason="radio-lost")
        self.assertIn("Non visibile", self.ui.state.get_label())
        self.assertTrue(self.ui.stop.get_sensitive())
        self.report(receiving=True, visible=True, remaining=65)
        self.assertEqual(self.ui.state.get_label(), "Ricezione attiva — 1:05")
        self.report(visible=None)
        self.assertFalse(self.ui.start.get_sensitive())

    def test_exclusive_and_active_monitor_require_explicit_confirmation(self):
        for mode in ("exclusive", "active-monitor"):
            for response in (tray.Gtk.ResponseType.CANCEL, tray.Gtk.ResponseType.OK):
                self.ui.busy = self.ui.polling = False
                self.cli.reset_mock()
                with patch.object(tray.Gtk, "MessageDialog") as factory:
                    self.check_radio({"mode": mode, "missing": []})
                    self.assertEqual(self.cli.run.call_count, 1)
                    dialog = factory.return_value
                    dialog.set_default_response.assert_called_with(tray.Gtk.ResponseType.CANCEL)
                    dialog.connect.call_args.args[1](dialog, response)
                commands = [call.args[0] for call in self.cli.run.call_args_list]
                self.assertEqual(["on", "forever"] in commands, response == tray.Gtk.ResponseType.OK)

    def test_shared_reuses_backend_without_changing_audience(self):
        self.check_radio({"mode": "shared", "missing": []})
        self.assertEqual(self.cli.run.call_args.args[0], ["on", "forever"])

    def test_bad_probe_does_not_start(self):
        for report in (None, {}, {"mode": "unknown", "missing": []},
                       {"mode": "shared", "missing": ["radio"]}):
            self.ui.busy = self.ui.polling = False
            self.cli.reset_mock()
            self.check_radio(report)
            self.assertFalse(any(c.args[0][0] == "on" for c in self.cli.run.call_args_list))
            self.ui.error.assert_called()

    def test_stop_keeps_backend_transfer_protection_and_surfaces_failure(self):
        self.ui.action(["off"])
        args, done = self.cli.run.call_args.args
        self.assertEqual(args, ["off"])
        done(1, "", "Transfer in progress")
        self.ui.error.assert_called_with("Transfer in progress")


if __name__ == "__main__":
    unittest.main()
