"""File based Kraken I/O with race aware atomic settings updates."""
import json, os, threading, time
from pathlib import Path
from ..proto.csv_parser import parse_doa_line, CSVLineError

class KrakenIO:
    def __init__(self, share, poll_interval=.05, partial_retry=.02, stale_s=2., down_s=10., consumed_timeout=5., writer='atomic', logger=None):
        self.share=Path(share); self.doa_path=self.share/'DOA_value.html'; self.settings_path=self.share/'settings.json'
        self.poll_interval=poll_interval; self.partial_retry=partial_retry; self.stale_s=stale_s; self.down_s=down_s
        self.consumed_timeout=consumed_timeout; self.writer=writer; self.log=logger or (lambda *a,**k:None)
        self.last_mtime=None; self.samples=[]; self.last_data_mono=None; self.partial_reads=0; self._lock=threading.RLock()
    def settings(self):
        with self.settings_path.open(encoding='utf-8') as f: value=json.load(f)
        if not isinstance(value,dict): raise ValueError('settings root must be object')
        return value
    def poll(self):
        try: mtime=self.doa_path.stat().st_mtime_ns
        except OSError: return []
        if mtime==self.last_mtime: return []
        for attempt in range(2):
            try:
                lines=self.doa_path.read_text(encoding='utf-8').splitlines()
                parsed=[parse_doa_line(x) for x in lines if x.strip()]
                if not parsed: raise CSVLineError('empty DOA file')
                self.samples=parsed; self.last_data_mono=time.monotonic(); self.last_mtime=mtime; return parsed
            except (OSError,CSVLineError):
                if attempt==0: time.sleep(self.partial_retry)
                else: self.partial_reads+=1
        return []
    def state(self, now=None):
        if self.last_data_mono is None: return 'DOWN'
        age=(time.monotonic() if now is None else now)-self.last_data_mono
        return 'DOWN' if age>self.down_s else 'STALE' if age>self.stale_s else 'OK'
    def _write(self, changes):
        if self.writer=='node_api': self.log('warning','node_api writer currently uses safe full-file atomic writer')
        current=self.settings(); current.update(changes); current['ext_upd_flag']=True
        tmp=self.settings_path.with_name(self.settings_path.name+'.klnk.tmp')
        with tmp.open('w',encoding='utf-8') as f:
            json.dump(current,f,ensure_ascii=False); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,self.settings_path)
    def apply(self, changes, calibration=False, timeout=None):
        """Atomic RMW and consumed check; returns consumption epoch and prior settings."""
        for attempt in range(2):
            try: before=self.settings()
            except (OSError,ValueError,TypeError) as e: raise RuntimeError('KRAKEN_DOWN') from e
            if all(before.get(k)==v for k,v in changes.items()): return None,before
            try: self._write(changes)
            except (OSError,ValueError,TypeError) as e: raise RuntimeError('WRITE_FAILED') from e
            written=time.time(); deadline=time.monotonic()+(self.consumed_timeout if timeout is None else timeout)
            while time.monotonic()<deadline:
                try: current=self.settings()
                except (OSError,ValueError,TypeError): current={}
                if current.get('ext_upd_flag') is False and all(current.get(k)==v for k,v in changes.items()): return time.time(),before
                time.sleep(min(.05,max(0,deadline-time.monotonic())))
            if attempt==0:
                self.log('warning','settings write lost race; retrying once')
                continue
        raise RuntimeError('NOT_CONSUMED')
    def ensure_format(self):
        s=self.settings()
        if s.get('doa_data_format')!='Kraken App':
            self.apply({'doa_data_format':'Kraken App'})
            self.log('warning','set doa_data_format to Kraken App')
