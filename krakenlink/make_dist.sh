#!/usr/bin/env bash
set -euo pipefail
usage() { echo "Usage: $0 [--out DIR] [--firmware] [--help]"; }
OUT=; firmware=0
while (($#)); do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --out) (($# >= 2)) || { usage >&2; exit 2; }; OUT=$2; shift ;;
    --firmware) firmware=1 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
OUT=${OUT:-$ROOT/dist}
mkdir -p "$OUT"
for item in raspi ground; do rm -rf -- "${OUT:?}/$item"; done
for role in air ground; do rm -f "$OUT/esp/$role/"{flash.sh,flash.ps1,flash.bat,find_port.py,README.md}; done
rm -f "$OUT/README.md"
mkdir -p "$OUT/raspi" "$OUT/ground" "$OUT/esp/air" "$OUT/esp/ground"
copy_package() { tar -C "$ROOT/krakenlink" --exclude='__pycache__' --exclude='*.pyc' -cf - krakenlink | tar -C "$1" -xf -; }
copy_package "$OUT/raspi"
copy_package "$OUT/ground"
cp "$SCRIPT_DIR/deploy/krakenimage/"{run_bridge.sh,bridge.toml.in,krakenlink-bridge.service.in,install.sh,uninstall.sh,deploy.sh,deploy.ps1,deploy.bat,README.md} "$OUT/raspi/"
cp "$SCRIPT_DIR/deploy/ground/"{install.sh,run_ground.sh,install.ps1,install.bat,run_ground.ps1,run_ground.bat,ground.toml.in,requirements.txt,README.md} "$OUT/ground/"
for role in air ground; do
  cp "$SCRIPT_DIR/deploy/esp/"{flash.sh,flash.ps1,flash.bat,find_port.py} "$OUT/esp/$role/"
  if [[ $role == air ]]; then destination='KrakenSDR Pi'; else destination='receiver laptop'; fi
  printf '# KrakenLink %s ESP32-S3\n\nBoard: ESP32-S3-N16R8. Flash with `./flash.sh` (Windows: `flash.bat`) using its CH343 **COM** port. The %s board belongs on the %s. Pairing is automatic.\n' \
    "$role" "$role" "$destination" > "$OUT/esp/$role/README.md"
  chmod +x "$OUT/esp/$role/flash.sh"
done
cp "$SCRIPT_DIR/deploy/esp/README.md" "$OUT/esp/README.md"
cat > "$OUT/README.md" <<'OVERVIEW'
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
OVERVIEW
if (( firmware )); then
  command -v pio >/dev/null || { echo 'pio is required for --firmware' >&2; exit 1; }
  (cd "$ROOT/krakenlink" && pio run -d firmware/esp32_link -e air_s3 -e ground_s3)
  PIO_DIR=${PLATFORMIO_CORE_DIR:-$HOME/.platformio}
  ESPTOOL="$PIO_DIR/packages/tool-esptoolpy/esptool.py"
  BOOTAPP="$PIO_DIR/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin"
  for spec in 'air air_s3' 'ground ground_s3'; do
    read -r role env <<< "$spec"
    BUILD="$ROOT/krakenlink/firmware/esp32_link/.pio/build/$env"
    python3 "$ESPTOOL" --chip esp32s3 merge_bin --flash_mode keep --flash_freq keep --flash_size keep -o "$OUT/esp/$role/firmware.bin" 0x0 "$BUILD/bootloader.bin" 0x8000 "$BUILD/partitions.bin" 0xe000 "$BOOTAPP" 0x10000 "$BUILD/firmware.bin"
    (cd "$OUT/esp/$role" && sha256sum firmware.bin > firmware.sha256)
  done
fi
echo "Wrote distribution bundle to $OUT"
