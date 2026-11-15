"""Check startup gating with mocked commands; never acquire a radio lease."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
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
        self.coex_patch = patch.object(backend, "coex_driver", return_value=False)
        self.coex_patch.start()
        self.addCleanup(self.coex_patch.stop)

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


class CoexTest(unittest.TestCase):
    """With the coexistence driver: no Wi-Fi warning, Omdrop's settings drive Owly's receiver."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name, value in (("coex_driver", True), ("STATE", Path(self.tmp.name) / "state.json")):
            p = patch.object(backend, name, return_value=value) if name == "coex_driver" else patch.object(backend, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.env = patch.dict(backend.os.environ, {"OMDROP_CLI_REAL": "/test/omdrop"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.execute = patch.object(backend.os, "execv").start()
        self.addCleanup(patch.stopall)
        self.calls = []
        self.settings = {"receiving": False, "visible": False, "name": "ThinkPad", "dir": "/tmp/dl",
                         "visibility": "everyone", "mode": "off"}
        self.active = False
        self.radio = False

        def run(cmd, **kwargs):
            self.calls.append(cmd)
            if cmd[:2] == ["/test/omdrop", "status"]:
                return subprocess.CompletedProcess(cmd, 0, json.dumps(self.settings))
            if cmd[-1] == "status":
                return subprocess.CompletedProcess(cmd, 0, '{"visible":true,"reason":"ok"}')
            if cmd[:3] == ["systemctl", "--user", "is-active"]:
                return subprocess.CompletedProcess(cmd, 0 if self.active else 3)
            if cmd[:2] == ["systemctl", "is-active"]:
                return subprocess.CompletedProcess(cmd, 0 if self.radio else 3)
            return subprocess.CompletedProcess(cmd, 0)
        patch.object(backend.subprocess, "run", side_effect=run).start()

    def test_start_uses_settings_without_wifi_warning(self):
        self.assertEqual(backend.run(["toggle", "5m"]), 0)
        flat = [" ".join(map(str, c)) for c in self.calls]
        self.assertTrue(any(c.startswith("pkexec") and c.endswith("coex-session start") for c in flat))
        self.assertIn("systemctl --user start omdrop-coex-receive", flat)
        self.assertTrue(any("--on-active=5m" in c for c in flat))
        self.assertEqual(json.loads(backend.STATE.read_text())["mode"], "timed")
        self.assertFalse(any("zenity" in c for c in flat))
        self.execute.assert_not_called()

    def test_contacts_only_is_refused_before_radio(self):
        self.settings["visibility"] = "contacts"
        with self.assertRaises(ValueError):
            backend.run(["on", "forever"])
        self.assertFalse(any(c[0] == "pkexec" for c in self.calls))

    def test_status_reports_coex_and_keeps_settings(self):
        self.active = True
        backend.STATE.write_text(json.dumps({"mode": "forever", "deadline": None}))
        with patch("builtins.print") as out:
            backend.run(["status", "--json"])
        status = json.loads(out.call_args.args[0])
        self.assertEqual((status["receiving"], status["visible"], status["coex"]), (True, True, True))
        self.assertEqual((status["mode"], status["name"], status["dir"]), ("forever", "ThinkPad", "/tmp/dl"))

    def test_toggle_while_receiving_stops_both_sides(self):
        self.active = True
        backend.run(["toggle", "10m"])
        flat = [" ".join(map(str, c)) for c in self.calls]
        self.assertTrue(any("stop omdrop-coex-receive" in c for c in flat))
        self.assertTrue(any(c.startswith("pkexec") and c.endswith("coex-session stop") for c in flat))

    def test_reschedule_keeps_radio_up_without_password(self):
        self.active = self.radio = True
        backend.run(["on", "forever"])
        flat = [" ".join(map(str, c)) for c in self.calls]
        self.assertFalse(any(c.startswith("pkexec") for c in flat))
        self.assertLess(flat.index("systemctl --user stop omdrop-coex-receive"),
                        flat.index("systemctl --user start omdrop-coex-receive"))
        self.assertEqual(json.loads(backend.STATE.read_text())["mode"], "forever")

    def test_rename_restarts_running_receiver(self):
        self.active = True
        backend.run(["name", "Portatile"])
        flat = [" ".join(map(str, c)) for c in self.calls]
        self.assertIn("/test/omdrop name Portatile", flat)
        self.assertIn("systemctl --user restart omdrop-coex-receive", flat)

    def test_peers_never_reach_the_exclusive_backend(self):
        with patch("builtins.print") as out:
            self.assertEqual(backend.run(["peers", "--json"]), 0)
            self.assertEqual(backend.run(["peers", "--json", "-n", "--stream"]), 0)
        out.assert_called_once_with("[]")
        self.execute.assert_not_called()
        self.assertFalse(any(c[0] == "pkexec" for c in self.calls))

    def test_other_commands_still_go_to_omdrop(self):
        backend.run(["senders", "list", "--json"])
        self.execute.assert_called_once_with("/test/omdrop", ["/test/omdrop", "senders", "list", "--json"])


class ConsentTest(unittest.TestCase):
    """coex-receive.py answers owly's prompt from a GNOME notification (Sì / No)."""

    def run_receiver(self, zenity_rc):
        with tempfile.TemporaryDirectory() as d:
            owly = Path(d) / "owly"
            owly.write_text("""#!/bin/bash
echo 'receiving as "x"' >&2
echo '"iPhone" ("iPhone") wants to send:' >&2
echo '  "IMG.jpg" public.jpeg 10 bytes' >&2
printf 'accept? [y/N] ' >&2
read -r answer
echo "answer=$answer" >&2
[[ $answer == y ]] && echo "$DIR/IMG.jpg"
""")
            owly.chmod(0o755)
            answer = "yes" if zenity_rc == 0 else "no"
            notify = f'case "$*" in *vuole\\ inviare*) echo "$@" > "{d}/asked"; echo 42; echo {answer};; esac'
            for tool, body in (("notify-send", notify),):
                (Path(d) / tool).write_text(f"#!/bin/bash\n{body}\n")
                (Path(d) / tool).chmod(0o755)
            result = subprocess.run(
                ["python3", str(Path(__file__).resolve().parents[1] / "desktop/coex-receive.py"),
                 "--dir", d, "--name", "x", "--once"],
                env={"PATH": f"{d}:/usr/bin:/bin", "OWLY": str(owly), "DIR": d},
                capture_output=True, text=True, timeout=10,
            )
            return result, (Path(d) / "asked").read_text()

    def test_accept_and_decline(self):
        result, asked = self.run_receiver(0)
        self.assertIn("answer=y", result.stdout)
        self.assertIn("IMG.jpg", asked)
        self.assertIn("--urgency=critical", asked)
        self.assertIn("--action=yes=Sì", asked)
        result, _ = self.run_receiver(1)
        self.assertIn("answer=n", result.stdout)


if __name__ == "__main__":
    unittest.main()
