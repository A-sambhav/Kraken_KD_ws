# KrakenLink distribution

1. Flash the official KrakenSDR image on the Pi.
2. From the laptop run `cd dist/raspi && ./deploy.sh krakenrf@<pi-ip>`.
3. On the receiver laptop run `cd dist/ground && ./install.sh && ./run_ground.sh`.

Flash `dist/esp/air` to the Pi's AIR board and `dist/esp/ground` to the receiver's GROUND board. Pairing is automatic.

## Windows laptop

Install Python 3.9+ from python.org (tick "Add python.exe to PATH"). The Windows OpenSSH client (ssh, scp) is
built into Windows 10/11.

1. Flash the official KrakenSDR image on the Pi.
2. `cd dist\raspi && deploy.bat krakenrf@<pi-ip>`
3. `cd dist\ground && install.bat && run_ground.bat`

Flash the boards with `dist\esp\air\flash.bat` and `dist\esp\ground\flash.bat` (add `-Port COM5` to pick the port).
