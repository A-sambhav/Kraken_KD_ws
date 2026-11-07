"""Run the KrakenLink bridge: python -m krakenlink.bridge --config path.toml"""
import argparse, json, logging, os, platform, struct, threading, time, traceback
from pathlib import Path
from ..proto.frame import Frame, decode_frame
from ..proto.messages import *
from ..proto.csv_parser import spectrum_bins
from ..proto.validate import DOA_METHODS
from .kraken_io import KrakenIO
from .commands import CommandWorker
from .link import LinkMonitor
from .logger import DOALogger
from .ratelimit import TokenBucket, PRIORITY

def load_config(path):
    raw=Path(path).read_bytes()
    try:
        import tomllib
        return tomllib.loads(raw.decode())
    except ImportError: pass
    import tomli
    return tomli.loads(raw.decode())

class Bridge:
    def __init__(self,cfg,transport=None,logger=None,log=None):
        self.cfg=cfg; self.log=log or logging.getLogger('krakenlink.bridge'); k=cfg.get('kraken',{}); self.started=time.monotonic()
        self.kraken=KrakenIO(k.get('share',str(Path.home()/'krakensdr_doa/krakensdr_doa/_share')),poll_interval=k.get('poll_interval',.05),partial_retry=k.get('partial_retry',.02),stale_s=k.get('stale_s',2),down_s=k.get('down_s',10),consumed_timeout=k.get('consumed_timeout',5),logger=self.log.warning)
        self.transport=transport or self._transport(cfg.get('transport',{})); self.csv=logger or DOALogger(**cfg.get('logging',{})); self.bucket=TokenBucket(cfg.get('rate',{}).get('bytes_per_second',625),transport=cfg.get('transport',{}).get('type','mavlink'),logger=self.log)
        self.link=LinkMonitor(); self.seq=0; self.rx_bad=0; self.running=False; self.fc=None; self.last_doas={}; self.last_doa_send={}; self.last_spec_send=0.; self.latest_samples={}; self.last_status=0; self.last_hb=0
        self.pending=[]; self.pending_order=0; self.pressure_toggle=0
        cc=cfg.get('commands',{}); self.commands=CommandWorker(self.kraken,self._send_ack,calibration_timeout=cc.get('calibration_timeout',30),consumed_timeout=k.get('consumed_timeout',5),daq_fs=cfg.get('daq_fs',2400000),retune_vfo_policy=cc.get('retune_vfo_policy','reject'),calib_settle_s=cc.get('calib_settle_s',1.0))
        fc_cfg=cfg.get('fc',{}).get('connection')
        if fc_cfg and cfg.get('transport',{}).get('type')!='mavlink':
            try:
                from .fc import FCReader
                self.fc=FCReader(fc_cfg,baud=cfg.get('fc',{}).get('baud',cfg.get('transport',{}).get('baud',921600))); self.fc.start()
            except Exception:self.log.exception('FC reader unavailable')
        elif fc_cfg and cfg.get('transport',{}).get('type')=='mavlink':
            try:
                from .fc import FCReader
                self.fc=FCReader(fc_cfg,shared_link=self.transport,baud=cfg.get('transport',{}).get('baud',921600)); self.fc.start()
            except Exception:self.log.exception('FC reader unavailable')
    def _transport(self,c):
        typ=c.get('type','loopback')
        if typ=='loopback':
            from .transports.loopback import LoopbackTransport
            return LoopbackTransport(c.get('host','127.0.0.1'),c.get('port',14560),c.get('bind_host','127.0.0.1'),c.get('bind_port',14561))
        if typ=='mavlink':
            from .transports.mavlink import MAVLinkTransport
            return MAVLinkTransport(c['connection'],source_system=c.get('source_system',1),source_component=c.get('source_component',191),target_system=c.get('target_system',255),target_component=c.get('target_component',0),fc_enabled=bool(self.cfg.get('fc',{}).get('connection')),baud=c.get('baud',921600))
        if typ=='espnow_uart':
            from .transports.espnow_uart import ESPNowUARTTransport
            return ESPNowUARTTransport(c['port'],c.get('baud',460800))
        raise ValueError('unknown transport '+typ)
    def _frame(self,typ,msg):
        b=msg.encode() if hasattr(msg,'encode') else bytes(msg); f=Frame(typ,self.seq,b); self.seq=(self.seq+1)&65535; return f.encode()
    def _send_ack(self,ack):
        self._send('ACK',ACK,ack)
    def _send(self,kind,typ,msg,vfo=0):
        payload=msg.encode() if hasattr(msg,'encode') else bytes(msg)
        self.pending.append((PRIORITY[kind],self.pending_order,vfo,kind,typ,payload)); self.pending_order+=1
        return True
    def _flush(self):
        # Only this scheduling cycle is retained: denied frames are dropped.
        pending=self.pending; self.pending=[]
        pending.sort(key=lambda x:(x[0],x[2] if x[3]=='DOA' else x[1]))
        for _,_,_,kind,typ,payload in pending:
            stats=self.transport.stats(); txbuf=stats.get('txbuf',100)
            if txbuf<25 and kind not in ('ACK','STATUS'):continue
            if txbuf<50 and kind in ('DOA','SPECTRUM','POSE'):
                self.pressure_toggle+=1
                if self.pressure_toggle%2:continue
            frame=Frame(typ,self.seq,payload).encode()
            if self.bucket.allow(len(frame)):
                self.seq=(self.seq+1)&65535
                self.transport.send(frame)
    def _receive(self):
        while True:
            raw=self.transport.recv()
            if raw is None:break
            try:
                frame=decode_frame(raw); self.link.received(True)
                if frame.type==PING:
                    p=PingMessage.decode(frame.payload); self._send('PONG',PONG,PongMessage(p.ground_time_ms,int((time.monotonic()-self.started)*1000)&0xffffffff,self.rx_bad&65535))
                elif frame.type==CMD:
                    command=CommandMessage.decode(frame.payload); self.commands.handle(command)
                    if command.opcode==8 and self.commands.cache.get(command.cmd_id, None) and self.commands.cache[command.cmd_id].result==1:
                        self._settings_snapshot(command.cmd_id)
            except Exception:self.rx_bad=(self.rx_bad+1)&65535
    def _status(self):
        try:s=self.kraken.settings()
        except Exception:s={}
        state=self.kraken.state(); ks={'OK':0,'STALE':1,'DOWN':3}.get(state,3)
        if self.commands.calibrating:ks=2
        center=int(float(s.get('center_freq',0))*1e6); gain=round(float(s.get('uniform_gain',0))*10)
        method=DOA_METHODS.index(s.get('doa_method','Bartlett')) if s.get('doa_method','Bartlett') in DOA_METHODS else 0
        age=65535 if self.kraken.last_data_mono is None else min(65535,int((time.monotonic()-self.kraken.last_data_mono)*1000))
        last=self.commands.last_ack or AckMessage(0,0,0,0)
        return StatusMessage(1 if self.commands.busy else 2 if state=='DOWN' else 0,ks,self.link.update(),center,gain,int(s.get('active_vfos',0)),method,int(bool(s.get('en_doa',False))),age,0,0,int(time.monotonic()-self.started),last.cmd_id,last.result,self.bucket.dropped,self.rx_bad,1 if self.csv.ok else 0)
    def _settings_snapshot(self,cmd_id):
        s=self.kraken.settings(); rates=getattr(self.kraken,'telemetry_rates',{})
        method=DOA_METHODS.index(s.get('doa_method','Bartlett')) if s.get('doa_method','Bartlett') in DOA_METHODS else 0
        out=SettingsMessage.globals(cmd_id,round(float(s.get('center_freq',0))*1e6),round(float(s.get('uniform_gain',0))*10),method,0 if str(s.get('ant_arrangement','UCA')).upper()=='UCA' else 1,round(float(s.get('ant_spacing_meters',0))*1000),int(bool(s.get('en_doa'))),int(s.get('active_vfos',1)),int(s.get('output_vfo',0)),int(s.get('dsp_decimation',1)),int(s.get('doa_data_format')=='Kraken App'),rates.get('telem_doa_hz_x10',50),rates.get('telem_spec_hz_x10',10))
        self._send('SETTINGS',SETTINGS,out)
        for part in (1,2):
            vals=[]
            for idx in range((part-1)*8,part*8):
                vals.append((int(s.get(f'vfo_freq_{idx}',0)),int(s.get(f'vfo_bw_{idx}',0)),int(s.get(f'vfo_squelch_{idx}',0))))
            self._send('SETTINGS',SETTINGS,SettingsMessage.vfos(cmd_id,part,vals))
    def _samples(self,samples):
        for idx,s in enumerate(samples):
            self.latest_samples[idx]=s
            self.csv.log_sample(s,idx,self.fc.snapshot()[1] if self.fc else None,self.link.state)
    def _schedule_telemetry(self):
        settings=self.kraken.settings(); rate_cfg=self.cfg.get('rate',{}); rates=getattr(self.kraken,'telemetry_rates',{})
        doa_hz=rates.get('telem_doa_hz_x10',round(float(rate_cfg.get('doa_hz',5))*10))/10
        spec_hz=rates.get('telem_spec_hz_x10',round(float(rate_cfg.get('spectrum_hz',1))*10))/10
        active=max(0,min(16,int(settings.get('active_vfos',len(self.latest_samples)))))
        output=int(settings.get('output_vfo',0)); output=0 if output==255 else output
        now=time.monotonic()
        for idx,s in sorted(self.latest_samples.items()):
            if idx>=active:continue
            due=doa_hz>0 and (idx not in self.last_doa_send or now-self.last_doa_send[idx]>=1/doa_hz)
            if due:
                heading=None; pose=None
                if self.fc:pose,heading=self.fc.snapshot()
                flags=(1 if heading is not None else 0)|(2 if self.kraken.state()!='OK' else 0)|(4 if self.commands.calibrating else 0)
                doa=DOAMessage(idx,flags,s.timestamp_ms,int((s.bearing_deg%360)*100),max(0,min(99,round(s.confidence))),min(0,round(s.rssi_db*10)),s.freq_hz,max(0,min(65535,s.latency_ms)),int((heading or 0)*100)%36000)
                self._send('DOA',DOA,doa,idx)
                self.last_doa_send[idx]=now
            if idx==output and spec_hz>0 and now-self.last_spec_send>=1/spec_hz:
                peak,bins=spectrum_bins(s.spectrum); self._send('SPECTRUM',SPECTRUM,SpectrumMessage(idx,s.timestamp_ms,peak,bins),idx); self.last_spec_send=now
    def step(self):
        self._receive(); samples=self.kraken.poll()
        if samples:self._samples(samples)
        if self.latest_samples:self._schedule_telemetry()
        now=time.monotonic()
        if now-self.last_status>=1:
            self._send('STATUS',STATUS,self._status()); self.last_status=now
        if self.fc and now-self.last_hb>=.5:
            pose,_=self.fc.snapshot()
            if pose:self._send('POSE',POSE,pose)
            self.last_hb=now
        self._flush()
    def run(self):
        self.running=True
        try:
            try:self.kraken.ensure_format()
            except Exception:self.log.exception('Kraken startup format check failed; retrying in loop')
            while self.running:
                try:self.step()
                except Exception:self.log.error('bridge loop failed:\n%s',traceback.format_exc()); time.sleep(1)
                time.sleep(self.kraken.poll_interval)
        finally:self.close()
    def close(self):
        self.running=False
        try:self.csv.close()
        except Exception:self.log.exception('logger close failed')
        try:self.transport.close()
        except Exception:pass
        if self.fc:self.fc.stop()

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--config',required=True); args=ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    cfg=load_config(args.config)
    while True:
        bridge=None
        try:bridge=Bridge(cfg); bridge.run()
        except KeyboardInterrupt:break
        except Exception:logging.getLogger('krakenlink.bridge').exception('daemon restart after uncaught loop error')
        if bridge is None:time.sleep(5)
        else:time.sleep(1)
if __name__=='__main__':main()
