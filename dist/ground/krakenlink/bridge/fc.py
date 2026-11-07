"""Optional pymavlink FC pose/heading reader."""
import threading,time
from ..proto.messages import PoseMessage
class FCReader:
    def __init__(self,connection,reopen_interval=2.,shared_link=None,baud=921600,source_system=1): self.connection=connection; self.reopen_interval=reopen_interval; self.shared_link=shared_link; self.baud=baud; self.source_system=source_system; self.ok=False; self.pose=None; self.heading=None; self.lock=threading.Lock(); self.running=False
    def start(self):self.running=True; threading.Thread(target=self._run,daemon=True).start()
    def stop(self):self.running=False
    def _run(self):
        if self.shared_link is not None:
            self.shared_link.fc_reader=self
            self.shared_link.fc_enabled=True
            while self.running: time.sleep(.1)
            return
        while self.running:
            try:
                from pymavlink import mavutil
                m=mavutil.mavlink_connection(self.connection,source_system=int(self.source_system),baud=self.baud,autoreconnect=True)
                self.ok=True
                for mid in (33,74,24): m.mav.command_long_send(0,0,mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,0,mid,500000,0,0,0,0,0)
                while self.running:
                    msg=m.recv_match(blocking=True,timeout=1)
                    if msg is None:continue
                    typ=msg.get_type()
                    if typ=='GLOBAL_POSITION_INT':
                        with self.lock:
                            h=msg.hdg if msg.hdg!=65535 else int((self.heading or 0)*100)
                            self.heading=h/100
                            self.pose=PoseMessage(msg.time_boot_ms,msg.lat,msg.lon,int(msg.relative_alt/100),h,0,0,0)
                    elif typ=='VFR_HUD':
                        with self.lock:
                            self.heading=float(msg.heading)
                            if self.pose:self.pose=PoseMessage(self.pose.fc_time_boot_ms,self.pose.lat_e7,self.pose.lon_e7,self.pose.rel_alt_dm,int(self.heading*100),int(msg.groundspeed*100),self.pose.fix_type,self.pose.sats)
                    elif typ=='GPS_RAW_INT' and self.pose:
                        with self.lock:self.pose=PoseMessage(self.pose.fc_time_boot_ms,self.pose.lat_e7,self.pose.lon_e7,self.pose.rel_alt_dm,self.pose.heading_cdeg,self.pose.groundspeed_cms,int(msg.fix_type),int(msg.satellites_visible))
            except Exception:self.ok=False
            time.sleep(self.reopen_interval)
    def snapshot(self):
        with self.lock:return self.pose,self.heading
    def handle_message(self,msg):
        typ=msg.get_type()
        if typ=='GLOBAL_POSITION_INT':
            with self.lock:
                h=msg.hdg if msg.hdg!=65535 else int((self.heading or 0)*100)
                self.heading=h/100
                self.pose=PoseMessage(msg.time_boot_ms,msg.lat,msg.lon,int(msg.relative_alt/100),h,0,0,0)
        elif typ=='VFR_HUD':
            with self.lock:
                self.heading=float(msg.heading)
                if self.pose:self.pose=PoseMessage(self.pose.fc_time_boot_ms,self.pose.lat_e7,self.pose.lon_e7,self.pose.rel_alt_dm,int(self.heading*100),int(msg.groundspeed*100),self.pose.fix_type,self.pose.sats)
        elif typ=='GPS_RAW_INT':
            with self.lock:
                if self.pose:self.pose=PoseMessage(self.pose.fc_time_boot_ms,self.pose.lat_e7,self.pose.lon_e7,self.pose.rel_alt_dm,self.pose.heading_cdeg,self.pose.groundspeed_cms,int(msg.fix_type),int(msg.satellites_visible))
