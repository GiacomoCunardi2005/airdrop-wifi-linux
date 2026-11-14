# iwlwifi AWDL coexistence patch (experimental)

`iwlwifi-awdl-coex-7.3.patch` applies to the Linux 7.3 tree (built against CachyOS 7.3.4). It is derived from the
kernel's iwlwifi driver and is therefore **GPL-2.0**.

It adds a module parameter `awdl_coex` (off by default, PCI `8086:7e40` only) that lets a monitor interface live on a
second channel next to an associated station:

- single RX queue (`pcie/gen1_2/trans.c`)
- `NO_VIRTUAL_MONITOR` so the monitor is a real firmware listener context (`mvm/mac80211.c`)
- monitor channel context accepted unless it equals the station's channel (`mvm/mld-mac80211.c`)
- `RX_INCLUDES_FCS` is **not** set in this mode: with it, the station associates but WPA never completes

Build only the driver directory against your running kernel (clang-built kernels need `LLVM=1`):

    make -C /usr/lib/modules/$(uname -r)/build M=$PWD/drivers/net/wireless/intel/iwlwifi LLVM=1 \
         CONFIG_IWLWIFI=m CONFIG_IWLMVM=m CONFIG_IWLMLD=m modules

Loading is done by `scripts/awdl-coex-test`, which arms a rollback timer and attempts to restore the stock modules
and reconnect on exit. Recovery failures are reported; the timer remains armed if cleanup fails.
This can crash the firmware or the kernel. Save your work first.
