import os
import subprocess
try:
    import tomllib
except ImportError:
    import tomli as tomllib
from pathlib import Path

from krakenlink.bridge.__main__ import load_config


DEPLOY = Path(__file__).parents[1] / "deploy"


def test_installer_architecture_check_is_safe_and_arch_aware(tmp_path):
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    uname = fakebin / "uname"
    uname.write_text('#!/bin/sh\nprintf "%s\\n" "$FAKE_ARCH"\n')
    uname.chmod(0o755)
    script = DEPLOY / "common/install_kraken.sh"
    for arch in ("aarch64", "x86_64"):
        result = subprocess.run(
            [str(script), "--check-architecture"],
            env={**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}", "FAKE_ARCH": arch},
            text=True, capture_output=True, check=False,
        )
        assert result.returncode == 0, result.stderr
        assert f"Supported architecture: {arch}" in result.stdout
    result = subprocess.run(
        [str(script), "--check-architecture"],
        env={**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}", "FAKE_ARCH": "riscv64"},
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 1
    assert "supports aarch64 and x86_64" in result.stderr


def test_installer_has_expected_arch_specific_steps_and_dependencies():
    script = (DEPLOY / "common/install_kraken.sh").read_text()
    assert "Miniforge3-Linux-$ARCH.sh" in script
    assert 'if [[ "$ARCH" == aarch64 ]]' in script
    assert "Ne10" in script
    assert "usb_max_current_enable=1" in script
    assert "scipy==1.9.3 numba==0.56.4 configparser pyzmq scikit-rf" in script
    assert 'CONFIG_SOURCE="$KRAKEN_ROOT/heimdall_daq_fw/config_files/kraken_default"' in script
    assert 'cp -a "$CONFIG_SOURCE"/. "$FW/"' in script
    assert "krakensdr-rtl.conf" in script


def test_pi_installer_is_thin_wrapper():
    text = (DEPLOY / "pi/install_kraken.sh").read_text().splitlines()
    assert len(text) == 2
    assert "../common/install_kraken.sh" in text[-1]


def test_local_bridge_and_ground_configs_load_and_match_ports(tmp_path):
    template = (DEPLOY / "laptop/bridge.local.toml.in").read_text()
    pi_template = (DEPLOY / "pi/bridge.pi.toml.in").read_text()
    assert 'share = "@KRAKEN_ROOT@/krakensdr_doa/_share"' in template
    assert next(line for line in template.splitlines() if line.startswith("share =")) == next(
        line for line in pi_template.splitlines() if line.startswith("share =")
    )
    rendered = tmp_path / "bridge.toml"
    rendered.write_text(template.replace("@KRAKEN_ROOT@", "/tmp/kraken").replace("@LOG_DIR@", "/tmp/logs"))
    bridge = load_config(rendered)
    ground = tomllib.loads((DEPLOY / "laptop/ground.local.toml").read_text())
    assert bridge["transport"] == {
        "type": "loopback", "host": "127.0.0.1", "port": 14570,
        "bind_host": "127.0.0.1", "bind_port": 14561,
    }
    assert "fc" not in bridge
    assert ground["transport"]["type"] == bridge["transport"]["type"]
    assert ground["transport"]["host"] == bridge["transport"]["bind_host"]
    assert ground["transport"]["port"] == bridge["transport"]["bind_port"]
    assert ground["transport"]["bind_host"] == bridge["transport"]["host"]
    assert ground["transport"]["bind_port"] == bridge["transport"]["port"]
    assert (ground["app"]["host"], ground["app"]["port"]) == ("127.0.0.1", 8050)


def test_launcher_help_has_no_side_effects():
    result = subprocess.run([str(DEPLOY / "laptop/kraken_doa.sh"), "--help"], text=True, capture_output=True)
    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "--with-ground" in result.stdout


def test_deploy_scripts_use_scoped_stop_and_safe_rsync():
    scripts = list(DEPLOY.rglob("*.sh"))
    for script in scripts:
        text = script.read_text()
        assert "kill.sh" not in text, script
        assert "kraken_doa_stop.sh" not in text, script
        assert "pkill -f node" not in text, script
    stop_script = DEPLOY / "common/kraken-stop.sh"
    result = subprocess.run(["bash", "-n", str(stop_script)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    launcher = (DEPLOY / "laptop/kraken_doa.sh").read_text()
    rsync_line = next(line for line in launcher.splitlines() if line.startswith("rsync "))
    assert "--exclude='__pycache__/'" in rsync_line
    assert "--exclude='_share/'" in rsync_line
