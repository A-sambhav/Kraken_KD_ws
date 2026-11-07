# ESP32-S3 firmware

Boards are ESP32-S3-N16R8. Use the CH343 **COM** port for flashing. Flash AIR to the Pi and GROUND to the laptop;
pairing is automatic. Each role folder has its own `flash.sh` and its merged image is flashed at address `0x0`.
Run `make_dist.sh --firmware` from the source checkout to build those images.
