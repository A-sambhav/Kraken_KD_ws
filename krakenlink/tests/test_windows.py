"""Windows (PowerShell/.bat) side of the dist bundles, SPEC section 23."""
import importlib.util
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "krakenlink"
DEPLOY = SRC / "deploy"
PS1 = {"ground/install.ps1", "ground/run_ground.ps1", "esp/flash.ps1", "krakenimage/deploy.ps1"}
DIST_PS1 = ["ground/install.ps1", "ground/run_ground.ps1", "esp/air/flash.ps1", "esp/ground/flash.ps1", "raspi/deploy.ps1"]
PWSH = shutil.which("pwsh")


def run(args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, **kwargs)


def windows_scripts():
    files = [p for p in DEPLOY.rglob("*") if p.suffix in (".ps1", ".bat")]
    files += [p for p in (ROOT / "dist").rglob("*") if p.suffix in (".ps1", ".bat") and ".venv" not in p.parts]
    return files


def test_gitattributes_line_endings():
    text = (ROOT / ".gitattributes").read_text()
    for rule in ("*.sh       text eol=lf", "*.ps1      text eol=crlf", "*.bat      text eol=crlf", "*.bin      binary"):
        assert rule in text
    out = run(["git", "-C", str(ROOT), "check-attr", "eol", "dist/raspi/install.sh", "dist/ground/run_ground.ps1"]).stdout
    assert "dist/raspi/install.sh: eol: lf" in out
    assert "dist/ground/run_ground.ps1: eol: crlf" in out


def test_sources_exist():
    assert {str(p.relative_to(DEPLOY)) for p in DEPLOY.rglob("*.ps1")} >= PS1
    for ps1 in PS1:
        assert (DEPLOY / ps1).with_suffix(".bat").is_file()
    assert (DEPLOY / "esp/find_port.py").is_file()


def test_windows_scripts_ascii_crlf_and_structure():
    files = windows_scripts()
    assert len(files) >= 2 * len(PS1) + 2 * len(DIST_PS1)
    for path in files:
        data = path.read_bytes()
        data.decode("ascii")
        assert data.endswith(b"\r\n"), path
        assert data.count(b"\n") == data.count(b"\r\n"), f"bare LF in {path}"
        text = data.decode()
        if path.suffix == ".bat":
            name = path.stem
            assert text == f'@echo off\r\npowershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0{name}.ps1" %*\r\nexit /b %ERRORLEVEL%\r\n'
            assert path.with_suffix(".ps1").is_file()
        else:
            for needle in ("param(", "$ErrorActionPreference = 'Stop'", "$PSScriptRoot", "[switch]$Help"):
                assert needle in text, (path, needle)


def test_static_content():
    run_ground = (DEPLOY / "ground/run_ground.ps1").read_text()
    for needle in ("UTF8Encoding $false", "finally", "krakenlink.tools.ports", "127.0.0.1:8050", "Missing .venv; run install.bat first", "No GROUND ESP32 port found"):
        assert needle in run_ground
    install = (DEPLOY / "ground/install.ps1").read_text()
    for needle in ("requirements.txt", "import krakenlink.ground.app", "PYTHONPATH", "3.9", "'-3'"):
        assert needle in install
    flash = (DEPLOY / "esp/flash.ps1").read_text()
    for needle in ("Get-FileHash", "esptool==4.8.1", "write_flash 0x0", "find_port.py", "folder named air or ground", "hold BOOT, tap RESET"):
        assert needle in flash
    deploy = (DEPLOY / "krakenimage/deploy.ps1").read_text()
    for needle in ("scp -r", "krakenlink.incoming", "bridge.toml", "install.sh", "OpenSSH"):
        assert needle in deploy
    assert "rsync" not in deploy
    # PowerShell 5.1 mangles embedded double quotes in native-command arguments.
    remote = deploy.split("$remote = @(", 1)[1].split(") -join", 1)[0]
    assert '"' not in remote


def test_ground_app_reads_config_as_utf8():
    assert "read_text(encoding='utf-8')" in (SRC / "krakenlink/ground/app.py").read_text()


def test_windows_docs():
    assert "run_ground.bat" in (DEPLOY / "ground/README.md").read_text()
    assert "flash.bat" in (DEPLOY / "esp/README.md").read_text()
    assert "deploy.bat" in (DEPLOY / "krakenimage/README.md").read_text()
    overview = (ROOT / "dist/README.md").read_text()
    for needle in ("deploy.bat", "install.bat", "run_ground.bat", "flash.bat"):
        assert needle in overview


def test_find_port_script_filters_ch343(monkeypatch, capsys):
    pytest.importorskip("serial")
    spec = importlib.util.spec_from_file_location("find_port_under_test", DEPLOY / "esp/find_port.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ports = [SimpleNamespace(device="COM7", vid=0x1A86), SimpleNamespace(device="COM4", vid=0x303A),
             SimpleNamespace(device="COM2", vid=0x1A86), SimpleNamespace(device="COM1", vid=None)]
    monkeypatch.setattr(mod, "comports", lambda: ports)
    assert mod.main() == 0
    assert capsys.readouterr().out.split() == ["COM2", "COM7"]
    monkeypatch.setattr(mod, "comports", lambda: ports[1:2])
    assert mod.main() == 1
    assert "No ESP32 port found" in capsys.readouterr().err


needs_pwsh = pytest.mark.skipif(PWSH is None, reason="pwsh not installed; PowerShell runtime checks skipped")


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    out = tmp_path_factory.mktemp("winbundle") / "dist"
    assert run([str(SRC / "make_dist.sh"), "--out", str(out)]).returncode == 0
    return out


def pwsh(script, *args, **kwargs):
    return run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(script), *args], **kwargs)


@needs_pwsh
def test_ps1_parse_without_errors(bundle):
    for rel in DIST_PS1:
        cmd = ("$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$null,[ref]$e); "
               "if ($e) { $e | ForEach-Object { $_.ToString() }; exit 1 }" % (bundle / rel))
        result = run([PWSH, "-NoProfile", "-NonInteractive", "-Command", cmd])
        assert result.returncode == 0, (rel, result.stdout, result.stderr)


@needs_pwsh
def test_ps1_help(bundle):
    for rel in DIST_PS1:
        result = pwsh(bundle / rel, "-Help")
        assert result.returncode == 0 and "Usage" in result.stdout, (rel, result.stdout, result.stderr)


@needs_pwsh
def test_run_ground_ps1_without_venv(bundle):
    result = pwsh(bundle / "ground/run_ground.ps1", "-NoBrowser")
    assert result.returncode != 0 and "Missing .venv" in result.stderr


@needs_pwsh
def test_flash_ps1_refuses_other_folder(bundle, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    shutil.copy(bundle / "esp/air/flash.ps1", other / "flash.ps1")
    result = pwsh(other / "flash.ps1")
    assert result.returncode == 2 and "folder named air or ground" in result.stderr
