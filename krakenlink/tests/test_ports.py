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
