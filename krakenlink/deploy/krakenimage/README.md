# KrakenLink on the official KrakenSDR image

The Pi 5 runs the **official KrakenSDR image** unchanged (its own `krakensdr.service` starts Kraken).
KrakenLink adds only the bridge, all inside `~/krakenlink` on the Pi, plus one systemd unit
(`/etc/systemd/system/krakenlink-bridge.service`). No existing file on the image is modified.

```
Kraken (_share/DOA_value.html, settings.json) -> bridge (~/krakenlink) -> AIR ESP32-S3 (USB "COM" port)
   ~~ ESP-NOW ~~> GROUND ESP32-S3 (laptop USB "COM" port) -> ground app http://127.0.0.1:8050
```

## Files

| File | Where it runs | What it does |
|------|---------------|--------------|
| `push.sh [user@host]` | laptop | rsyncs `krakenlink/` + the files below to `~/krakenlink` on the Pi, restarts the bridge |
| `run_bridge.sh` | Pi | `run` (foreground, used by systemd), `start`/`stop` (by hand), `status`, `log`, `install-service`, `remove-service` |
| `bridge.toml.in` | Pi | bridge config; `@AIR_PORT@` is filled from `/dev/serial/by-id` at every start |
| `krakenlink-bridge.service.in` | Pi | systemd unit, runs as `krakenrf`, `Restart=always` (waits for the ESP32 / Kraken) |

## Setup (once)

1. Flash the ESP32-S3 boards: `pio run -d firmware/esp32_link -e air_s3 -t upload` (Pi board) and
   `-e ground_s3` (laptop board). Plug **both into their "COM" (CH343) USB port**, not the native "USB" port.
2. From the laptop: `deploy/krakenimage/push.sh`
3. On the Pi: `cd ~/krakenlink && ./run_bridge.sh install-service` (starts now and on every boot).

## Use

- Laptop: `python3 -m krakenlink.ground --config ground.espnow.toml`, open http://127.0.0.1:8050.
- Pi: `./run_bridge.sh status` / `./run_bridge.sh log`; `sudo systemctl restart krakenlink-bridge`.
- After changing code on the laptop: `deploy/krakenimage/push.sh` again.

## Limits

- The bridge runs as `krakenrf`; Kraken's `settings.json` is root-owned, so ground → Pi **commands are
  refused** (DOA/spectrum/status downlink works). Running the bridge as root would enable them.
- Kraken writes DOA only when a signal is above the VFO squelch, unless the squelch is set below the noise
  floor (then you get bearings on noise with very low confidence).
- The Pi has no time sync off-network; CSV log timestamps use its clock.
