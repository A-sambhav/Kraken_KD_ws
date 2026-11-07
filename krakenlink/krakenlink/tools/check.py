"""Pi deployment checks: python -m krakenlink.tools.check --config bridge.toml."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from krakenlink.bridge.__main__ import load_config
from krakenlink.bridge.transports.espnow_uart import ESPNowUARTTransport
from krakenlink.proto.csv_parser import parse_doa_line


def _result(name, status, detail):
    return (status, f"{status} {name}: {detail}")


def check_usb(sys_usb="/sys/bus/usb/devices"):
    count = 0
    for d in Path(sys_usb).glob("*"):
        try:
            if (d / "idVendor").read_text().strip().lower() == "0bda" and (d / "idProduct").read_text().strip().lower() == "2838":
                count += 1
        except OSError:
            pass
    return _result("KrakenSDR USB", "PASS" if count >= 5 else "FAIL", f"found {count}/5 devices")


def _service(name, runner=subprocess.run):
    if not shutil.which("systemctl"):
        return _result(name, "WARN", "systemctl unavailable")
    try:
        p = runner(["systemctl", "is-active", name], capture_output=True, text=True, timeout=3)
        active = (p.stdout or "").strip() == "active" and p.returncode == 0
        return _result(name, "PASS" if active else "FAIL", (p.stdout or p.stderr or "inactive").strip())
    except (OSError, subprocess.SubprocessError) as e:
        return _result(name, "WARN", str(e))


def check_kraken_service(runner=subprocess.run):
    return _service("krakensdr.service", runner)


def check_doa(path):
    try:
        p = Path(path)
        age = time.time() - p.stat().st_mtime
        if age >= 3:
            return _result("DOA data", "FAIL", f"stale ({age:.1f}s)")
        lines = [line for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
        parse_doa_line(lines[-1])
        return _result("DOA data", "PASS", f"fresh 377-field record ({age:.1f}s)")
    except (OSError, ValueError, IndexError) as e:
        return _result("DOA data", "FAIL", str(e))


def check_settings(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("settings root is not an object")
        ok = data.get("doa_data_format") == "Kraken App"
        return _result("Kraken settings", "PASS" if ok else "WARN", "doa_data_format=" + repr(data.get("doa_data_format")))
    except (OSError, ValueError) as e:
        return _result("Kraken settings", "FAIL", str(e))


def check_air(port, serial_factory=None, service_holds_port=False, timeout=3):
    if service_holds_port:
        return _result("Air ESP32", "WARN", "port held by krakenlink-bridge.service; skipped")
    if not port or not Path(port).exists():
        return _result("Air ESP32", "FAIL", "serial port missing")
    transport = None
    try:
        transport = ESPNowUARTTransport(port, serial_factory=serial_factory)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            transport.recv()
            status = transport.stats().get("local_status")
            if status is not None:
                paired = status.get("paired")
                mac = status.get("peer_mac") or "unknown"
                return _result("Air ESP32", "PASS" if paired else "WARN", f"paired={paired}, peer={mac}")
            time.sleep(.02)
        return _result("Air ESP32", "FAIL", "no 0x7F status frame within timeout")
    except Exception as e:
        return _result("Air ESP32", "FAIL", str(e))
    finally:
        if transport:
            transport.close()


def check_fc(port, heartbeat_reader=None, timeout=3):
    if not port or not Path(port).exists():
        return _result("Cube Orange", "WARN", "FC serial port missing; DOA still flows")
    if heartbeat_reader is not None:
        try:
            received = heartbeat_reader(port, timeout)
            return _result("Cube Orange", "PASS" if received else "WARN", "MAVLink HEARTBEAT received" if received else "no MAVLink HEARTBEAT; DOA still flows")
        except Exception as e:
            return _result("Cube Orange", "WARN", str(e))
    try:
        from pymavlink import mavutil
        link = mavutil.mavlink_connection(port, baud=115200)
        msg = link.recv_match(type="HEARTBEAT", blocking=True, timeout=timeout)
        return _result("Cube Orange", "PASS" if msg else "WARN", "MAVLink HEARTBEAT received" if msg else "no MAVLink HEARTBEAT; DOA still flows")
    except Exception as e:
        return _result("Cube Orange", "WARN", str(e))


def run_checks(config, service_runner=subprocess.run, serial_factory=None, heartbeat_reader=None):
    cfg = config
    share = Path(cfg.get("kraken", {}).get("share", "~/krakensdr_doa/krakensdr_doa/_share")).expanduser()
    air = cfg.get("transport", {}).get("port", "")
    fc = cfg.get("fc", {}).get("connection", "")
    # systemctl failure is a FAIL; missing systemctl is a WARN.
    holds = False
    try:
        holds = service_runner(["systemctl", "is-active", "krakenlink-bridge.service"], capture_output=True, text=True, timeout=3).stdout.strip() == "active"
    except (OSError, subprocess.SubprocessError):
        pass
    return [check_usb(), check_kraken_service(service_runner), check_doa(share / "DOA_value.html"), check_settings(share / "settings.json"), check_air(air, serial_factory, holds), check_fc(fc, heartbeat_reader), _service("krakenlink-bridge.service", service_runner)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True)
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    results = run_checks(cfg)
    for _, line in results:
        print(line)
    return int(any(status == "FAIL" for status, _ in results))


if __name__ == "__main__":
    sys.exit(main())
