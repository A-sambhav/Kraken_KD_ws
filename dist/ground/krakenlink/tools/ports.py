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
