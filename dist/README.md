# KrakenLink distribution

1. Flash the official KrakenSDR image on the Pi.
2. From the laptop run `cd dist/raspi && ./deploy.sh krakenrf@<pi-ip>`.
3. On the receiver laptop run `cd dist/ground && ./install.sh && ./run_ground.sh`.

Flash `dist/esp/air` to the Pi's AIR board and `dist/esp/ground` to the receiver's GROUND board. Pairing is automatic.
