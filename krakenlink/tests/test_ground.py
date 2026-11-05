import struct
from krakenlink.ground.link import GroundLink
from krakenlink.ground.commands import CommandClient
from krakenlink.ground.app import absolute_bearing, create_app, build_compass_figure, build_trends_figure, build_map_figure
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

def test_app_figures_render_synthetic_ground_frames():
    from krakenlink.proto.messages import SpectrumMessage, PoseMessage
    g=GroundLink(wall_clock=lambda:1000)
    g.receive(Frame(1,0,DOAMessage(1,1,1,9000,80,-100,433000000,2,18000).encode()).encode())
    g.receive(Frame(2,1,SpectrumMessage(1,2,10,bytes(range(72))).encode()).encode())
    g.receive(Frame(4,2,PoseMessage(1,100000000,200000000,5,0,0,3,8).encode()).encode())
    compass=build_compass_figure(g,{'array_offset_cfg':10})
    assert any(t.name=='VFO 1 absolute now' and list(t.theta)==[280] for t in compass.data)
    assert any(t.name.startswith('Spectrum') and len(t.r)==72 for t in compass.data)
    trends=build_trends_figure(g)
    assert any('RSSI' in t.name and list(t.y)==[-10.0] for t in trends.data)
    mapfig=build_map_figure(g)
    assert len(mapfig.data)==2 and mapfig.data[0].lat[0]==10

def test_ping_sequence_increments():
    g=GroundLink()
    assert [decode_frame(g.ping()).seq for _ in range(3)]==[0,1,2]
