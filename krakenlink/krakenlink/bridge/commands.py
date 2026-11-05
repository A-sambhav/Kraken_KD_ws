"""Serialized command worker implementing ACCEPTED/final acknowledgements."""
import collections, struct, threading, time
from ..proto.validate import validate_command, NackReason
from ..proto.messages import AckMessage

class CommandWorker:
    def __init__(self, kraken, ack_callback=None, calibration_timeout=30., consumed_timeout=5., daq_fs=2_400_000, retune_vfo_policy='reject'):
        self.kraken=kraken; self.send_ack=ack_callback or (lambda ack:None); self.calibration_timeout=calibration_timeout
        self.consumed_timeout=consumed_timeout; self.daq_fs=daq_fs; self.policy=retune_vfo_policy; self.cache=collections.OrderedDict()
        self.lock=threading.RLock(); self.busy=False; self.calibrating=False; self.thread=None; self.last_ack=None; self.write_count=0
    def handle(self, cmd):
        with self.lock:
            cached=self.cache.get(cmd.cmd_id)
            if cached:
                self.cache.move_to_end(cmd.cmd_id); self.send_ack(cached); return cached
            try: settings=self.kraken.settings()
            except Exception: return self._emit(AckMessage(cmd.cmd_id,cmd.opcode,2,7))
            verdict=validate_command(cmd.opcode,cmd.params,settings,daq_fs=self.daq_fs,retune_vfo_policy=self.policy,busy=self.busy)
            if isinstance(verdict,tuple) or hasattr(verdict,'reason'):
                return self._emit(AckMessage(cmd.cmd_id,cmd.opcode,2,int(verdict.reason),getattr(verdict,'detail',0)))
            changes=verdict
            if cmd.opcode==9:
                self.kraken.telemetry_rates=changes; return self._emit(AckMessage(cmd.cmd_id,cmd.opcode,1,0))
            if not changes or all(settings.get(k)==v for k,v in changes.items()): return self._emit(AckMessage(cmd.cmd_id,cmd.opcode,1,0))
            if self.busy: return self._emit(AckMessage(cmd.cmd_id,cmd.opcode,2,6))
            accepted=AckMessage(cmd.cmd_id,cmd.opcode,0,0); self._cache(cmd.cmd_id,accepted); self.send_ack(accepted)
            self.busy=True; self.thread=threading.Thread(target=self._run,args=(cmd,changes,settings),daemon=True); self.thread.start(); return accepted
    def _cache(self,key,val):
        self.cache[key]=val; self.cache.move_to_end(key)
        while len(self.cache)>64:self.cache.popitem(last=False)
    def _emit(self,ack): self._cache(ack.cmd_id,ack); self.last_ack=ack; self.send_ack(ack); return ack
    def _run(self,cmd,changes,old):
        start=time.monotonic(); cal=bool({'center_freq','uniform_gain'}&changes.keys())
        try:
            written,_=self.kraken.apply(changes,timeout=self.consumed_timeout)
            self.write_count+=1
            if written is not None and cal:
                self.calibrating=True; deadline=time.monotonic()+self.calibration_timeout
                center=changes.get('center_freq',old.get('center_freq'))*1_000_000
                window=self.daq_fs/max(1,int(old.get('dsp_decimation',1)))/2
                while time.monotonic()<deadline:
                    for sample in list(self.kraken.samples):
                        if sample.timestamp_ms>int(written*1000) and abs(sample.freq_hz-center)<=window:
                            written=None; break
                    if written is None: break
                    time.sleep(min(self.kraken.poll_interval,.05))
                if written is not None: result,reason=3,10
                else: result,reason=1,0
            else: result,reason=1,0
            # Center retune allowed: Kraken may move out-of-window VFOs.
            detail=0
            if result==1 and cmd.opcode==1 and self.policy=='allow':
                center=changes['center_freq']*1e6; dec=int(old.get('dsp_decimation',1)); limit=self.daq_fs/2/dec
                bad=[i for i in range(int(old.get('active_vfos',1))) if abs(float(old.get(f'vfo_freq_{i}',center))-center)+float(old.get(f'vfo_bw_{i}',100))/2>limit]
                if bad: result,reason,detail=4,11,bad[0]
            ack=AckMessage(cmd.cmd_id,cmd.opcode,result,reason,detail,min(65535,int((time.monotonic()-start)*10)))
        except RuntimeError as e:
            reason={'KRAKEN_DOWN':7,'WRITE_FAILED':8,'NOT_CONSUMED':9}.get(str(e),8); ack=AckMessage(cmd.cmd_id,cmd.opcode,2,reason)
        except Exception: ack=AckMessage(cmd.cmd_id,cmd.opcode,2,8)
        finally: self.calibrating=False; self.busy=False
        with self.lock: self._emit(ack)
