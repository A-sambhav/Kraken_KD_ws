import pytest

from krakenlink.bridge.transports.espnow_uart import ESPNowUARTTransport
from krakenlink.ground.transports.espnow_serial import ESPNowSerialTransport
from krakenlink.proto.frame import cobs_encode, encode_frame


class FakeSerial:
    def __init__(self, data):
        self.data = bytearray(data)

    def read(self, _size):
        data = bytes(self.data)
        self.data.clear()
        return data

    def write(self, _data):
        return 0

    def close(self):
        pass


@pytest.mark.parametrize("transport_type", [ESPNowUARTTransport, ESPNowSerialTransport])
@pytest.mark.parametrize("payload_len", [22, 31])
def test_status_frames_are_local_and_exposed_in_stats(transport_type, payload_len):
    payload = bytearray(payload_len)
    for i in range(5):
        payload[i * 4:i * 4 + 4] = (i + 1).to_bytes(4, "little")
    if payload_len == 31:
        payload[22] = 1
        payload[23:29] = bytes.fromhex("010203040506")
        payload[29:31] = (7).to_bytes(2, "little")
    frame = encode_frame(0x7F, 4, bytes(payload))
    transport = transport_type("fake", serial_instance=FakeSerial(cobs_encode(frame) + b"\0"))

    assert transport.recv() is None
    stats = transport.stats()
    assert stats["paired"] is (payload_len == 31)
    assert stats["peer_mac"] == ("01:02:03:04:05:06" if payload_len == 31 else None)
    assert stats["counters"]["tx"] == 1
    assert stats["counters"]["tx_nopeer"] == (7 if payload_len == 31 else 0)
