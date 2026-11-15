#!/usr/bin/python3
"""Forward the original panel's commands, checking Wi-Fi impact before startup.

With the coexistence driver loaded (iwlwifi awdl_coex=1) receiving runs next to the connected
station instead: coex-session (root, via pkexec) brings up the AWDL radio, coex-receive.py runs
Owly's receiver. Settings (name, folder, audience, sound) still come from Omdrop.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
COEX_PARAM = Path("/sys/module/iwlwifi/parameters/awdl_coex")
COEX_SESSION = os.environ.get("OMDROP_COEX_SESSION", "/usr/local/lib/awdl-coex/coex-session")
RECEIVE_UNIT = "omdrop-coex-receive"
WINDOW_UNIT = "omdrop-coex-window"
STATE = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "omdrop-coex.json"


def coex_driver():
    try:
        return COEX_PARAM.read_text().strip() == "Y"
    except OSError:
        return False


def real_cli():
    cli = os.environ.get("OMDROP_CLI_REAL") or shutil.which("omdrop")
    if not cli or Path(cli).resolve() == Path(__file__).resolve():
        raise ValueError("Installare il backend Omdrop.")
    return cli


def omdrop_status(cli):
    result = subprocess.run([cli, "status", "--json"], capture_output=True, text=True, timeout=10, check=True)
    status = json.loads(result.stdout)
    if not isinstance(status, dict) or not isinstance(status.get("receiving"), bool):
        raise ValueError("Impossibile verificare lo stato di AirDrop.")
    return status


def user_unit_active(unit):
    return subprocess.run(["systemctl", "--user", "is-active", "--quiet", unit]).returncode == 0


def coex_status(cli):
    status = omdrop_status(cli)
    radio = {"visible": False, "reason": "stopped"}
    try:
        radio = json.loads(subprocess.run([COEX_SESSION, "status"], capture_output=True, text=True,
                                          timeout=10).stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        radio["reason"] = "coex_helper_missing"
    receiving = user_unit_active(RECEIVE_UNIT)
    try:
        state = json.loads(STATE.read_text())
    except (OSError, ValueError):
        state = {}
    deadline = state.get("deadline")
    status.update({
        "receiving": receiving,
        "visible": bool(radio.get("visible")),
        "reason": radio.get("reason") if receiving or radio.get("reason") != "ok" else "stopped",
        "mode": state.get("mode", "forever") if receiving else "off",
        "remaining": max(0, int(deadline - time.time())) if receiving and deadline else None,
        "rx_proven": False,
        # Read by the panel to say that Wi-Fi stays connected.
        "coex": True,
    })
    return status


def radio_active():
    return subprocess.run(["systemctl", "is-active", "--quiet", "awdl-coex-radio"]).returncode == 0


def coex_on(cli, window):
    status = omdrop_status(cli)
    if status.get("visibility") != "everyone":
        raise ValueError("Con Wi-Fi + AirDrop insieme si riceve solo da «Tutti»: cambia il pubblico nel pannello.")
    # A reschedule replaces the receiver and its window; the radio stays up.
    stop_receiver()
    if not radio_active():
        rc = subprocess.run(["pkexec", COEX_SESSION, "start"], timeout=120).returncode
        if rc not in (0, 5):
            raise ValueError("La radio AirDrop non è partita (driver Wi-Fi + AirDrop).")
    window = window or "forever"
    mode = window if window in ("once", "forever") else "timed"
    deadline = None
    if mode == "timed":
        minutes = int(window.rstrip("m")) if window.rstrip("m").isdigit() else 10
        deadline = time.time() + minutes * 60
    # Written first: the receiver reads "one file" mode from it; at boot there is none, so "forever".
    STATE.write_text(json.dumps({"mode": mode, "deadline": deadline}))
    subprocess.run(["systemctl", "--user", "reset-failed", RECEIVE_UNIT], capture_output=True)
    subprocess.run(["systemctl", "--user", "start", RECEIVE_UNIT], check=True)
    if mode == "timed":
        subprocess.run(["systemd-run", "--user", "--quiet", f"--unit={WINDOW_UNIT}", f"--on-active={minutes}m",
                        sys.executable, str(Path(__file__).resolve()), "off"], check=True)
    return 0


def stop_receiver():
    for unit in (f"{WINDOW_UNIT}.timer", RECEIVE_UNIT):
        subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True)
    STATE.unlink(missing_ok=True)


def coex_off():
    stop_receiver()
    subprocess.run(["pkexec", COEX_SESSION, "stop"], timeout=60)
    return 0


def coex(cli, args):
    """Handle what differs with the coexistence driver; None means forward to Omdrop."""
    command = args[0] if args else ""
    if command == "status" and "--json" in args:
        print(json.dumps(coex_status(cli)))
        return 0
    if command == "toggle":
        return coex_off() if user_unit_active(RECEIVE_UNIT) else coex_on(cli, args[1] if len(args) > 1 else None)
    if command == "on":
        return coex_on(cli, next((a for a in args[1:] if not a.startswith("-")), None))
    if command == "off":
        return coex_off()
    if command == "peers":
        # The old exclusive backend answers this as root via pkexec, every 2 s while the radar is
        # open; with the coexistence radio it must not touch the card. No peer list yet: empty.
        if "--stream" not in args:
            print("[]")
        return 0
    if command in ("name", "dir") and len(args) > 1:
        # Omdrop saves the setting; the receiver reads it when it starts.
        rc = subprocess.run([cli, *args]).returncode
        if rc == 0 and user_unit_active(RECEIVE_UNIT):
            subprocess.run(["systemctl", "--user", "restart", RECEIVE_UNIT])
        return rc
    if command == "send":
        raise ValueError("Invio non ancora disponibile con Wi-Fi + AirDrop insieme.")
    return None


def run(args):
    cli = real_cli()
    if coex_driver():
        rc = coex(cli, args)
        if rc is not None:
            return rc
    elif args and args[0] in ("on", "toggle", "send"):
        status = omdrop_status(cli)
        stopping = args[0] == "toggle" and status["receiving"]
        already_up = status["receiving"] and status.get("visible") is True
        if not stopping and not already_up:
            owly = shutil.which("owly")
            if not owly:
                raise ValueError("Owly non installato.")
            result = subprocess.run([owly, "doctor", "--json"], capture_output=True, text=True, timeout=10, check=True)
            report = json.loads(result.stdout)
            if not isinstance(report, dict) or report.get("mode") not in ("shared", "exclusive", "active-monitor") or report.get("missing") != []:
                raise ValueError("La radio di Owly non è pronta.")
            if report["mode"] != "shared":
                answer = subprocess.run([
                    "zenity", "--question", "--no-markup", "--default-cancel", "--title=AirDrop",
                    "--text=Questa modalità AirDrop scollega il Wi-Fi durante la ricezione. Continuare?",
                ], timeout=60)
                if answer.returncode:
                    return 1
    os.execv(cli, [cli, *args])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run(sys.argv[1:]))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"AirDrop: {error}", file=sys.stderr)
        sys.exit(1)
