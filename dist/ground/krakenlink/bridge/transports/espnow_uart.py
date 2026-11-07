"""COBS delimited UART transport for an ESP-NOW forwarder."""
import threading
from ...proto.frame import cobs_encode,cobs_decode
from .base import Transport
class ESPNowUARTTransport(Transport):
    def __init__(self,port,baudrate=460800,serial_instance=None,reopen_interval=2.,serial_factory=None):
        self.port=port; self.baudrate=baudrate; self.serial_factory=serial_factory; self.reopen_interval=reopen_interval; self.reopen_at=0.
        if serial_instance is None:
            serial_instance=self._new_serial()
        self.serial=serial_instance; self.buf=bytearray(); self.tx=0; self.rx=0; self.bad=0; self.local_status=None
        self.tx_lock=threading.Lock()  # ground: GUI threads and the pump thread both send
    def send(self,frame):
        with self.tx_lock:
            try:self._ensure(); self.serial.write(cobs_encode(frame)+b'\0'); self.tx+=1; return True
            except Exception:self.bad+=1; self._lost(); return False
    def recv(self):
        try:
            self._ensure(); data=self.serial.read(4096)
            if data:self.buf.extend(data)
            i=self.buf.find(0)
            if i<0:return None
            packet=bytes(self.buf[:i]); del self.buf[:i+1]
            if not packet:return None
            result=cobs_decode(packet)
            if len(result)>=8 and result[0]==0xA7 and result[2]==0x7F:
                payload=result[6:-2]
                if result[3] in (22,31) and len(result)==result[3]+8:
                    self.local_status={'paired':bool(payload[22]) if len(payload)>=23 else False,
                    'peer_mac':':'.join(f'{b:02x}' for b in payload[23:29]) if len(payload)>=29 else None,
                    'counters':{'tx':int.from_bytes(payload[0:4],'little'),'tx_fail':int.from_bytes(payload[4:8],'little'),
                        'rx':int.from_bytes(payload[8:12],'little'),'rx_bad':int.from_bytes(payload[12:16],'little'),
                        'uart_bad':int.from_bytes(payload[16:20],'little'),'tx_nopeer':int.from_bytes(payload[29:31],'little') if len(payload)>=31 else 0}}
                self.rx+=1; return None
            self.rx+=1; return result
        except Exception:self.bad+=1; self._lost(); return None
    def _new_serial(self):
        if self.serial_factory:return self.serial_factory(self.port,baudrate=self.baudrate,timeout=0)
        import serial
        return serial.Serial(self.port,baudrate=self.baudrate,timeout=0)
    def _ensure(self):
        if self.serial is None:
            if self.reopen_at and __import__('time').monotonic()<self.reopen_at:raise OSError('reconnect pending')
            self.serial=self._new_serial(); self.reopen_at=0.
    def _lost(self):
        try:self.serial.close()
        except Exception:pass
        self.serial=None; self.reopen_at=__import__('time').monotonic()+self.reopen_interval; self.buf.clear()
    def stats(self):
        result={'tx':self.tx,'rx':self.rx,'bad':self.bad,'local_status':self.local_status}
        if self.local_status is not None: result.update(self.local_status)
        return result
    def close(self):
        if self.serial:self.serial.close()
