import struct
from krakenlink.ground.link import GroundLink
from krakenlink.ground.commands import CommandClient
from krakenlink.ground.app import absolute_bearing, create_app, build_compass_figure, build_trends_figure, build_map_figure, status_color, status_names, mhz_to_hz, metres_to_mm
from krakenlink.proto.frame import Frame, decode_frame
from krakenlink.proto.messages import DOAMessage, PongMessage, AckMessage, SettingsMessage

class Clock:
    def __init__(self): self.t=0.
    def __call__(self): return self.t

def test_loss_wrap_rtt_and_state():
    c=Clock(); g=GroundLink(clock=c)
    for seq in (65534,65535,0,2):
        g.receive(Frame(1,seq,DOAMessage(0,0,1,1200,80,-100,1000,2,0).encode()).encode()); c.t+=.5
    assert g.seq_gaps==1 and g.loss_pct>0 and g.state==g.UP
    p=decode_frame(g.ping(now=c.t)); stamp=struct.unpack('<I',p.payload[:4])[0]
    c.t+=.25; g.receive(Frame(0x21,7,PongMessage(stamp,0,0).encode()).encode())
    assert g.rtt_ms==250
    c.t+=4; assert g.update()==g.DEGRADED
    c.t+=7; assert g.update()==g.LOST

def test_settings_parts_and_bearing():
    g=GroundLink()
    parts=[SettingsMessage.globals(3,100_000_000,90,0,0,400,1,2,0,1,1,50,10),SettingsMessage.vfos(3,1,[(i,100,-20) for i in range(8)]),SettingsMessage.vfos(3,2,[(i+8,200,-30) for i in range(8)])]
    for m in parts:g.receive(Frame(5,m.part,m.encode()).encode())
    assert len(g.settings['vfos'])==16 and g.settings['vfos'][8]==(8,200,-30)
    assert absolute_bearing(350,20,10)==20

def test_command_retry_and_ack_idempotency():
    c=Clock(); wire=[]; client=CommandClient(wire.append,clock=c,start_id=65535)
    cid=client.submit(1,struct.pack('<I',100_000_000)); assert cid==65535
    first=decode_frame(wire[-1]); assert not first.retry
    for _ in range(4):c.t+=1; client.tick()
    assert len(wire)==5
    c.t+=1; client.tick(); assert client.commands[cid]['status']=='no_response'
    client.receive_ack(AckMessage(cid,1,0,0)); client.receive_ack(AckMessage(cid,1,1,0))
    assert client.commands[cid]['status']=='done'

def test_app_builds_without_server():
    app=create_app(GroundLink(),CommandClient(lambda frame:None))
    assert app.layout is not None

    def walk(node):
        if isinstance(node,(list,tuple)):
            for child in node: yield from walk(child)
        elif hasattr(node,'children'):
            yield node
            yield from walk(node.children)
    tabs=next(x for x in walk(app.layout) if getattr(x,'id',None)=='pages')
    assert [x.label for x in tabs.children]==['Status','DoA Estimation','Settings','Map']

def test_ui_conversions_and_status_colors():
    assert mhz_to_hz(433.125)==433_125_000
    assert mhz_to_hz(100.0)==100_000_000
    assert metres_to_mm(.125)==125
    assert metres_to_mm(1.5)==1500
    for status in ('UP','OK'): assert status_color(status)=='#7ccc63'
    for status in ('DEGRADED','STALE','CALIBRATING'): assert status_color(status)=='#f39c12'
    for status in ('LOST','DOWN'): assert status_color(status)=='#e74c3c'

def test_status_display_mappings():
    assert status_names(0, 0, 0, 3661, 12, 1) == {
        'kraken_state': 'OK', 'bridge_state': 'RUNNING', 'doa_method': 'Bartlett',
        'uptime': '1:01:01', 'last_command': 'id 12 · DONE',
    }
    assert status_names(4, 2, 5, 59, 0, 4)['kraken_state'] == 'FORMAT_WRONG'
    assert status_names(4, 2, 5, 59, 0, 4)['bridge_state'] == 'WAIT_KRAKEN'
    assert status_names(4, 2, 5, 59, 0, 4)['doa_method'] == 'ROOT-MUSIC'
    assert status_names(9, 8, 99, 59, 0, 99)['bridge_state'] == 'UNKNOWN(8)'
    assert status_names(9, 8, 99, 59, 0, 99)['doa_method'] == 'UNKNOWN(99)'

def test_app_figures_render_synthetic_ground_frames():
    from krakenlink.proto.messages import SpectrumMessage, PoseMessage
    g=GroundLink(wall_clock=lambda:1000)
    g.receive(Frame(1,0,DOAMessage(1,1,1,9000,80,-100,433000000,2,18000).encode()).encode())
    g.receive(Frame(2,1,SpectrumMessage(1,2,10,bytes(range(72))).encode()).encode())
    g.receive(Frame(4,2,PoseMessage(1,100000000,200000000,5,0,0,3,8).encode()).encode())
    compass=build_compass_figure(g,{'array_offset_cfg':10})
    assert compass.layout.paper_bgcolor=='rgba(0,0,0,0)'
    assert compass.layout.polar.angularaxis.direction=='clockwise'
    assert compass.layout.polar.angularaxis.rotation==90
    assert compass.layout.plot_bgcolor=='rgba(0,0,0,0)'
    assert compass.layout.template.layout.paper_bgcolor=='rgb(17,17,17)'
    assert any(t.name=='VFO 1 absolute now' and list(t.theta)==[280] for t in compass.data)
    assert any(t.name.startswith('Spectrum') and len(t.r)==72 for t in compass.data)
    assert next(t for t in compass.data if t.name.startswith('Spectrum')).fill=='toself'
    trends=build_trends_figure(g)
    assert any('RSSI' in t.name and list(t.y)==[-10.0] for t in trends.data)
    mapfig=build_map_figure(g)
    assert len(mapfig.data)==2 and mapfig.data[0].y[0]==10
    assert mapfig.layout.xaxis.scaleanchor == 'y'
    empty_map=build_map_figure(type('L',(),{'pose':None,'last_good_doa':None})())
    assert empty_map.layout.annotations[0].text == 'No position from flight controller yet'

def test_ping_sequence_increments():
    g=GroundLink()
    assert [decode_frame(g.ping()).seq for _ in range(3)]==[0,1,2]

def test_command_client_concurrent_submit_tick_and_ack():
    import threading, time
    sent=[]; failures=[]; client=CommandClient(lambda frame:(time.sleep(0),sent.append(frame)),start_id=0)
    finished=threading.Event()
    def submitter():
        try:
            for _ in range(2000):client.submit(8)
        except Exception as exc:failures.append(exc)
        finally:finished.set()
    def worker():
        try:
            while not finished.is_set():
                for cid in client.tick():client.receive_ack(AckMessage(cid,8,1,0))
        except Exception as exc:failures.append(exc)
    a=threading.Thread(target=submitter); b=threading.Thread(target=worker)
    a.start(); b.start(); a.join(); b.join()
    assert not failures
    snapshot=client.snapshot()
    assert len(snapshot)==2000
    assert set(snapshot)==set(range(2000))
    assert all(c['status'] in {'pending','accepted','done','done_warn','nack','timeout','no_response'} for c in snapshot.values())

def test_ground_pump_continues_after_iteration_exception():
    import threading
    from krakenlink.ground.app import pump_loop
    class Transport:
        def __init__(self):self.calls=0
        def recv(self):
            self.calls+=1
            if self.calls==1:raise OSError('temporary receive failure')
            return b'later-frame'
    class Link:
        def __init__(self):self.received=[]
        def receive(self,raw):self.received.append(raw);return None
        def ping(self):return b'ping'
    class Client:
        def tick(self):return {}
    transport=Transport(); link=Link(); stop=threading.Event(); sleeps=0
    def short_sleep(_):
        nonlocal sleeps
        sleeps+=1
        if sleeps>=2:stop.set()
    pump_loop(transport,link,Client(),stop,short_sleep)
    assert transport.calls==2
    assert link.received==[b'later-frame']
