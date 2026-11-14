"""Exercise recovery with shell mocks; never touch the radio or run sudo."""
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = (Path(__file__).resolve().parents[1] / "scripts/awdl-coex-test").read_text()
RESTORE = SCRIPT[SCRIPT.index("restore() {"):SCRIPT.index("sudo -v || exit 1")]
MOCKS = r'''
set -uo pipefail
WLAN=testwifi OUT=/unused STAMP=test
sudo() {
    printf '%s\n' "$*" >> "$CALLS"
    case "$*" in
        'rmmod iwlmvm iwlwifi') return "${MODULE_FAIL:-0}" ;;
        'nmcli --wait 30 device connect testwifi') return "${CONNECT_FAIL:-0}" ;;
    esac
    return 0
}
kill() { printf 'kill %s\n' "$*" >> "$CALLS"; }
sleep() { printf 'sleep\n' >> "$CALLS"; }
ip() {
    printf 'ip %s\n' "$*" >> "$CALLS"
    (( ++attempts >= 3 ))
}
nmcli() { echo 'testwifi:connected'; }
attempts=0
'''


class CleanupTest(unittest.TestCase):
    def run_restore(self, settings=""):
        with tempfile.TemporaryDirectory() as directory:
            calls = Path(directory) / "calls"
            result = subprocess.run(
                ["bash", "-c", MOCKS + settings + "\n" + RESTORE + "\nrestore"],
                env={"PATH": "/usr/bin:/bin", "CALLS": str(calls)},
                text=True, capture_output=True, timeout=5,
            )
            return result, calls.read_text().splitlines()

    def test_missing_pids_and_delayed_interface(self):
        result, calls = self.run_restore()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(line.startswith("kill ") for line in calls))
        self.assertEqual(calls.count("ip link show testwifi"), 3)
        self.assertLess(calls.index("sleep"), calls.index("nmcli --wait 30 device connect testwifi"))
        self.assertIn("nmcli device set testwifi managed yes", calls)
        self.assertIn("systemctl stop awdl-coex-rollback.timer", calls)

    def test_stops_only_recorded_background_processes(self):
        result, calls = self.run_restore("CAP=101 MONCAP=102 PINGPID=103 KMSG=104 KSYNC=105")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([line for line in calls if line.startswith("kill ")],
                         [f"kill {pid}" for pid in range(101, 106)])

    def test_recovery_failures_keep_timer_and_report_failure(self):
        for failure in ("CONNECT_FAIL=1", "MODULE_FAIL=1"):
            with self.subTest(failure=failure):
                result, calls = self.run_restore(failure)
                self.assertEqual(result.returncode, 1)
                self.assertIn("Ripristino incompleto", result.stdout)
                self.assertNotIn("systemctl stop awdl-coex-rollback.timer", calls)

    def test_timer_failure_aborts_before_touching_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "awdl-diag").mkdir()
            mocks = r'''
sudo() {
    printf '%s\n' "$*" >> "$CALLS"
    [[ $1 != systemd-run ]]
}
modinfo() { echo test-vermagic; }
ip() { echo 'default via gateway dev testwifi'; }
iw() { :; }
'''
            calls = Path(directory) / "calls"
            result = subprocess.run(
                ["bash", "-c", mocks + SCRIPT],
                env={"PATH": "/usr/bin:/bin", "HOME": directory, "CALLS": str(calls)},
                text=True, capture_output=True, timeout=5,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("Timer di emergenza non attivato", result.stdout)
            self.assertEqual(len(calls.read_text().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
