"""Stable serial port discovery for Pi deployments."""
from pathlib import Path


def detect_ports(by_id="/dev/serial/by-id"):
    """Return (air, Cube) device paths, or empty strings when unavailable."""
    try:
        names = sorted(p.name for p in Path(by_id).iterdir())
    except OSError:
        names = []
    air = next((n for n in names if "1a86" in n.lower() or "espressif" in n.lower()), "")
    cube = next((n for n in names if "cubeorange" in n.lower() and "-if00" in n.lower()), "")
    if not cube:
        cube = next((n for n in names if any(x in n.lower() for x in ("cubepilot", "ardupilot")) and "-if00" in n.lower()), "")
    return (str(Path(by_id) / air) if air else "", str(Path(by_id) / cube) if cube else "")


ESP_VIDS = (0x1A86, 0x303A)  # WCH CH343 (COM port), Espressif native USB


def find_esp_ports(ports=None, vids=ESP_VIDS):
    """Return sorted device names (COM5, /dev/ttyACM0, ...) of USB serial ports with an ESP32 VID."""
    if ports is None:
        from serial.tools.list_ports import comports
        ports = comports()
    return sorted(p.device for p in ports if getattr(p, "vid", None) in vids)


def main(argv=None):
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="List ESP32 serial ports (CH343 or Espressif USB), one per line.")
    ap.add_argument("--esp", action="store_true", help="list ESP32 ports (default)")
    ap.parse_args(argv)
    found = find_esp_ports()
    if not found:
        print("No ESP32 port found", file=sys.stderr)
        return 1
    print("\n".join(found))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
