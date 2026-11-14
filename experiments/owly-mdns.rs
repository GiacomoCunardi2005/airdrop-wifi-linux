//! Unprivileged Owly mDNS responder for the installed Omdrop receiver.
//! Reuses the current radio lease; never acquires or changes the radio.
use owly_airdrop::{
    driver::mdns::Mdns,
    proto::mdns::{Burst, RECEIVER_FLAGS, Service},
};
use owlyd::api::{self, LinkInfo};
use std::io;
use tokio::signal::unix::{SignalKind, signal};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let host = std::env::args()
        .nth(1)
        .ok_or_else(|| io::Error::other("usage: owly-mdns <host-label>"))?;
    let mut term = signal(SignalKind::terminate())?;
    let connection = api::connect(None).await?;
    let radio = api::radio(&connection).await?;
    let link = LinkInfo::from_dict(&radio.link().await?)
        .filter(|link| link.interface == "awdl0")
        .ok_or_else(|| io::Error::other("Owly has no awdl0 lease"))?;
    let burst = link.announce.map(|a| Burst {
        count: a.count,
        interval: a.interval,
        pause: a.pause,
    });
    let service = Service {
        instance: link.mac.replace(':', ""),
        host,
        port: 8771,
        addr: link.address.parse()?,
        flags: RECEIVER_FLAGS,
    };
    let registration = Mdns::new(link.index)
        .with_burst(burst)
        .register(service)
        .await?;
    eprintln!("Owly mDNS responder ready on awdl0:8771 (existing lease)");
    tokio::select! { _ = term.recv() => {}, _ = tokio::signal::ctrl_c() => {} }
    drop(registration);
    Ok(())
}
