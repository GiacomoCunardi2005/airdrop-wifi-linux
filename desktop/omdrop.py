#!/usr/bin/python3
"""Forward the original panel's commands, checking Wi-Fi impact before startup."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def run(args):
    cli = os.environ.get("OMDROP_CLI_REAL") or shutil.which("omdrop")
    if not cli or Path(cli).resolve() == Path(__file__).resolve():
        raise ValueError("Installare il backend Omdrop.")
    if args and args[0] in ("on", "toggle", "send"):
        result = subprocess.run([cli, "status", "--json"], capture_output=True, text=True, timeout=10, check=True)
        status = json.loads(result.stdout)
        if not isinstance(status, dict) or not isinstance(status.get("receiving"), bool):
            raise ValueError("Impossibile verificare lo stato di AirDrop.")
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
