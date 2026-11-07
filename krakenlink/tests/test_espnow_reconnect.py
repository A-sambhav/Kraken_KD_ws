from krakenlink.bridge.transports.espnow_uart import ESPNowUARTTransport
from krakenlink.proto.frame import cobs_encode, encode_frame


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeSerial:
    def __init__(self, incoming=b'', read_error=None, write_error=None):
        self.incoming = bytearray(incoming)
        self.read_error = read_error
        self.write_error = write_error
        self.closed = False
        self.writes = []

    def read(self, size):
        if self.read_error:
            error, self.read_error = self.read_error, None
            raise error
        data = bytes(self.incoming[:size])
        del self.incoming[:size]
        return data

    def write(self, data):
        if self.write_error:
            raise self.write_error
        self.writes.append(data)
        return len(data)

    def close(self):
        self.closed = True


def test_reconnect_retries_until_device_returns_and_receives_frames():
    clock = FakeClock()
    device = FakeSerial(read_error=OSError('unplugged'))
    attempts = []

    def factory(*_args, **_kwargs):
        attempts.append(clock())
        if clock() < 3.0:
            raise OSError('unplugged')
        return device

    transport = ESPNowUARTTransport('fake', serial_instance=device, serial_factory=factory,
                                    reopen_interval=2, clock=clock)
    assert transport.recv() is None
    assert device.closed

    frame = encode_frame(0x20, 1, b'reconnected')
    while clock() < 5.2:
        previous_reopen_at = transport.reopen_at
        was_pending = transport.serial is None and clock() < previous_reopen_at
        assert transport.recv() is None
        if was_pending:
            assert transport.send(frame) is False
        if was_pending:
            assert transport.reopen_at == previous_reopen_at
        if transport.serial is device:
            break
        clock.advance(0.005)

    assert transport.serial is device
    assert clock() - 3.0 <= transport.reopen_interval
    device.incoming.extend(cobs_encode(frame) + b'\0')
    assert transport.recv() == frame
    assert attempts


def test_bad_packet_is_dropped_without_reopening_port():
    clock = FakeClock()
    frame = encode_frame(0x20, 2, b'valid')
    serial = FakeSerial(b'\x05x\0' + cobs_encode(frame) + b'\0')
    transport = ESPNowUARTTransport('fake', serial_instance=serial, clock=clock)

    assert transport.recv() == frame
    assert transport.bad == 1
    assert transport.serial is serial
    assert not serial.closed


def test_write_error_closes_and_schedules_reopen():
    clock = FakeClock()
    serial = FakeSerial(write_error=TimeoutError('write timeout'))
    transport = ESPNowUARTTransport('fake', serial_instance=serial, reopen_interval=2, clock=clock)

    assert transport.send(b'frame') is False
    assert serial.closed
    assert transport.serial is None
    assert transport.reopen_at == 2
    assert transport.bad == 1
    assert transport.recv() is None
    assert transport.reopen_at == 2
