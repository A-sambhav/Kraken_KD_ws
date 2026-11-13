"""Print the CH343 (USB VID 0x1A86) serial ports, one per line; exit 1 if none. Needs only pyserial."""
import sys

from serial.tools.list_ports import comports

CH343_VID = 0x1A86


def find_ports(ports=None):
    if ports is None:
        ports = comports()
    return sorted(p.device for p in ports if getattr(p, "vid", None) == CH343_VID)


def main():
    found = find_ports()
    if not found:
        print("No ESP32 port found", file=sys.stderr)
        return 1
    print("\n".join(found))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
