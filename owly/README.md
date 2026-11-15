# Owly pieces

Built by `packaging/arch/PKGBUILD` on top of [Owly](https://github.com/t4t5/owly) 0.4.3
(commit `21171d8f9a08bfa2c625a1fa338e877a67913e54`):

- `fixed-announce.patch` adds `owly receive --fixed-channel`: 64 mDNS announcements 16.4 ms apart, then a
  three-second pause, as Owly's fixed radio does. A receiver outside `owlyd` can't get that policy otherwise.
- `coex-radio.rs` is the `coex-radio` example: Owly's AWDL engine on the prepared `awdlmon`, fixed channel 6,
  creating `awdl0`. It runs until stopped (`OWLY_COEX_SECS` bounds a test run).

Both are MIT-licensed changes to Owly, copyright (c) 2026 T4T5; see [LICENSE.owly](LICENSE.owly).
