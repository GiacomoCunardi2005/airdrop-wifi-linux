"""Check startup gating with mocked commands; never acquire a radio lease."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "omdrop_gnome", Path(__file__).resolve().parents[1] / "desktop/omdrop.py",
)
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class StartupTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(backend.os.environ, {"OMDROP_CLI_REAL": "/test/omdrop"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.exec_patch = patch.object(backend.os, "execv")
        self.execute = self.exec_patch.start()
        self.addCleanup(self.exec_patch.stop)
        self.run_patch = patch.object(backend.subprocess, "run")
        self.run = self.run_patch.start()
        self.addCleanup(self.run_patch.stop)
        self.which_patch = patch.object(backend.shutil, "which", return_value="/test/owly")
        self.which_patch.start()
        self.addCleanup(self.which_patch.stop)

    def answers(self, *, receiving=False, visible=False, mode="shared", consent=0):
        self.run.side_effect = [
            subprocess.CompletedProcess([], 0, json.dumps({"receiving": receiving, "visible": visible})),
            subprocess.CompletedProcess([], 0, json.dumps({"mode": mode, "missing": []})),
            subprocess.CompletedProcess([], consent),
        ]

    def test_status_does_not_probe_or_start_radio(self):
        backend.run(["status", "--json"])
        self.run.assert_not_called()
        self.execute.assert_called_once_with("/test/omdrop", ["/test/omdrop", "status", "--json"])

    def test_exclusive_requires_consent_and_preserves_arguments(self):
        self.answers(mode="exclusive")
        backend.run(["on", "-c", "5m"])
        self.assertIn("--default-cancel", self.run.call_args.args[0])
        self.execute.assert_called_once_with("/test/omdrop", ["/test/omdrop", "on", "-c", "5m"])

    def test_cancel_never_starts_radio(self):
        self.answers(mode="active-monitor", consent=1)
        self.assertEqual(backend.run(["send", "phone", "photo.jpg"]), 1)
        self.execute.assert_not_called()

    def test_failed_probe_never_starts(self):
        self.run.side_effect = subprocess.TimeoutExpired(["omdrop"], 10)
        with self.assertRaises(subprocess.TimeoutExpired):
            backend.run(["on", "forever"])
        self.execute.assert_not_called()

    def test_invalid_probe_never_starts(self):
        for report in (None, {}, {"mode": "exclusive"}, {"mode": "unknown", "missing": []}):
            self.run.side_effect = [
                subprocess.CompletedProcess([], 0, '{"receiving":false}'),
                subprocess.CompletedProcess([], 0, json.dumps(report)),
            ]
            with self.assertRaises(ValueError):
                backend.run(["on", "forever"])
        self.execute.assert_not_called()

    def test_stopping_needs_no_wifi_confirmation(self):
        self.answers(receiving=True)
        backend.run(["toggle", "10m"])
        self.assertEqual(self.run.call_count, 1)
        self.execute.assert_called_once()

    def test_shared_start_and_live_reschedule_need_no_confirmation(self):
        self.answers()
        backend.run(["on", "5m"])
        self.assertEqual(self.run.call_count, 2)
        self.run.reset_mock()
        self.answers(receiving=True, visible=True)
        backend.run(["on", "forever"])
        self.assertEqual(self.run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
