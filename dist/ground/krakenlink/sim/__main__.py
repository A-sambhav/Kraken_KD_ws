"""Run a small HTTP and file based Kraken simulator."""
import argparse, json, math, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_SETTINGS = {
    'center_freq': 433.0, 'uniform_gain': 20.7, 'active_vfos': 1,
    'output_vfo': 0, 'dsp_decimation': 1, 'doa_method': 'Bartlett',
    'ant_arrangement': 'UCA', 'ant_spacing_meters': 0.1, 'en_doa': True,
    'doa_data_format': 'Kraken App', 'ext_upd_flag': False,
    **{f'vfo_freq_{i}': 433_000_000 for i in range(16)},
    **{f'vfo_bw_{i}': 100_000 for i in range(16)},
    **{f'vfo_squelch_{i}': -100 for i in range(16)},
}

class KrakenSimulator:
    def __init__(self, directory='.', calibration_gap=8.0, crash_on_invalid=False, poll_interval=.5):
        self.directory=Path(directory); self.directory.mkdir(parents=True,exist_ok=True)
        self.settings_path=self.directory/'settings.json'; self.doa_path=self.directory/'DOA_value.html'
        self.calibration_gap=float(calibration_gap); self.crash_on_invalid=crash_on_invalid; self.poll_interval=poll_interval
        self.lock=threading.RLock(); self.stop_event=threading.Event(); self.crashed=False; self.calibrating_until=0.; self.started=time.time()
        if not self.settings_path.exists(): self._write_settings(DEFAULT_SETTINGS.copy())
        self.watcher=threading.Thread(target=self._watcher,daemon=True); self.producer=threading.Thread(target=self._produce,daemon=True)

    def start(self): self.watcher.start(); self.producer.start()
    def stop(self): self.stop_event.set()
    def _read_settings(self):
        with self.settings_path.open(encoding='utf-8') as f: return json.load(f)
    def _write_settings(self,settings):
        tmp=self.settings_path.with_suffix('.json.tmp')
        with tmp.open('w',encoding='utf-8') as f: json.dump(settings,f); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,self.settings_path)

    @staticmethod
    def is_valid(settings):
        try:
            methods=('Bartlett','Capon','MEM','TNA','MUSIC','ROOT-MUSIC')
            center=float(settings['center_freq'])*1e6; gain=float(settings['uniform_gain']); n=int(settings['active_vfos']); dec=int(settings['dsp_decimation'])
            if not 24e6<=center<=1_766e6 or center%1000 != 0 or n<1 or n>16 or dec<1 or not 0<=gain<=49.6: return False
            method=settings.get('doa_method')
            if method not in methods: return False
            if method=='ROOT-MUSIC' and settings.get('ant_arrangement')!='ULA': return False
            fs=2_400_000/dec
            for i in range(n):
                freq=float(settings[f'vfo_freq_{i}']); bw=float(settings[f'vfo_bw_{i}']); sq=float(settings[f'vfo_squelch_{i}'])
                if not 100<=bw<=fs or not -150<=sq<=0 or abs(freq-center)+bw/2>fs/2: return False
            return True
        except (KeyError,ValueError,TypeError): return False

    def apply_settings(self, changes):
        """Test/control hook: apply a candidate dict as if written by the bridge."""
        with self.lock:
            current=self._read_settings(); candidate=dict(current); candidate.update(changes)
            if not self.is_valid(candidate):
                if self.crash_on_invalid: self.crashed=True
                return False
            calibrates=any(k in changes for k in ('center_freq','uniform_gain')) and any(current.get(k)!=candidate.get(k) for k in ('center_freq','uniform_gain'))
            candidate['ext_upd_flag']=True; self._write_settings(candidate)
            if calibrates: self.calibrating_until=time.time()+self.calibration_gap
            return True

    def _watcher(self):
        try: last=self._read_settings()
        except (OSError,ValueError): last=None
        while not self.stop_event.wait(self.poll_interval):
            try:
                with self.lock:
                    s=self._read_settings()
                    if s.get('ext_upd_flag'):
                        if not self.is_valid(s):
                            if self.crash_on_invalid: self.crashed=True
                            continue
                        if last is not None and any(s.get(k)!=last.get(k) for k in ('center_freq','uniform_gain')):
                            self.calibrating_until=max(self.calibrating_until,time.time()+self.calibration_gap)
                        s['ext_upd_flag']=False; self._write_settings(s)
                    last=s
            except (OSError,ValueError): continue

    def _line(self, vfo=0):
        now=int(time.time()*1000); s=self._read_settings(); freq=int(s.get(f'vfo_freq_{vfo}',433000000))
        arr=[0.0]*360; arr[90]=10.0
        fields=[str(now),'270','90','-42.0',str(freq),str(s.get('ant_arrangement','UCA')),'25','sim','0','0','0','0','GPS','R','R','R','R']+[str(v) for v in arr]
        return ','.join(fields)+'\n'

    def _produce(self):
        while not self.stop_event.wait(.2):
            if self.crashed or time.time()<self.calibrating_until: continue
            try:
                s=self._read_settings()
                line=''.join(self._line(i) for i in range(int(s.get('active_vfos',1))))
                with self.doa_path.open('r+',encoding='utf-8') as f: f.seek(0); f.write(line); f.truncate()
            except FileNotFoundError:
                self.doa_path.write_text(self._line(),encoding='utf-8')
            except (OSError,ValueError): pass

def make_handler(sim):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            name={'/':'DOA_value.html','/DOA_value.html':'DOA_value.html','/settings.json':'settings.json'}.get(self.path)
            if not name: self.send_error(404); return
            path=sim.directory/name
            try: data=path.read_bytes()
            except OSError: self.send_error(404); return
            self.send_response(200); self.send_header('Content-Type','application/json' if name.endswith('.json') else 'text/plain; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
        def do_POST(self):
            if self.path!='/settings': self.send_error(404); return
            try:
                body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))));
                if not isinstance(body,dict): raise ValueError()
                with sim.lock:
                    existing=sim._read_settings(); existing.update(body)
                    # Node endpoint's replace semantics are simulated; bridge direct writer can preserve keys.
                    if sim.crash_on_invalid and not sim.is_valid(existing): sim.crashed=True
                    sim._write_settings(existing)
                self.send_response(200); self.end_headers()
            except (ValueError,OSError): self.send_error(400)
        def log_message(self,*args): pass
    return Handler

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',type=int,default=8081); ap.add_argument('--directory',default='.'); ap.add_argument('--calibration-gap',type=float,default=8.0); ap.add_argument('--crash-on-invalid',action='store_true')
    args=ap.parse_args(argv); sim=KrakenSimulator(args.directory,args.calibration_gap,args.crash_on_invalid); sim.start()
    server=ThreadingHTTPServer(('0.0.0.0',args.port),make_handler(sim)); print(f'Kraken simulator serving {sim.directory} on :{args.port}')
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); sim.stop()

if __name__=='__main__': main()
