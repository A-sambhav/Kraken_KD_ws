import json, random, socket, struct, threading, time

from krakenlink.bridge.kraken_io import KrakenIO
from krakenlink.bridge.commands import CommandWorker
from krakenlink.bridge.link import LinkMonitor
from krakenlink.bridge.ratelimit import TokenBucket, PriorityQueue
from krakenlink.bridge.transports.loopback import LoopbackTransport
from krakenlink.proto.frame import Frame, decode_frame
from krakenlink.proto.messages import CommandMessage, ACK, AckMessage, StatusMessage, DOA, SPECTRUM
from krakenlink.sim.__main__ import KrakenSimulator

def wait_for(fn, timeout=4):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if fn():return True
        time.sleep(.01)
    return False

def test_command_idempotency_busy_calibration_and_noop(tmp_path):
    sim=KrakenSimulator(tmp_path,calibration_gap=1,poll_interval=.05); sim.start()
    try:
        io=KrakenIO(tmp_path,poll_interval=.05,consumed_timeout=1)
        assert wait_for(lambda: bool(io.poll()))
        acks=[]; worker=CommandWorker(io,acks.append,calibration_timeout=3,consumed_timeout=1)
        cmd=CommandMessage(7,1,struct.pack('<I',433100000))
        first=worker.handle(cmd); assert first.result==0
        worker.handle(cmd)
        # The bridge/main loop owns polling; the worker only observes samples.
        assert wait_for(lambda: (io.poll(), any(a.result==1 for a in acks))[1],5)
        writes=worker.write_count; same=[a for a in acks if a.cmd_id==7]
        assert len(same)==3 and same[0]==same[1] and same[0].result==0 and same[-1].result==1 and writes==1
        # no-op returns final success immediately without another write
        no_op=worker.handle(CommandMessage(8,1,struct.pack('<I',433100000)))
        assert no_op.result==1 and worker.write_count==1
        # New calibration gives a deterministic BUSY interval.
        sim.calibration_gap=1
        worker.handle(CommandMessage(9,1,struct.pack('<I',433200000)))
        assert wait_for(lambda:worker.calibrating,2)
        from krakenlink.bridge.__main__ import Bridge
        class NullTransport:
            def send(self,frame):return True
            def recv(self):return None
            def stats(self):return {}
            def close(self):pass
        class NullLogger:
            ok=True
            def close(self):pass
        bridge=Bridge({'kraken':{'share':str(tmp_path),'poll_interval':.05,'consumed_timeout':1},'rate':{}},transport=NullTransport(),logger=NullLogger())
        bridge.kraken=io; bridge.commands=worker
        assert StatusMessage.decode(bridge._status().encode()).kraken_state==2
        busy=worker.handle(CommandMessage(10,5,b'\0'))
        assert busy.result==2 and busy.reason==6
    finally:sim.stop()

def test_retune_done_waits_for_simulator_calibration_gap(tmp_path):
    sim=KrakenSimulator(tmp_path,calibration_gap=2.0,poll_interval=.1); sim.start()
    try:
        io=KrakenIO(tmp_path,poll_interval=.1,consumed_timeout=2)
        assert wait_for(lambda: bool(io.poll()))
        acks=[]; worker=CommandWorker(io,acks.append,calibration_timeout=6,consumed_timeout=2,calib_settle_s=1.0)
        accepted_at=time.monotonic()
        assert worker.handle(CommandMessage(70,1,struct.pack('<I',433100000))).result==0
        assert wait_for(lambda: (io.poll(), any(a.cmd_id==70 and a.result in (1,3,4) for a in acks))[1],7)
        final=next(a for a in acks if a.cmd_id==70 and a.result in (1,3,4))
        assert final.result==1
        assert time.monotonic()-accepted_at>=2.0
    finally:sim.stop()

def test_example_loopback_ports_are_complementary():
    from pathlib import Path
    from krakenlink.bridge.__main__ import load_config
    root=Path(__file__).resolve().parents[1]
    bridge=load_config(root/'krakenlink/bridge/config.example.toml')
    ground=load_config(root/'ground.example.toml')
    # Bridge loopback defaults: sends to 14560 and binds 14561.
    assert bridge['transport']['type']=='mavlink'
    assert (ground['transport']['port'],ground['transport']['bind_port'])==(14561,14560)

def test_rate_limiter_budget_and_priority():
    b=TokenBucket(100,capacity=100,transport='mavlink')
    sent=0
    for _ in range(500):
        if b.allow(10,now=0):sent+=10
    assert sent<=100
    q=PriorityQueue(); q.put('SPECTRUM',b's'); q.put('DOA',b'd',vfo=2); q.put('ACK',b'a'); q.put('STATUS',b'x')
    assert [q.pop()[0] for _ in range(4)]==['ACK','STATUS','DOA','SPECTRUM']

def test_loopback_link_loss_recovery_and_logger_continues(tmp_path, monkeypatch):
    # A loopback UDP pair exercises the configured application transport.
    class FakeSocket:
        next_port=30000
        def __init__(self,*a): self.port=FakeSocket.next_port; FakeSocket.next_port+=1; self.inbox=[]
        def setsockopt(self,*a):pass
        def bind(self,addr):self.port=addr[1] or self.port
        def setblocking(self,*a):pass
        def getsockname(self):return ('127.0.0.1',self.port)
        def sendto(self,data,peer):
            for sock in sockets:
                if sock.port==peer[1]:sock.inbox.append((data,('127.0.0.1',30000)))
        def recvfrom(self,n):
            if not self.inbox:raise BlockingIOError()
            return self.inbox.pop(0)
        def close(self):pass
    sockets=[]
    def factory(*a):
        s=FakeSocket(*a); sockets.append(s); return s
    import krakenlink.bridge.transports.loopback as loopback
    monkeypatch.setattr(loopback.socket,'socket',factory)
    receiver=LoopbackTransport(bind_port=0); port=receiver.sock.getsockname()[1]
    sender=LoopbackTransport(port=port,bind_port=0)
    monitor=LinkMonitor(); sent=sender.send(Frame(ACK,1,AckMessage(1,1,0,0).encode()).encode())
    assert sent and wait_for(lambda: receiver.recv() is not None)
    monitor.received(True,now=1); monitor.update(now=12); assert monitor.state==monitor.LOST
    monitor.received(True,now=13); assert monitor.update(now=13)==monitor.UP
    # Logger remains independently writable through the full link outage window.
    from krakenlink.bridge.logger import DOALogger
    logger=DOALogger(str(tmp_path/'logs')); logger._open(); logger.file.write('sample\n'); logger.close()
    assert list((tmp_path/'logs').glob('*.csv'))
    sender.close(); receiver.close()

def test_simulator_stop_restart_states(tmp_path):
    sim=KrakenSimulator(tmp_path,poll_interval=.05); sim.start(); io=KrakenIO(tmp_path)
    try:
        assert wait_for(lambda: bool(io.poll())); assert io.state()=='OK'
        sim.stop(); assert wait_for(lambda: io.state()=='STALE',2.5)
        assert wait_for(lambda: io.state()=='DOWN',10.5)
    finally:sim.stop()
    sim2=KrakenSimulator(tmp_path,poll_interval=.05); sim2.start()
    try: assert wait_for(lambda: bool(io.poll()),3); assert io.state()=='OK'
    finally:sim2.stop()

def test_random_cmd_frames_do_not_crash_simulator(tmp_path):
    sim=KrakenSimulator(tmp_path,crash_on_invalid=True,poll_interval=.03); sim.start()
    try:
        io=KrakenIO(tmp_path,consumed_timeout=.3); assert wait_for(lambda: bool(io.poll()))
        worker=CommandWorker(io,lambda a:None,calibration_timeout=.1,consumed_timeout=.3)
        rng=random.Random(382); allowed=(1,2,3,4,5,6,7,8,9,255)
        for i in range(2000):
            op=rng.choice(allowed); payload=bytes(rng.randrange(256) for _ in range(rng.randrange(17)))
            try:worker.handle(CommandMessage(i,op,payload))
            except Exception:pass
        assert not sim.crashed
    finally:sim.stop()

def test_bridge_telemetry_rates_latest_and_runtime_update(tmp_path):
    from types import SimpleNamespace
    from krakenlink.bridge.__main__ import Bridge
    class T:
        def __init__(self): self.sent=[]
        def send(self,b): self.sent.append(decode_frame(b)); return True
        def recv(self): return None
        def stats(self): return {}
        def close(self): pass
    class L:
        ok=True
        def log_sample(self,*a): pass
        def close(self): pass
    settings=KrakenSimulator(tmp_path)._read_settings(); settings.update(active_vfos=2,output_vfo=1); (tmp_path/'settings.json').write_text(json.dumps(settings))
    sim=KrakenSimulator(tmp_path,poll_interval=.05); sim.start()
    t=T(); b=Bridge({'kraken':{'share':str(tmp_path),'poll_interval':.02},'transport':{'type':'loopback'},'rate':{'bytes_per_second':100000,'doa_hz':5,'spectrum_hz':1}},transport=t,logger=L())
    stop=time.monotonic()+3.05
    while time.monotonic()<stop: b.step(); time.sleep(.02)
    doa=[f for f in t.sent if f.type==DOA]; spec=[f for f in t.sent if f.type==SPECTRUM]
    assert 25 <= len(doa) <= 34 and 2 <= len(spec) <= 4
    assert all(__import__('krakenlink.proto.messages',fromlist=['DOAMessage']).DOAMessage.decode(f.payload).vfo in (0,1) for f in doa)
    assert all(__import__('krakenlink.proto.messages',fromlist=['SpectrumMessage']).SpectrumMessage.decode(f.payload).vfo==1 for f in spec)
    try:
        t.sent.clear(); b.kraken.telemetry_rates={'telem_doa_hz_x10':10,'telem_spec_hz_x10':0}
        stop=time.monotonic()+3.05
        while time.monotonic()<stop: b.step(); time.sleep(.02)
        doa=[f for f in t.sent if f.type==DOA]; spec=[f for f in t.sent if f.type==SPECTRUM]
        assert 5 <= len(doa) <= 8 and not spec
    finally: sim.stop()

def test_bridge_flush_radio_backpressure_gates():
    from krakenlink.bridge.__main__ import Bridge
    from krakenlink.proto.messages import DOAMessage
    class T:
        txbuf=40; sent=[]
        def send(self,b): self.sent.append(decode_frame(b)); return True
        def recv(self): return None
        def stats(self): return {'txbuf':self.txbuf}
        def close(self): pass
    class L:
        ok=True
        def close(self): pass
    t=T(); b=Bridge({'transport':{'type':'loopback'},'rate':{'bytes_per_second':100000}},transport=t,logger=L())
    for k in ('DOA','DOA','ACK','STATUS'): b._send(k,{'DOA':DOA,'ACK':ACK,'STATUS':3}[k],DOAMessage(0,0,0,0,0,0,0,0,0) if k=='DOA' else AckMessage(1,1,0,0) if k=='ACK' else StatusMessage(0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0))
    b._flush(); assert len([f for f in t.sent if f.type==DOA])==1
    t.sent.clear(); t.txbuf=20
    for k in ('DOA','ACK','STATUS'): b._send(k,{'DOA':DOA,'ACK':ACK,'STATUS':3}[k],DOAMessage(0,0,0,0,0,0,0,0,0) if k=='DOA' else AckMessage(1,1,0,0) if k=='ACK' else StatusMessage(0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0))
    b._flush(); assert [f.type for f in t.sent]==[ACK,3]

def test_bridge_assigns_sequences_only_to_transmitted_frames():
    from krakenlink.bridge.__main__ import Bridge
    class T:
        sent=[]
        def send(self,b):self.sent.append(decode_frame(b));return True
        def recv(self):return None
        def stats(self):return {}
        def close(self):pass
    class L:
        ok=True
        def close(self):pass
    t=T(); b=Bridge({'transport':{'type':'loopback'},'rate':{'bytes_per_second':1}},transport=t,logger=L())
    # One 16-byte frame fits the deliberately tiny budget; the following frames drop.
    b.bucket.capacity=b.bucket.tokens=16; b.bucket.rate=0
    for cid in (1,2,3):b._send('ACK',ACK,AckMessage(cid,1,0,0))
    b._flush(); assert [f.seq for f in t.sent]==[0]
    b.bucket.tokens=16
    b._send('ACK',ACK,AckMessage(4,1,0,0)); b._flush()
    assert [f.seq for f in t.sent]==[0,1]

def test_mavlink_single_connection_dispatch_and_intervals():
    from types import SimpleNamespace
    from krakenlink.bridge.transports.mavlink import MAVLinkTransport
    from krakenlink.bridge.fc import FCReader
    calls=[]
    class Mav:
        MAV_TYPE_ONBOARD_CONTROLLER=18; MAV_AUTOPILOT_INVALID=8; MAV_CMD_SET_MESSAGE_INTERVAL=511
    class Sender:
        def command_long_send(self,*a): calls.append(a)
        def heartbeat_send(self,*a): pass
        def tunnel_send(self,*a): pass
    class Conn:
        mav=Sender()
        def recv_match(self,**kw): return queue.pop(0) if queue else None
        def close(self): pass
    queue=[]; conn=Conn()
    connect_args=[]
    def connect(*a,**k): connect_args.append((a,k)); return conn
    util=SimpleNamespace(mavlink=Mav,mavlink_connection=connect)
    tr=MAVLinkTransport('/fake',source_system=42,fc_enabled=True,mavutil_module=util,baud=57600)
    reader=FCReader('/fake',shared_link=tr); tr.fc_reader=reader
    assert len(calls)==3 and all(c[4] in (33,74,24) and c[5]==500000 for c in calls)
    assert connect_args[0][1]['baud']==57600 and connect_args[0][1]['source_system']==42
    assert tr.conn is conn
    msg=SimpleNamespace(get_type=lambda:'GLOBAL_POSITION_INT',hdg=9000,time_boot_ms=1,lat=2,lon=3,relative_alt=400)
    queue.append(msg); tr.recv(); pose,heading=reader.snapshot()
    assert pose.lat_e7==2 and heading==90

def test_espnow_uart_reopens_after_serial_io_error():
    from krakenlink.bridge.transports.espnow_uart import ESPNowUARTTransport
    class Serial:
        def __init__(self,fail=False): self.fail=fail; self.closed=False
        def write(self,b):
            if self.fail: raise OSError('gone')
            return len(b)
        def read(self,n):
            if self.fail: raise OSError('gone')
            return b''
        def close(self): self.closed=True
    instances=[]
    def factory(*a,**k):
        s=Serial(fail=not instances); instances.append(s); return s
    tr=ESPNowUARTTransport('/fake',serial_instance=instances.append(Serial(True)) or instances[0],serial_factory=factory,reopen_interval=0)
    assert not tr.send(b'x') and instances[0].closed
    assert tr.send(b'x') and len(instances)==2

def test_espnow_uart_configured_baud_is_passed_to_serial_factory():
    from krakenlink.bridge.transports.espnow_uart import ESPNowUARTTransport
    calls=[]
    ESPNowUARTTransport('/fake',baudrate=230400,serial_factory=lambda *a,**k:(calls.append((a,k)) or object()))
    assert calls[0]==(('/fake',),{'baudrate':230400,'timeout':0})

def test_command_worker_observes_samples_without_polling_and_uses_daq_window():
    from types import SimpleNamespace
    class K:
        poll_interval=.001
        samples=[SimpleNamespace(timestamp_ms=4_000_000_000_000,freq_hz=433_001_000)]
        poll_calls=0
        def settings(self): return {'center_freq':433.,'dsp_decimation':2,'active_vfos':1,'vfo_freq_0':433_001_200,'vfo_bw_0':0}
        def apply(self,*a,**k): return time.time(),self.settings()
        def poll(self): self.poll_calls+=1; raise AssertionError('worker must not poll')
    k=K(); worker=CommandWorker(k,calibration_timeout=.2,daq_fs=800,retune_vfo_policy='allow')
    # The sample is exactly within daq_fs / 2 / decimation (200 Hz).
    worker.handle(CommandMessage(1,1,struct.pack('<I',433001000)))
    assert wait_for(lambda:any(a and a.result==1 for a in [worker.last_ack]),1)
    assert k.poll_calls==0


def test_settings_read_retries_partial_write(tmp_path):
    """Kraken rewrites settings.json non-atomically; a transient partial file must not read as KRAKEN_DOWN."""
    import json, threading, time as _t
    from krakenlink.bridge.kraken_io import KrakenIO
    p = tmp_path / 'settings.json'
    p.write_text('{"center_freq": 4')  # half-written
    def finish():
        _t.sleep(0.03); p.write_text(json.dumps({'center_freq': 433.0}))
    threading.Thread(target=finish).start()
    assert KrakenIO(tmp_path).settings()['center_freq'] == 433.0
