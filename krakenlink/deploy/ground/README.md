# KrakenLink ground station

On Ubuntu/Debian with Python 3.9 or newer, run `./install.sh` once, then plug in the GROUND ESP32-S3 using its
CH343 COM port and run `./run_ground.sh`. Open http://127.0.0.1:8050. Pass `--port DEV` to select a port
explicitly or `--no-browser` to suppress browser launch.

The Settings tab sends commands to the Pi bridge and shows their acknowledgement state. After changing a value,
wait for the command table to show completion before sending another command of the same type.
