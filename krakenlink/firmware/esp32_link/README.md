# KrakenLink ESP32 ESP-NOW bridge

This PlatformIO project builds one opaque KLF frame forwarder for each side of
the link. It validates KLF v1 framing and CRC, carries one unchanged frame per
ESP-NOW packet, and reports local counters to its host once per second as KLF
type `0x7F`.

## Wiring

On the air unit, connect the Raspberry Pi UART at 460800 baud, 8N1:

- Pi TX → ESP32 GPIO16 (UART RX)
- Pi RX ← ESP32 GPIO17 (UART TX)
- Pi GND ↔ ESP32 GND

The ground unit uses USB serial (`Serial`) at 460800 baud. Do not connect the
Pi UART to ESP32 pins while using the ground USB serial arrangement.

## Pairing and channel

Edit `include/config.h` on both units. Set `PEER_MAC` to the other ESP32's
station MAC, and use the same `ESPNOW_CHANNEL` on both. The file also contains
the air UART pin/baud settings and the optional `ENABLE_BROADCAST_PAIRING`
switch. Type `0x7F` is local status and is never sent over ESP-NOW.

## Build and flash

Install PlatformIO Core and the Espressif32 platform, then connect the target:

```sh
pio run -e air
pio run -e ground
pio run -e air -t upload --upload-port /dev/ttyUSB0
pio run -e ground -t upload --upload-port /dev/ttyUSB1
pio device monitor -b 460800 --port /dev/ttyUSB1
```

The `air` and `ground` environments define `ROLE_AIR` and `ROLE_GROUND` and
share `src/main.cpp`.

## ESP-NOW Long Range

Set `USE_LR_MODE` to `1` in `include/config.h` on **both** modules to enable
Espressif's WiFi LR protocol. LR mode trades throughput for sensitivity; both
ends must use the same mode. It remains on the configured 2.4 GHz channel.

## Native checks and vectors

```sh
pio test -e native
python tools/gen_vectors.py
```

`test/test_klf/vectors.h` is committed output from the Python `krakenlink.proto`
codec. The pytest vector-drift check regenerates the header in memory and
compares it with the committed file.
