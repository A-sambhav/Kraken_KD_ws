"""Transport-independent ground link decoder, metrics, history and state."""
import collections
import time
from ..proto.frame import decode_frame, FrameError, Frame
from ..proto.messages import (DOA, SPECTRUM, STATUS, POSE, SETTINGS, ACK, PONG,
    DOAMessage, SpectrumMessage, StatusMessage, PoseMessage, SettingsMessage,
    AckMessage, PongMessage, decode_message)

class GroundLink:
    LOST, UP, DEGRADED = 2, 0, 1
    def __init__(self, clock=time.monotonic, wall_clock=time.time, history_s=300):
        self.clock, self.wall_clock, self.history_s = clock, wall_clock, history_s
        self.state=self.LOST; self.last_rx=None; self.last_good_doa=None; self.rx_bad=0
        self.rx_counts=collections.Counter(); self.seq_last=None; self.seq_gaps=0; self.seq_expected=0
        self.frames=collections.deque(); self.bytes=collections.deque(); self.samples=collections.defaultdict(collections.deque)
        self.spectrum=None; self.status=None; self.pose=None; self.settings_parts={}; self.settings=None
        self.rtt_samples=collections.deque(); self.rtt_ms=None; self.pending_ping={}; self.switch_advised=False
        self._loss_windows=collections.deque(); self._window_start=None; self._window_good=0; self._window_lost=0; self._bad_windows=0
        self.rtt_accepted={}
        self.ping_seq=0
    @property
    def link_age(self): return float('inf') if self.last_rx is None else max(0,self.clock()-self.last_rx)
    @property
    def loss_pct(self):
        self._trim_metrics(); return 100*self.seq_gaps/max(1,self.seq_expected) if self.seq_expected else 0.
    @property
    def frames_per_s(self):
        self._trim_metrics(); return len(self.frames)/max(1.,(self.clock()-self.frames[0][0]) if self.frames else 1.)
    @property
    def bytes_per_s(self):
        self._trim_metrics(); return sum(b for _,b in self.bytes)/max(1.,(self.clock()-self.bytes[0][0]) if self.bytes else 1.)
    @property
    def rtt_p95_ms(self):
        a=sorted(x[1] for x in self.rtt_samples); return a[min(len(a)-1,int(.95*(len(a)-1)))] if a else None
    @property
    def last_good_packet(self): return self.last_good_doa
    def _trim_metrics(self):
        now=self.clock()
        for q in (self.frames,self.bytes):
            while q and q[0][0]<now-60:q.popleft()
        for q in self.samples.values():
            while q and q[0]['time']<now-self.history_s:q.popleft()
        while self.rtt_samples and self.rtt_samples[0][0]<now-300:self.rtt_samples.popleft()
    def _seq(self,seq,now):
        if self.seq_last is not None:
            gap=(seq-self.seq_last-1)&0xffff
            if gap<0x8000:
                self.seq_gaps+=gap; self.seq_expected+=gap+1
                if self._window_start is None:self._window_start=now
                self._window_good+=1; self._window_lost+=gap
        else:self.seq_expected+=1; self._window_start=now; self._window_good+=1
        self.seq_last=seq
        if self._window_start is None:self._window_start=now
        if now-self._window_start>=60:
            pct=100*self._window_lost/max(1,self._window_good+self._window_lost)
            self._bad_windows=self._bad_windows+1 if pct>5 else 0
            if self._bad_windows>=3:self.switch_advised=True
            self._window_start=now; self._window_good=self._window_lost=0
    def receive(self, raw):
        now=self.clock()
        try:
            frame=decode_frame(raw); message=decode_message(frame.type,frame.payload)
        except (ValueError,TypeError): self.rx_bad+=1; return None
        self._seq(frame.seq,now); self.last_rx=now; self.rx_counts[frame.type]+=1
        self.frames.append((now,1)); self.bytes.append((now,len(raw))); self.state=self.UP; self._trim_metrics()
        if isinstance(message,DOAMessage):
            item={'time':now,'wall_time':self.wall_clock(),'vfo':message.vfo,'bearing_cdeg':message.bearing_cdeg,'bearing_deg':message.bearing_cdeg/100,'confidence':message.confidence,'rssi_db':message.rssi_ddb/10,'freq_hz':message.freq_hz,'flags':message.flags,'fc_heading_cdeg':message.fc_heading_cdeg}
            self.samples[message.vfo].append(item); self.last_good_doa=item
        elif isinstance(message,SpectrumMessage):self.spectrum=message
        elif isinstance(message,StatusMessage):self.status=message
        elif isinstance(message,PoseMessage):self.pose=message
        elif isinstance(message,SettingsMessage):self._settings(message)
        elif isinstance(message,PongMessage):
            sent=self.pending_ping.pop(message.ground_time_ms,None)
            if sent is not None:
                self.rtt_ms=max(0,(now-sent)*1000); self.rtt_samples.append((now,self.rtt_ms))
        elif isinstance(message,AckMessage) and message.result==0:
            self.rtt_accepted[message.cmd_id]=now
        elif isinstance(message,AckMessage) and message.result in (1,2,3,4):
            sent=self.rtt_accepted.pop(message.cmd_id,None)
            if sent is not None:self.rtt_samples.append((now,(now-sent)*1000))
        if self.rtt_p95_ms is not None and self.rtt_p95_ms>3000:self.switch_advised=True
        return message
    def _settings(self,m):
        parts=self.settings_parts.setdefault(m.cmd_id,{})
        parts[m.part]=m
        if len(parts)==3:
            g=parts[0].body
            import struct
            vals=struct.unpack('<I H B B H B B B B B H H',g)
            settings=dict(zip(('center_freq_hz','gain_x10','doa_method','array_type','array_dim_mm','en_doa','active_vfos','output_vfo','dsp_decimation','doa_data_format_ok','telem_doa_hz_x10','telem_spec_hz_x10'),vals))
            settings['vfos']=[]
            for part in (1,2):
                body=parts[part].body
                settings['vfos'].extend([struct.unpack_from('<IIb',body,i*9) for i in range(8)])
            self.settings=settings; del self.settings_parts[m.cmd_id]
    def update(self,now=None):
        now=self.clock() if now is None else now
        age=float('inf') if self.last_rx is None else now-self.last_rx
        if age>=10:self.state=self.LOST
        elif age>=3:self.state=self.DEGRADED
        return self.state
    def ping(self,seq=None,now=None):
        from ..proto.messages import PingMessage
        now=self.clock() if now is None else now; stamp=int(now*1000)&0xffffffff
        self.pending_ping[stamp]=now
        while len(self.pending_ping)>8:self.pending_ping.pop(next(iter(self.pending_ping)))
        rx=sum(self.rx_counts.values())&0xffff
        if seq is None:
            seq=self.ping_seq; self.ping_seq=(self.ping_seq+1)&0xffff
        return Frame(0x20,seq,PingMessage(stamp,rx).encode()).encode()
