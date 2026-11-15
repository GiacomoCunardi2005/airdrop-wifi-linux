#!/usr/bin/python3
"""User side of "Wi-Fi + AirDrop insieme": Owly's receiver on awdl0, consent asked on the desktop.

`owly receive` prints each offer on stderr and waits up to 15 s for y/N on stdin. This wrapper
shows the offer as a GNOME notification with Sì / No instead and answers for the user. --once stops after a file.
"""
import argparse
import html
import json
import os
import subprocess
import sys
import threading
import time

# The packaged Owly build (with receive --fixed-channel); OWLY overrides it for a lab checkout.
OWLY = os.environ.get("OWLY", "/usr/lib/awdl-coex/owly")
PROMPT = "accept? [y/N] "


def ask(offer):
    """GNOME notification with Sì / No, kept on screen (critical) until answered.

    owly declines by itself after 15 s, so the question is withdrawn after 13 s.
    Everything in the offer is the sender's: escaped, never markup (SEC-4).
    """
    sender = offer[0].removesuffix(" wants to send:") if offer else "Un dispositivo"
    body = html.escape("\n".join(offer[1:]) or "un file")
    proc = subprocess.Popen(
        ["notify-send", "--app-name=AirDrop", "--icon=folder-download", "--urgency=critical", "--print-id",
         "--action=yes=Sì", "--action=no=No", f"AirDrop: {sender} vuole inviare", body],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        out, _ = proc.communicate(timeout=13)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
        ids = out.split()
        if ids and ids[0].isdigit():
            subprocess.run(["gdbus", "call", "--session", "--dest=org.freedesktop.Notifications",
                            "--object-path=/org/freedesktop/Notifications",
                            "--method=org.freedesktop.Notifications.CloseNotification", ids[0]],
                           capture_output=True)
        return False
    return "yes" in out.split()


STATE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"), "omdrop-coex.json")


def omdrop_settings():
    """Name and folder from Omdrop's settings, so the panel's choices also hold after a reboot."""
    cli = os.environ.get("OMDROP_CLI_REAL") or os.path.expanduser("~/.local/bin/omdrop")
    try:
        status = json.loads(subprocess.run([cli, "status", "--json"], capture_output=True, text=True,
                                           timeout=20, check=True).stdout)
        return status.get("dir") or os.path.expanduser("~/Downloads"), status.get("name") or os.uname().nodename
    except (OSError, ValueError, subprocess.SubprocessError):
        return os.path.expanduser("~/Downloads"), os.uname().nodename


def once_mode():
    try:
        with open(STATE) as f:
            return json.load(f).get("mode") == "once"
    except (OSError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir")
    parser.add_argument("--name")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not (args.dir and args.name):
        folder, name = omdrop_settings()
        args.dir, args.name = args.dir or folder, args.name or name
    args.once = args.once or once_mode()
    os.makedirs(args.dir, exist_ok=True)
    proc = subprocess.Popen(
        [OWLY, "receive", "--fixed-channel", "--dir", args.dir, "--name", args.name],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=0,
    )
    def watch_radio():
        # owly keeps waiting if awdl0 goes away (radio restart, suspend): end it, so the service restarts.
        while proc.poll() is None:
            if not os.path.exists("/sys/class/net/awdl0"):
                proc.kill()
                return
            time.sleep(5)
    threading.Thread(target=watch_radio, daemon=True).start()
    offer, line = [], ""
    while True:
        ch = proc.stdout.read(1)
        if not ch:
            break
        line += ch
        if line == PROMPT:
            # No newline follows the prompt: answer as soon as it appears.
            proc.stdin.write("y\n" if ask(offer) else "n\n")
            proc.stdin.flush()
            offer, line = [], ""
            continue
        if ch != "\n":
            continue
        text, line = line.rstrip("\n"), ""
        print(text, flush=True)
        if text.endswith("wants to send:"):
            offer = [text]
        elif offer and text.startswith("  "):
            offer.append(text.strip())
        elif text.startswith("/"):
            subprocess.run(["notify-send", "-i", "folder-download", "AirDrop", f"Ricevuto {os.path.basename(text)}"])
            if args.once:
                # One file was the window: a clean exit, so the service doesn't restart it.
                proc.terminate()
                proc.wait()
                return 0
    return proc.wait()


if __name__ == "__main__":
    sys.exit(main())
