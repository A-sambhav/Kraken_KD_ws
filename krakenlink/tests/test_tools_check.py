import json
import os
import time
from pathlib import Path

from krakenlink.sim.__main__ import KrakenSimulator
from krakenlink.proto.frame import cobs_encode, encode_frame
from krakenlink.tools.check import check_usb, check_doa, check_settings, check_air


def test_usb_check_pass_and_fail(tmp_path):
    for i in range(5):
        d = tmp_path / f'usb{i}'; d.mkdir(); (d/'idVendor').write_text('0bda'); (d/'idProduct').write_text('2838')
    assert check_usb(tmp_path)[0] == 'PASS'
    (tmp_path/'usb4'/'idProduct').write_text('0000')
    assert check_usb(tmp_path)[0] == 'FAIL'


def test_doa_check_uses_simulator_parser(tmp_path):
    sim = KrakenSimulator(tmp_path)
    sim.doa_path.write_text(sim._line())
    assert check_doa(sim.doa_path)[0] == 'PASS'
    sim.doa_path.write_text('partial')
    assert check_doa(sim.doa_path)[0] == 'FAIL'


def test_settings_check_pass_and_warn(tmp_path):
    p = tmp_path/'settings.json'
    p.write_text(json.dumps({'doa_data_format':'Kraken App'}))
    assert check_settings(p)[0] == 'PASS'
    p.write_text(json.dumps({'doa_data_format':'other'}))
    assert check_settings(p)[0] == 'WARN'


class FakeSerial:
    def __init__(self, *_args, **_kwargs):
        payload = bytearray(31); payload[22] = 1; payload[23:29] = bytes.fromhex('010203040506')
        self.data = bytearray(cobs_encode(encode_frame(0x7f, 0, payload)) + b'\0')
    def read(self, _n):
        out = bytes(self.data); self.data.clear(); return out
    def close(self): pass


def test_air_check_status_pass_and_fail(tmp_path):
    port = tmp_path/'air'; port.touch()
    assert check_air(port, lambda *_a, **_k: FakeSerial(), timeout=.01)[0] == 'PASS'
    assert check_air(port, lambda *_a, **_k: type('Empty', (), {'read':lambda s,n:b'', 'close':lambda s:None})(), timeout=.01)[0] == 'FAIL'
