# KrakenLink on the official KrakenSDR image

Flash the official KrakenSDR image on the Pi. From a laptop with this bundle, deploy it with:

```sh
cd dist/raspi
./deploy.sh krakenrf@<pi-ip>
```

The deploy script copies the bundle to `~/krakenlink` and runs its installer. The bridge is installed as a
systemd service. It uses only files in this folder and adds `/etc/systemd/system/krakenlink-bridge.service`.

## Day-to-day

```sh
./run_bridge.sh status
./run_bridge.sh log
sudo systemctl restart krakenlink-bridge
./uninstall.sh
```

The installer checks Python, serial and TOML support, warns if the Kraken share or AIR ESP32 is absent, then
installs and starts the service. `install.sh --no-service` skips the service step. `uninstall.sh` removes the
service but leaves this folder and its logs/configuration. The bridge runs as root so ground commands can update
the Kraken-owned settings file; logs remain under this folder.

For operation, plug the AIR ESP32 into its CH343 COM port. The bridge detects the port on each start.
