"""Daily rotating, bounded CSV DOA logger."""
import csv, datetime, os, threading
class DOALogger:
    COLUMNS=('utc_iso','kraken_ts_ms','vfo','bearing_deg','confidence','rssi_db','freq_hz','latency_ms','fc_heading_deg','lat','lon','rel_alt_m','link_state')
    def __init__(self,directory='/var/log/krakenlink',max_bytes=500*1024*1024,flush_interval=1.):
        self.directory=directory; self.max_bytes=max_bytes; self.flush_interval=flush_interval; self.file=None; self.writer=None; self.day=None; self.last_flush=0.; self.ok=True; self.lock=threading.Lock()
    def _open(self):
        os.makedirs(self.directory,exist_ok=True); day=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d'); path=os.path.join(self.directory,f'doa_{day}.csv')
        if self.day!=day:
            if self.file:self.file.close()
            self.file=open(path,'a',newline='',encoding='utf-8',buffering=1); self.writer=csv.writer(self.file); self.day=day
            if os.path.getsize(path)==0:self.writer.writerow(self.COLUMNS)
        total=sum(os.path.getsize(os.path.join(self.directory,n)) for n in os.listdir(self.directory) if n.endswith('.csv'))
        if total>=self.max_bytes: raise OSError('log size cap reached')
    def log_sample(self,sample,vfo,heading=None,link_state=2):
        with self.lock:
            try:
                self._open(); self.writer.writerow((datetime.datetime.now(datetime.timezone.utc).isoformat(),sample.timestamp_ms,vfo,sample.bearing_deg,sample.confidence,sample.rssi_db,sample.freq_hz,sample.latency_ms,'' if heading is None else heading,sample.latitude,sample.longitude,'',link_state))
                if __import__('time').monotonic()-self.last_flush>=self.flush_interval:self.file.flush(); self.last_flush=__import__('time').monotonic()
            except OSError: self.ok=False
    def close(self):
        if self.file:self.file.flush(); self.file.close(); self.file=None
