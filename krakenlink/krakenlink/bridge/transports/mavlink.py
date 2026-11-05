"""MAVLink2 TUNNEL encapsulation (pymavlink is an optional runtime dependency)."""
import time
from .base import Transport
class MAVLinkTransport(Transport):
    def __init__(self,connection,source_system=1,source_component=191,target_system=255,target_component=0,payload_type=0xA700,fc_enabled=False,connection_factory=None,mavutil_module=None,reopen_interval=2.,fc_system=1,fc_component=1,baud=921600):
        self.connection=connection; self.source_system=source_system; self.source_component=source_component; self.target_system=target_system; self.target_component=target_component; self.payload_type=payload_type; self.fc_enabled=fc_enabled; self.fc_reader=None; self.connection_factory=connection_factory; self.fc_system=fc_system; self.fc_component=fc_component; self.baud=baud; self.reopen_interval=reopen_interval; self.reopen_at=0.; self.conn=None
        if mavutil_module is not None:self.mavutil=mavutil_module
        else:
            from pymavlink import mavutil
            self.mavutil=mavutil
        try:self._open()
        except Exception:self.conn=None; self.reopen_at=time.monotonic()+self.reopen_interval
        self.last_hb=0; self.txbuf=100; self.tx=0; self.rx=0; self.bad=0
    def _open(self):
        if self.connection_factory:self.conn=self.connection_factory(self.connection,source_system=self.source_system,source_component=self.source_component,baud=self.baud)
        else:self.conn=self.mavutil.mavlink_connection(self.connection,source_system=self.source_system,source_component=self.source_component,baud=self.baud)
        self.reopen_at=0.
        if self.fc_enabled:
            for mid in (33,74,24):
                try:self.conn.mav.command_long_send(self.fc_system,self.fc_component,self.mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,0,mid,500000,0,0,0,0,0)
                except Exception:pass
    def _reopen(self):
        if self.reopen_at and time.monotonic()<self.reopen_at:return False
        try:self._open(); return True
        except Exception:self.reopen_at=time.monotonic()+self.reopen_interval; return False
    def _lost(self):
        try:self.conn.close()
        except Exception:pass
        self.conn=None; self.reopen_at=time.monotonic()+self.reopen_interval
    def send(self,frame):
        if self.conn is None and not self._reopen():return False
        now=time.monotonic()
        if len(frame)>128:return False
        payload=bytes(frame)+bytes(128-len(frame))
        try:
            if now-self.last_hb>=1:
                self.conn.mav.heartbeat_send(self.mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,self.mavutil.mavlink.MAV_AUTOPILOT_INVALID,0,0,0); self.last_hb=now
            self.conn.mav.tunnel_send(self.target_system,self.target_component,self.payload_type,len(frame),payload); self.tx+=1; return True
        except (OSError,IOError): self.bad+=1; self._lost(); return False
        except Exception:return False
    def recv(self):
        try:
            if self.conn is None:
                if not self._reopen():return None
            # Drain non-TUNNEL traffic so a busy FC port never backs up behind one read per loop.
            for _ in range(200):
                msg=self.conn.recv_match(blocking=False)
                if msg is None:return None
                typ=msg.get_type()
                if typ=='RADIO_STATUS':self.txbuf=int(getattr(msg,'txbuf',100))
                if typ in ('GLOBAL_POSITION_INT','VFR_HUD','GPS_RAW_INT') and self.fc_reader:
                    self.fc_reader.handle_message(msg)
                if typ=='TUNNEL' and int(msg.payload_type)==self.payload_type:
                    self.rx+=1; return bytes(msg.payload[:int(msg.payload_length)])
            return None
        except (OSError,IOError):self.bad+=1; self._lost(); return None
        except Exception:self.bad+=1; return None
    def close(self):
        try:self.conn.close()
        except Exception:pass
    def stats(self):return {'tx':self.tx,'rx':self.rx,'bad':self.bad,'txbuf':self.txbuf}
