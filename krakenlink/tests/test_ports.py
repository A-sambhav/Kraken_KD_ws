from krakenlink.tools.ports import detect_ports


def test_detects_air_and_cube_if00_only(tmp_path):
    names = ['usb-1a86_USB_Serial-if00', 'usb-Espressif_USB_JTAG-if00', 'usb-CubeOrange-if02', 'usb-CubeOrange-if00']
    for n in names:
        (tmp_path / n).symlink_to('/dev/null')
    air, cube = detect_ports(tmp_path)
    assert air.endswith('usb-1a86_USB_Serial-if00')
    assert cube.endswith('usb-CubeOrange-if00')


def test_missing_ports(tmp_path):
    assert detect_ports(tmp_path) == ('', '')
    assert detect_ports(tmp_path / 'missing') == ('', '')


from types import SimpleNamespace

import krakenlink.tools.ports as ports_mod
from krakenlink.tools.ports import find_esp_ports


def fake(device, vid):
    return SimpleNamespace(device=device, vid=vid)


FAKE = [fake('COM9', 0x303A), fake('COM3', 0x0403), fake('COM5', 0x1A86), fake('COM1', None)]


def test_find_esp_ports_filters_vid_and_sorts():
    assert find_esp_ports(FAKE) == ['COM5', 'COM9']
    assert find_esp_ports([]) == []


def test_ports_cli_exit_codes(monkeypatch, capsys):
    import serial.tools.list_ports as lp
    monkeypatch.setattr(lp, 'comports', lambda: FAKE)
    assert ports_mod.main(['--esp']) == 0
    assert capsys.readouterr().out.split() == ['COM5', 'COM9']
    monkeypatch.setattr(lp, 'comports', lambda: [fake('COM3', 0x0403)])
    assert ports_mod.main([]) == 1
    assert 'No ESP32 port found' in capsys.readouterr().err
