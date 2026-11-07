"""Ground MAVLink TUNNEL client using pymavlink when installed."""
from ...bridge.transports.base import Transport

class GroundMAVLinkTransport(Transport):
    def __init__(self,connection,target_system=1,target_component=191,payload_type=0xA700,connection_factory=None,mavutil_module=None):
        if mavutil_module is None:
            from pymavlink import mavutil as mavutil_module
        self.mavutil=mavutil_module; self.conn=(connection_factory(connection,source_system=255,source_component=190) if connection_factory else mavutil_module.mavlink_connection(connection,source_system=255,source_component=190))
        self.target_system=target_system; self.target_component=target_component; self.payload_type=payload_type; self.seq=0; self.last_hb=0; self.rx=0; self.tx=0; self.bad=0; self.global_position_int=None
    def send(self,frame):
        try:
            import time
            if len(frame)>128:return False
            now=time.monotonic()
            if now-self.last_hb>=1:
                self.conn.mav.heartbeat_send(self.mavutil.mavlink.MAV_TYPE_GCS,self.mavutil.mavlink.MAV_AUTOPILOT_INVALID,0,0,0); self.last_hb=now
            self.conn.mav.tunnel_send(self.target_system,self.target_component,self.payload_type,len(frame),bytes(frame)+bytes(128-len(frame))); self.tx+=1; return True
        except Exception:self.bad+=1; return False
    def recv(self):
        try:
            for _ in range(200):
                m=self.conn.recv_match(blocking=False)
                if m is None:return None
                typ=m.get_type()
                if typ=='GLOBAL_POSITION_INT':self.global_position_int=m
                if typ=='TUNNEL' and int(m.payload_type)==self.payload_type:self.rx+=1; return bytes(m.payload[:int(m.payload_length)])
            return None
        except Exception:self.bad+=1; return None
    def stats(self):return {'tx':self.tx,'rx':self.rx,'bad':self.bad}
    def close(self):self.conn.close()
