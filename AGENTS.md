# Notes for AI agents

- Porting to another Wi-Fi chip: read [docs/PORTING.md](docs/PORTING.md). Only the kernel driver changes;
  user space detects any module exposing `parameters/awdl_coex`.
- What was measured, including dead ends: [docs/FINDINGS.md](docs/FINDINGS.md). Add new results there
  with absolute dates.
- Driver experiments can crash the firmware or the kernel: one radio experiment per boot, ask the user
  before loading modules, and never retry `sudo` in a loop (`pam_faillock`).
- Tests: `python3 -B -m unittest discover -s tests`. They mock the radio and never run `sudo`.
- Never commit packet captures, logs, MAC addresses, SSIDs or host names.
- Script messages are in Italian; code comments and docs in English.
