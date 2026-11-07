import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "krakenlink"


def run(args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, **kwargs)


def test_make_dist_layout_help_and_scripts(tmp_path):
    out = tmp_path / "bundle"
    result = run([str(SRC / "make_dist.sh"), "--out", str(out)])
    assert result.returncode == 0, result.stderr
    expected = {"raspi/krakenlink", "raspi/run_bridge.sh", "raspi/bridge.toml.in", "raspi/krakenlink-bridge.service.in", "raspi/install.sh", "raspi/uninstall.sh", "raspi/deploy.sh", "raspi/README.md", "ground/krakenlink", "ground/install.sh", "ground/run_ground.sh", "ground/ground.toml.in", "ground/requirements.txt", "ground/README.md", "esp/README.md", "esp/air/flash.sh", "esp/air/README.md", "esp/ground/flash.sh", "esp/ground/README.md", "README.md"}
    actual = {str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()}
    package_files = {name for name in actual if name.startswith(("raspi/krakenlink/", "ground/krakenlink/"))}
    assert (expected - {"raspi/krakenlink", "ground/krakenlink"}) | package_files == actual
    assert {p.name for p in out.iterdir()} == {"raspi", "ground", "esp", "README.md"}
    assert not list(out.rglob("__pycache__")) and not list(out.rglob("*.pyc"))
    for script in out.rglob("*.sh"):
        assert os.access(script, os.X_OK)
        assert run(["bash", "-n", str(script)]).returncode == 0
    for rel in ("raspi/install.sh", "raspi/deploy.sh", "ground/install.sh", "ground/run_ground.sh", "esp/air/flash.sh"):
        result = run([str(out / rel), "--help"])
        assert result.returncode == 0, result.stderr
    assert run([str(SRC / "make_dist.sh"), "--help"]).returncode == 0


def test_ground_and_bridge_configs_load(tmp_path):
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    ground = (SRC / "deploy/ground/ground.toml.in").read_text().replace("@GROUND_PORT@", "/dev/example")
    cfg = tomllib.loads(ground)
    assert cfg["transport"] == {"type": "espnow", "port": "/dev/example", "baudrate": 460800}
    bridge = (SRC / "deploy/krakenimage/bridge.toml.in").read_text().replace("@AIR_PORT@", "/dev/example")
    path = tmp_path / "bridge.toml"
    path.write_text(bridge)
    import sys
    sys.path.insert(0, str(SRC))
    try:
        from krakenlink.bridge.__main__ import load_config
        assert load_config(path)["transport"] == {"type": "espnow_uart", "port": "/dev/example", "baud": 460800}
    finally:
        sys.path.remove(str(SRC))


def test_ground_port_detection_with_fake_by_id(tmp_path):
    bundle = tmp_path / "bundle"
    assert run([str(SRC / "make_dist.sh"), "--out", str(bundle)]).returncode == 0
    runner = bundle / "ground/run_ground.sh"
    byid = tmp_path / "by-id"
    byid.mkdir()
    (byid / "usb-Espressif_Ground").touch()
    result = run([str(runner), "--no-browser"], env={**os.environ, "KRAKENLINK_BY_ID": str(byid)})
    assert result.returncode != 0 and "Missing .venv" in result.stderr
    (byid / "usb-Espressif_Ground").unlink()
    result = run([str(runner), "--no-browser"], env={**os.environ, "KRAKENLINK_BY_ID": str(byid)})
    assert result.returncode != 0 and "No GROUND ESP32 port" in result.stderr


def test_flash_port_and_role_selection(tmp_path):
    bundle = tmp_path / "bundle"
    assert run([str(SRC / "make_dist.sh"), "--out", str(bundle)]).returncode == 0
    script = bundle / "esp/air/flash.sh"
    byid = tmp_path / "by-id"
    byid.mkdir()
    env = {**os.environ, "KRAKENLINK_BY_ID": str(byid)}
    result = run([str(script)], env=env)
    assert result.returncode != 0 and "Expected exactly one CH343" in result.stderr
    first, second = byid / "usb-1a86-A", byid / "usb-1a86-B"
    first.touch(); second.touch()
    result = run([str(script)], env=env)
    assert result.returncode != 0 and str(first) in result.stderr and str(second) in result.stderr
    other = tmp_path / "other"
    other.mkdir()
    shutil.copy(script, other / "flash.sh")
    result = run([str(other / "flash.sh")])
    assert result.returncode != 0 and "folder named air or ground" in result.stderr


RUNTIME = {".venv", "logs", "__pycache__"}  # created by using a bundle in place (see .gitignore)
RUNTIME_FILES = {"ground/ground.toml", "raspi/bridge.toml"}


def tree_bytes(root):
    """sha256 per generated file; hashes keep a failing diff small (raw bytes made pytest use ~11 GB)."""
    import hashlib
    out = {}
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if not p.is_file() or RUNTIME.intersection(rel.parts) or str(rel) in RUNTIME_FILES:
            continue
        out[str(rel)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_committed_dist_matches_generator(tmp_path):
    actual, fresh = tree_bytes(ROOT / "dist"), tmp_path / "fresh"
    result = run([str(SRC / "make_dist.sh"), "--out", str(fresh)])
    assert result.returncode == 0, result.stderr
    expected = tree_bytes(fresh)
    ignore = {f"esp/{role}/{name}" for role in ("air", "ground") for name in ("firmware.bin", "firmware.sha256")}
    assert {k: v for k, v in actual.items() if k not in ignore} == {k: v for k, v in expected.items() if k not in ignore}
