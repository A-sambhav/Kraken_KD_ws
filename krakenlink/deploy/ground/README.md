# KrakenLink ground station

On Ubuntu/Debian with Python 3.9 or newer, run `./install.sh` once, then plug in the GROUND ESP32-S3 using its
CH343 COM port and run `./run_ground.sh`. Open http://127.0.0.1:8050. Pass `--port DEV` to select a port
explicitly or `--no-browser` to suppress browser launch.

The Settings tab sends commands to the Pi bridge and shows their acknowledgement state. After changing a value,
wait for the command table to show completion before sending another command of the same type.

## Windows

1. Install Python 3.9 or newer from python.org and tick **Add python.exe to PATH**.
2. Plug in the GROUND ESP32-S3 by its CH343 COM port. Windows Update normally installs the CH343 driver; if no COM
   port appears, install WCH's CH343SER driver. The port is listed in Device Manager under Ports (COM & LPT).
3. In this folder run `install.bat` once, then `run_ground.bat` (or `run_ground.bat -Port COM5`, add `-NoBrowser`
   to skip opening the browser). Both can also be started by double-clicking. Press Ctrl+C to stop.
