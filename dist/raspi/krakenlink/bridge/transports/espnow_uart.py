"""COBS delimited UART transport for an ESP-NOW forwarder."""
import threading
import time

from ...proto.frame import cobs_encode, cobs_decode
from .base import Transport


class ESPNowUARTTransport(Transport):
    def __init__(self, port, baudrate=460800, serial_instance=None,
                 reopen_interval=2., serial_factory=None, write_timeout=1.0,
                 clock=time.monotonic):
        self.port = port
        self.baudrate = baudrate
        self.serial_factory = serial_factory
        self.reopen_interval = reopen_interval
        self.write_timeout = write_timeout
        self.clock = clock
        self.reopen_at = 0.
        self.serial = serial_instance
        self.buf = bytearray()
        self.tx = 0
        self.rx = 0
        self.bad = 0
        self.local_status = None
        self.tx_lock = threading.Lock()
        if self.serial is None:
            self._ensure()

    def send(self, frame):
        with self.tx_lock:
            try:
                if not self._ensure():
                    return False
                self.serial.write(cobs_encode(frame) + b'\0')
                self.tx += 1
                return True
            except Exception:
                self.bad += 1
                self._lost()
                return False

    def recv(self):
        try:
            if not self._ensure():
                return None
            data = self.serial.read(4096)
            if data:
                self.buf.extend(data)
        except Exception:
            self.bad += 1
            self._lost()
            return None

        while True:
            i = self.buf.find(0)
            if i < 0:
                return None
            packet = bytes(self.buf[:i])
            del self.buf[:i + 1]
            if not packet:
                continue
            try:
                result = cobs_decode(packet)
            except Exception:
                self.bad += 1
                continue
            if len(result) >= 8 and result[0] == 0xA7 and result[2] == 0x7F:
                payload = result[6:-2]
                if result[3] in (22, 31) and len(result) == result[3] + 8:
                    self.local_status = {
                        'paired': bool(payload[22]) if len(payload) >= 23 else False,
                        'peer_mac': ':'.join(f'{b:02x}' for b in payload[23:29]) if len(payload) >= 29 else None,
                        'counters': {
                            'tx': int.from_bytes(payload[0:4], 'little'),
                            'tx_fail': int.from_bytes(payload[4:8], 'little'),
                            'rx': int.from_bytes(payload[8:12], 'little'),
                            'rx_bad': int.from_bytes(payload[12:16], 'little'),
                            'uart_bad': int.from_bytes(payload[16:20], 'little'),
                            'tx_nopeer': int.from_bytes(payload[29:31], 'little') if len(payload) >= 31 else 0,
                        },
                    }
                self.rx += 1
                continue
            self.rx += 1
            return result

    def _new_serial(self):
        if self.serial_factory:
            return self.serial_factory(self.port, baudrate=self.baudrate, timeout=0)
        import serial
        return serial.Serial(self.port, baudrate=self.baudrate, timeout=0,
                             write_timeout=self.write_timeout)

    def _ensure(self):
        if self.serial is not None:
            return True
        now = self.clock()
        if self.reopen_at and now < self.reopen_at:
            return False
        try:
            self.serial = self._new_serial()
            self.reopen_at = 0.
            return True
        except Exception:
            self.serial = None
            self.reopen_at = self.clock() + self.reopen_interval
            return False

    def _lost(self):
        serial = self.serial
        self.serial = None
        if serial is not None:
            try:
                serial.close()
            except Exception:
                pass
        self.reopen_at = self.clock() + self.reopen_interval
        self.buf.clear()

    def stats(self):
        result = {'tx': self.tx, 'rx': self.rx, 'bad': self.bad, 'local_status': self.local_status}
        if self.local_status is not None:
            result.update(self.local_status)
        return result

    def close(self):
        if self.serial:
            self.serial.close()
            self.serial = None
