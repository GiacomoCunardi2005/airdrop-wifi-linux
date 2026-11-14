# Owly on the experimental coexistence monitor

This is a bounded diagnostic experiment, **not an always-on receiver yet**. It retains the existing
iwlwifi coexistence patch and channel setup, but uses Owly's AWDL engine and AirDrop receiver instead
of OWL/OpenDrop. This separates userspace differences from the next driver experiments.

The adapter uses Owly's existing `Native` engine on the prepared `awdlmon` interface, fixed to channel 6.
It creates `awdl0`, handles signals and radio failures, and stops after at most 210 seconds.
It does not create an ACKing IBSS context. The monitor still has the known ACK limitation; successful
discovery or transfer is not assumed. Keep the working exclusive-mode `airdrop-owly` as the control.

The small CLI patch adds an explicit `receive --fixed-channel` option: 64 mDNS announcements spaced
16.4 ms apart, then a three-second pause, matching Owly's fixed-radio announcement policy.
Without this option, a receiver attached outside owlyd cannot obtain that policy from a radio lease.
The normal command and its per-transfer confirmation remain unchanged.

## Build on this lab layout

Prerequisite: Owly 0.4.3 source at `~/awdl-diag/owly`, commit
`21171d8f9a08bfa2c625a1fa338e877a67913e54`, and the coexistence modules described in `patches/README.md`.
From this repository, apply once to a clean Owly checkout:

```bash
git -C ~/awdl-diag/owly apply "$PWD/patches/owly-fixed-announce.patch"
install -D -m 644 experiments/owly-coex-radio.rs \
  ~/awdl-diag/owly/crates/owly-cli/examples/coex-radio.rs
cargo build --manifest-path ~/awdl-diag/owly/Cargo.toml --locked --release \
  -p owly-cli --bin owly --example coex-radio
```

The test uses the binaries in that checkout's `target/release`; it does not replace the installed
Owly CLI, daemon or driver profile. Do not run another AirDrop session at the same time.

## Run and assess

Save work first: loading experimental kernel modules can still crash the system. Setup and teardown
briefly interrupt Wi-Fi; the question here is whether transfers work **during** coexistence. An
always-on solution must remove those transitions from normal use and pass recovery/stability tests.

```bash
AIRDROP=owly scripts/awdl-coex-test
```

When prompted, open the iPhone share sheet with AirDrop set to Everyone for 10 Minutes. If the PC
appears, send a photo and answer `y` at the receiver's prompt. Let the test finish after about three
minutes. Captures and logs stay under `~/awdl-diag`, outside this repository:

- `coex-owly-radio-*`: AWDL peer and packet counters.
- `coex-owly-receive-*`: discovery, offer and receive output.
- `coex-radio-*` / `coex-awdl0-*`: paired radio and IPv6 captures.
- `coex-ping-*` / `coex-internet-*`: gateway and external ICMP reachability during reception.
- `coex-kernel-*`: kernel recovery/errors (also includes earlier messages from this boot).

External ICMP uses `one.one.one.one`; a successful gateway ping alone does not prove Internet access.
This is not yet a throughput or sustained application-connectivity test. A transfer counts only when
a new file is received, its offered size matches, and its content decodes; pre-existing files do not count.

Validation without touching the radio:

```bash
python3 -B -m unittest discover -s tests -v
cargo test --manifest-path ~/awdl-diag/owly/Cargo.toml --locked -p owly-cli --bin owly \
  fixed_channel_announcements_are_opt_in_and_require_mdns
```
