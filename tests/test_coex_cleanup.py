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
wait() { printf 'wait %s\n' "$*" >> "$CALLS"; }
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
        result, calls = self.run_restore("CAP=101 MONCAP=102 PINGPID=103 NETPID=104 KMSG=105 KSYNC=106 RADIOPID=107")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([line for line in calls if line.startswith("kill ")],
                         ["kill 107"] + [f"kill {pid}" for pid in range(101, 107)])
        self.assertLess(calls.index("wait 107"), calls.index("rmmod iwlmvm iwlwifi"))

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
ip() {
    [[ $* == 'link show awdl0' ]] && return 1
    echo 'default via gateway dev testwifi'
}
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

    def test_owly_receive_path_keeps_confirmation_and_measures_internet(self):
        receive = SCRIPT[SCRIPT.index('if [[ ${AIRDROP:-0} != 0 ]]; then'):]
        with tempfile.TemporaryDirectory() as directory:
            calls = Path(directory) / "calls"
            mocks = r'''
set -u
OUT=$HOME STAMP=test AIRDROP=owly WLAN=testwifi GW=gateway
OWLY=/test/owly COEX_RADIO=/test/coex-radio
sudo() { printf 'sudo %s\n' "$*" >> "$CALLS"; }
ip() { echo 'inet6 fe80::1/64 scope link'; }
ping() { printf 'ping %s\n' "$*" >> "$CALLS"; }
tshark() { printf 'tshark %s\n' "$*" >> "$CALLS"; }
timeout() { printf 'timeout %s\n' "$*" >> "$CALLS"; echo 'wants to send:'; }
kill() { :; }
wait() { :; }
hostname() { echo testhost; }
xdg-user-dir() { echo "$HOME"; }
'''
            result = subprocess.run(
                ["bash", "-c", mocks + receive],
                env={"PATH": "/usr/bin:/bin", "HOME": directory, "CALLS": str(calls)},
                text=True, capture_output=True, timeout=5,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            recorded = calls.read_text()
            self.assertIn("sudo /test/coex-radio", recorded)
            self.assertIn("/test/owly receive --fixed-channel --dir", recorded)
            self.assertNotIn("--accept", recorded)
            self.assertNotIn("opendrop", recorded)
            self.assertIn("ping -I testwifi -i 1 -c 170 -q one.one.one.one", recorded)
            self.assertIn("tshark -i awdlmon", recorded)
            self.assertIn("offerte AirDrop: 1", result.stdout)


if __name__ == "__main__":
    unittest.main()
