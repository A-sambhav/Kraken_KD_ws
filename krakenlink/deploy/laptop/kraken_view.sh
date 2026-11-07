#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
KRAKENLINK_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
FAKE_MODE=0
for arg in "$@"; do
    if [[ "$arg" == "--fake" ]]; then
        FAKE_MODE=1
        break
    fi
done

if [[ "$FAKE_MODE" == 1 ]]; then
    echo "Fake mode enabled; skipping hardware checks and driver setup."
elif command -v lsusb >/dev/null 2>&1; then
    DEVICE_COUNT="$(lsusb -d 0bda:2838 2>/dev/null | wc -l | tr -d ' ')"
    printf 'Found %s KrakenSDR RTL2832U device(s) (expected 5).\n' "$DEVICE_COUNT"
    if [[ "$DEVICE_COUNT" != 5 ]]; then
        echo "Warning: check KrakenSDR power supply / USB cable."
    fi
else
    echo "Warning: lsusb is unavailable; install usbutils to count devices."
fi

if [[ "$FAKE_MODE" != 1 ]] && ! ldconfig -p 2>/dev/null | grep -q 'librtlsdr\.so\.0'; then
    echo "librtlsdr is required for hardware mode. Installing librtlsdr0 and rtl-sdr..."
    sudo apt-get install -y librtlsdr0 rtl-sdr
fi

if [[ "$FAKE_MODE" != 1 ]] && command -v lsmod >/dev/null 2>&1 && lsmod | awk '{print $1}' | grep -qx 'dvb_usb_rtl28xxu'; then
    echo "The DVB kernel driver can claim the RTL-SDR devices."
    read -r -p "Unload it and blacklist DVB drivers for future boots? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        printf '%s\n' 'blacklist dvb_usb_rtl28xxu' 'blacklist rtl2832_sdr' 'blacklist rtl2832' | sudo tee /etc/modprobe.d/blacklist-rtlsdr-kraken.conf >/dev/null
        echo "Wrote /etc/modprobe.d/blacklist-rtlsdr-kraken.conf"
        if ! sudo modprobe -r rtl2832_sdr dvb_usb_rtl28xxu rtl2832 2>/dev/null; then
            echo "Driver is attached to the plugged-in KrakenSDR; librtlsdr will detach it on open (or unplug, re-run, replug)."
        fi
    fi
fi

export PYTHONPATH="$KRAKENLINK_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m krakenlink.tools.kraken_view "$@"
