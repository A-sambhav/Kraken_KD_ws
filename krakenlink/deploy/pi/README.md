# Raspberry Pi deployment

1. Flash stock 64-bit Raspberry Pi OS Bookworm or newer on a Pi 5 (8 GB), boot it, and connect the Pi to the network. The KrakenSDR needs its own 5 V supply; power the Pi with a 5 V/5 A supply.
2. Clone this repository on the Pi. From the repository root run `deploy/pi/install_kraken.sh`, then `deploy/pi/install_krakenlink.sh`. The first script installs the KrakenSDR DAQ/DOA stack and the vendored `krakensdr_doa`; the second creates the bridge virtualenv, detects USB serial devices and enables both services. Connect devices and rerun the second script after plugging in missing devices. Log out and back in after the `dialout` group change.
3. Reboot. Check with `~/krakenlink/.venv/bin/python -m krakenlink.tools.check --config ~/krakenlink/bridge.toml`.
4. On the ground station, follow the existing ground ESP-NOW setup: install the ground ESP32-S3 firmware, configure `deploy/ground.espnow.toml`, and launch the ground app with `python -m krakenlink.ground --config deploy/ground.espnow.toml`.

The Pi bridge uses ESP-NOW via the air ESP32-S3 and USB MAVLink from Cube Orange for pose/heading. Connect the Cube by USB; ArduPilot USB MAVLink works without parameter changes, and the bridge requests the needed data rates. The telemetry radio is not used. For troubleshooting, the Kraken DOA debug UI remains available on port 8080.
