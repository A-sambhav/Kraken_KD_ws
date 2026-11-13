# ESP32-S3 firmware

Boards are ESP32-S3-N16R8. Use the CH343 **COM** port for flashing. Flash AIR to the Pi and GROUND to the laptop;
pairing is automatic. Each role folder has its own `flash.sh` and its merged image is flashed at address `0x0`.
Run `make_dist.sh --firmware` from the source checkout to build those images.

On Windows, install Python 3.9+ from python.org (tick **Add python.exe to PATH**) and run `flash.bat` in the role
folder, or `flash.bat -Port COM5` to choose the port (Device Manager > Ports (COM & LPT)). It creates `.venv` with
esptool on first use.
