//! Lab adapter: run Owly on the channel-6 monitor prepared by awdl-coex-test.
//! Build as the `coex-radio` example in Owly's owly-cli crate (0.4.3).
use std::{io, time::Duration};

use owly_awdl::{Channel, Config, Presence, RadioConstraints};
use owly_radio::native::Native;
use tokio::signal::unix::{SignalKind, signal};
use tokio::sync::watch;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt()
        .with_env_filter("owly_awdl=info,owly_radio=info")
        .with_ansi(false)
        .init();
    // Register before starting the worker so teardown can close its TAP cleanly.
    let mut interrupt = signal(SignalKind::interrupt())?;
    let mut terminate = signal(SignalKind::terminate())?;
    let mut hangup = signal(SignalKind::hangup())?;
    if std::path::Path::new("/sys/class/net/awdl0").exists() {
        return Err(io::Error::other("awdl0 already exists; stop the other receiver").into());
    }
    let mac = std::fs::read_to_string("/sys/class/net/awdlmon/address")?;
    let host = nix::unistd::gethostname()?;
    let config = Config::new(
        mac.trim().parse()?,
        &host.to_string_lossy(),
        RadioConstraints {
            channel: Channel(6),
            presence: Presence::Fixed,
        },
    );
    let (peers, _peer_updates) = watch::channel(Vec::new());
    let radio = Native::start("awdlmon", "awdl0", config, peers)?;
    let mut failed = radio.failed();
    println!("Owly AWDL on awdlmon, fixed channel 6; station untouched by this adapter");
    tokio::select! {
        _ = interrupt.recv() => {},
        _ = terminate.recv() => {},
        _ = hangup.recv() => {},
        // OWLY_COEX_SECS bounds a lab run; the always-on service leaves it unset and runs until stopped.
        _ = async {
            match std::env::var("OWLY_COEX_SECS").ok().and_then(|s| s.parse().ok()) {
                Some(secs) => tokio::time::sleep(Duration::from_secs(secs)).await,
                None => std::future::pending().await,
            }
        } => {},
        _ = failed.wait_for(|reason| reason.is_some()) => {},
    }
    let failure = failed.borrow().clone();
    radio.stop();
    if let Some(reason) = failure {
        return Err(io::Error::other(reason).into());
    }
    Ok(())
}
