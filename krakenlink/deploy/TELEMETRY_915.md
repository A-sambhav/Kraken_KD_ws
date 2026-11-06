# 915 MHz MicoAir telemetry setup (Transport A)

> **Legal:** 915 MHz is not license-exempt in India (the band there is 865-867 MHz).
> Set the radio pair to 865-867 MHz if its firmware allows, before any flight.

## Wiring
- Air radio -> Cube Orange **TELEM1** (SERIAL1).
- Cube Orange -> Raspberry Pi 5 by **USB** (shows as `/dev/ttyACM0`).
- Ground radio -> laptop USB (usually `/dev/ttyUSB0`; check with `ls /dev/serial/by-id/`).

## Cube Orange (ArduPilot) parameters
| Param | Value | Why |
|---|---|---|
| SERIAL1_PROTOCOL | 2 | MAVLink2 on the radio port |
| SERIAL1_BAUD | 57 | 57600, must match the radio's serial baud |
| SYSID_THISMAV | 1 | must match `source_system` / `target_system` in the configs |
| SR1_* (EXTRA1, POSITION, ...) | keep modest (2-4 Hz) | leaves radio capacity for KrakenLink |
USB (SERIAL0) is MAVLink by default. ArduPilot forwards TUNNEL between USB and TELEM1 automatically.

## Radio
- Both radios: same air speed (64 kbps recommended), NetID, frequency range, and MAVLink framing on.
- If the radios are SiK-compatible they send RADIO_STATUS; the bridge throttles itself when the buffer fills.

## Run
1. Pi: `sudo ~/krakenlink/.venv/bin/python -m krakenlink.bridge --config ~/krakenlink/deploy/bridge.mavlink.toml`
2. Laptop: `mavproxy.py --master=/dev/ttyUSB0 --baudrate 57600 --out udp:127.0.0.1:14550 --out udp:127.0.0.1:14551`
3. Laptop: open QGroundControl (auto-connects on UDP 14550).
4. Laptop: `python -m krakenlink.ground --config deploy/ground.mavlink.toml`, then open http://127.0.0.1:8050
5. Check: QGC still shows normal telemetry; ground app link panel is UP.
6. When stable, install the systemd unit (`deploy/krakenlink-bridge.pi.service`) so the bridge starts on boot.
