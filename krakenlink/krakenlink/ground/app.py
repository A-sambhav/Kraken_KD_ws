"""Dash ground station; importing/building layout does not start a server."""
import math
import struct

def absolute_bearing(bearing_deg, array_offset_cfg=0, fc_heading_deg=0):
    return (float(bearing_deg) + float(array_offset_cfg) + float(fc_heading_deg)) % 360

def _plotly():
    import plotly.graph_objects as go
    return go

def build_compass_figure(link, cfg=None):
    go = _plotly(); cfg = cfg or {}; fig = go.Figure()
    samples = sorted((s for q in link.samples.values() for s in q), key=lambda s:s['time'])
    for vfo in sorted({s['vfo'] for s in samples}):
        rows=[s for s in samples if s['vfo']==vfo]
        if rows:
            now=link.clock()
            opacity=[max(.04,.45*(1-max(0,now-s['time'])/max(1,link.history_s))) for s in rows]
            fig.add_trace(go.Scatterpolar(theta=[s['bearing_deg'] for s in rows],r=[max(0.05, (s['confidence']/99)) for s in rows],mode='markers',name=f'VFO {vfo} relative',marker={'opacity':opacity}))
            s=rows[-1]; heading=s['fc_heading_cdeg']/100 if s['flags']&1 else 0
            absolute=absolute_bearing(s['bearing_deg'],cfg.get('array_offset_cfg',0),heading)
            fig.add_trace(go.Scatterpolar(theta=[s['bearing_deg']],r=[1],mode='markers',name=f'VFO {vfo} relative now'))
            fig.add_trace(go.Scatterpolar(theta=[absolute],r=[1],mode='markers',name=f'VFO {vfo} absolute now'))
    spectrum=link.spectrum
    if spectrum is not None:
        fig.add_trace(go.Scatterpolar(theta=[i*5 for i in range(72)],r=[max(.01,x/255) for x in spectrum.bins],mode='lines',name=f'Spectrum VFO {spectrum.vfo}'))
    fig.update_layout(polar={'angularaxis':{'direction':'clockwise','rotation':90}},title='Bearing and spectrum')
    return fig

def build_trends_figure(link):
    go=_plotly(); fig=go.Figure()
    for vfo, queue in sorted(link.samples.items()):
        rows=list(queue)
        if rows:
            x=[s['wall_time'] for s in rows]
            fig.add_trace(go.Scatter(x=x,y=[s['rssi_db'] for s in rows],mode='lines',name=f'VFO {vfo} RSSI (dB)'))
            fig.add_trace(go.Scatter(x=x,y=[s['confidence'] for s in rows],mode='lines',name=f'VFO {vfo} confidence',yaxis='y2'))
    fig.update_layout(title='Last 5 minutes',yaxis={'title':'RSSI (dB)'},yaxis2={'title':'Confidence','overlaying':'y','side':'right'})
    return fig

def build_map_figure(link):
    go=_plotly(); fig=go.Figure(); pose=link.pose
    if pose:
        lat,lon=pose.lat_e7/1e7,pose.lon_e7/1e7
        fig.add_trace(go.Scattergeo(lat=[lat],lon=[lon],mode='markers',name='Drone POSE',marker={'size':10}))
        doa=link.last_good_doa
        if doa:
            heading=doa['fc_heading_cdeg']/100 if doa['flags']&1 else 0
            bearing=absolute_bearing(doa['bearing_deg'],getattr(link,'array_offset_cfg',0),heading)
            dist=0.5; rad=math.radians(bearing)
            end_lat=lat+dist*math.cos(rad)/111.32
            end_lon=lon+dist*math.sin(rad)/(111.32*max(.01,math.cos(math.radians(lat))))
            fig.add_trace(go.Scattergeo(lat=[lat,end_lat],lon=[lon,end_lon],mode='lines',name='Bearing (~500 m)'))
    fig.update_layout(title='Drone map',geo={'projection_type':'equirectangular','showland':True})
    return fig

def _command_rows(commands):
    if not commands:return []
    from dash import html
    names={0:'OK',1:'BAD_OPCODE',2:'BAD_LEN',3:'OUT_OF_RANGE',4:'VFO_OUT_OF_WINDOW',5:'INCOMPATIBLE',6:'BUSY',7:'KRAKEN_DOWN',8:'WRITE_FAILED',9:'NOT_CONSUMED',10:'CALIB_TIMEOUT',11:'VFO_MOVED'}
    return html.Table([html.Thead(html.Tr([html.Th(x) for x in ('ID','Opcode','Status','Reason')])),html.Tbody([html.Tr([html.Td(str(c['cmd_id'])),html.Td(str(c['opcode'])),html.Td(c['status']),html.Td(names.get(c.get('reason'),str(c.get('reason') or '')))]) for c in list(commands.commands.values())[-30:]])])

def create_layout(link=None, commands=None):
    from dash import dcc, html
    import plotly.graph_objects as go
    empty=go.Figure()
    gain=[{'label':f'{x/10:.1f} dB','value':x} for x in sorted(__import__('krakenlink.proto.validate',fromlist=['GAIN_X10']).GAIN_X10)]
    def number(id,label,**kw):return html.Label([label,dcc.Input(id=id,type='number',**kw)])
    controls=[html.H3('Settings')]
    controls += [number('center-freq','Center frequency (Hz)'),html.Button('Set center',id='set-center'),dcc.Dropdown(id='gain',options=gain,placeholder='Gain'),html.Button('Set gain',id='set-gain')]
    controls += [number('vfo-idx','VFO index',min=0,max=15),number('vfo-freq','VFO frequency Hz'),number('vfo-bw','VFO bandwidth Hz'),number('vfo-squelch','Squelch dB'),dcc.Checklist(id='vfo-fields',options=[{'label':x,'value':x} for x in ('frequency','bandwidth','squelch')]),html.Button('Set VFO',id='set-vfo')]
    controls += [number('active-vfos','Active VFOs',min=1,max=16),number('output-vfo','Output VFO (255 = all)',min=0,max=255),html.Button('Set active/output VFOs',id='set-active'),dcc.Dropdown(id='doa-method',options=[{'label':x,'value':i} for i,x in enumerate(('Bartlett','Capon','MEM','TNA','MUSIC','ROOT-MUSIC'))]),html.Button('Set DOA method',id='set-method')]
    controls += [dcc.Dropdown(id='array-type',options=[{'label':'UCA','value':0},{'label':'ULA','value':1}]),number('array-dim','Array dimension (mm)',min=20,max=2000),html.Button('Set array',id='set-array'),dcc.RadioItems(id='doa-enable',options=[{'label':'Disabled','value':0},{'label':'Enabled','value':1}]),html.Button('Set DOA enable',id='set-doa'),html.Button('GET_SETTINGS',id='request-snapshot')]
    controls += [number('telem-doa','DOA rate ×10 Hz',min=2,max=100),number('telem-spec','Spectrum rate ×10 Hz',min=0,max=20),html.Button('Set telemetry rates',id='set-rates'),html.Div(id='command-message'),html.Div(id='command-table'),html.H4('Latest SETTINGS'),html.Pre(id='settings-snapshot')]
    return html.Div([dcc.Interval(id='refresh',interval=500,n_intervals=0),html.H2('KrakenLink Ground Station'),html.Div(id='link-panel'),dcc.Graph(id='compass',figure=empty),dcc.Graph(id='trends',figure=empty),dcc.Graph(id='map-panel',figure=empty),html.Div(controls)])

def create_app(link=None, commands=None, cfg=None):
    from dash import Dash, Input, Output, State, ctx, no_update
    import json
    app=Dash(__name__); app.layout=create_layout(link,commands); cfg=cfg or {}
    @app.callback(Output('link-panel','children'),Output('compass','figure'),Output('trends','figure'),Output('map-panel','figure'),Output('command-table','children'),Output('settings-snapshot','children'),Input('refresh','n_intervals'))
    def refresh(_):
        if link is None:return ('LOST',build_compass_figure(type('L',(),{'samples':{},'spectrum':None})(),cfg),build_trends_figure(type('L',(),{'samples':{}})()),build_map_figure(type('L',(),{'pose':None,'last_good_doa':None})()),_command_rows(commands), '')
        state=link.update(); status=link.status
        state_name={0:'UP',1:'DEGRADED',2:'LOST'}[state]
        status_text='kraken_state unavailable · bridge_state unavailable'
        if status:status_text=f'kraken_state {status.kraken_state} · bridge_state {status.bridge_state}'
        packet='never' if link.last_good_packet is None else time_text(link.last_good_packet.get('wall_time'))
        link.array_offset_cfg=cfg.get('array_offset_cfg',0)
        from dash import html
        color={link.UP:'#d8f3dc',link.DEGRADED:'#fff3bf',link.LOST:'#ffe3e3'}[state]
        panel=html.Div(f'{state_name} · age {link.link_age:.1f}s · last good packet {packet} · loss {link.loss_pct:.1f}% · {link.frames_per_s:.1f} frames/s · {link.bytes_per_s:.0f} B/s · RTT {link.rtt_ms} ms · rx_bad {link.rx_bad} · switch advised {link.switch_advised} · {status_text}',style={'backgroundColor':color,'padding':'0.75rem'})
        return panel,build_compass_figure(link,cfg),build_trends_figure(link),build_map_figure(link),_command_rows(commands),json.dumps(link.settings,indent=2,default=str) if link.settings else ''
    buttons=['set-center','set-gain','set-vfo','set-active','set-method','set-array','set-doa','request-snapshot','set-rates']
    states=[State('center-freq','value'),State('gain','value'),State('vfo-idx','value'),State('vfo-freq','value'),State('vfo-bw','value'),State('vfo-squelch','value'),State('vfo-fields','value'),State('active-vfos','value'),State('output-vfo','value'),State('doa-method','value'),State('array-type','value'),State('array-dim','value'),State('doa-enable','value'),State('telem-doa','value'),State('telem-spec','value')]
    @app.callback(Output('command-message','children'),[Input(x,'n_clicks') for x in buttons],states,prevent_initial_call=True)
    def submit(*args):
        if commands is None:return 'Command client unavailable'
        vals=args[len(buttons):]; (center,gain,idx,freq,bw,sq,mask,active,out,method,arr,dim,en,dr,sr)=vals
        op=ctx.triggered_id
        try:
            if op=='set-center':opcode,p=1,struct.pack('<I',int(center))
            elif op=='set-gain':opcode,p=2,struct.pack('<H',int(gain))
            elif op=='set-vfo':
                mask=mask or []; m=(1 if 'frequency' in mask else 0)|(2 if 'bandwidth' in mask else 0)|(4 if 'squelch' in mask else 0)
                opcode,p=3,struct.pack('<BBIIb',int(idx),m,int(freq or 0),int(bw or 0),int(sq or 0))
            elif op=='set-active':opcode,p=4,struct.pack('<BB',int(active),int(out))
            elif op=='set-method':opcode,p=5,bytes([int(method)])
            elif op=='set-array':opcode,p=6,struct.pack('<BH',int(arr),int(dim))
            elif op=='set-doa':opcode,p=7,bytes([int(en)])
            elif op=='request-snapshot':opcode,p=8,b''
            else:opcode,p=9,struct.pack('<HH',int(dr),int(sr))
            cid=commands.submit(opcode,p); return f'Submitted command {cid} (opcode {opcode})'
        except (ValueError,TypeError,struct.error) as exc:return f'Invalid command: {exc}'
    return app

def time_text(value):
    import datetime
    return datetime.datetime.fromtimestamp(value,datetime.timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')

def main(argv=None):
    import argparse, time, threading
    from pathlib import Path
    from .link import GroundLink
    from .commands import CommandClient
    try:import tomllib
    except ImportError:import tomli as tomllib
    ap=argparse.ArgumentParser(); ap.add_argument('--config',required=True); args=ap.parse_args(argv)
    cfg=tomllib.loads(Path(args.config).read_text()); t=cfg.get('transport',{}); typ=t.get('type','loopback')
    if typ=='loopback':
        from .transports.loopback import GroundLoopbackTransport
        transport=GroundLoopbackTransport(t.get('host','127.0.0.1'),t.get('port',14561),t.get('bind_host','127.0.0.1'),t.get('bind_port',14560))
    elif typ=='espnow':
        from .transports.espnow_serial import ESPNowSerialTransport
        transport=ESPNowSerialTransport(t['port'],t.get('baudrate',460800))
    elif typ=='mavlink':
        from .transports.mavlink import GroundMAVLinkTransport
        transport=GroundMAVLinkTransport(t['connection'],t.get('target_system',1))
    else:raise ValueError('unknown ground transport '+typ)
    link=GroundLink(); client=CommandClient(transport.send); app=create_app(link,client,cfg)
    def pump():
        last_ping=0
        while True:
            raw=transport.recv()
            if raw:
                msg=link.receive(raw)
                from ..proto.messages import AckMessage
                if isinstance(msg,AckMessage):client.receive_ack(msg)
            client.tick(); now=time.monotonic()
            if now-last_ping>=1:transport.send(link.ping()); last_ping=now
            time.sleep(.005)
    threading.Thread(target=pump,daemon=True).start()
    app.run(host=cfg.get('app',{}).get('host','127.0.0.1'),port=cfg.get('app',{}).get('port',8050),debug=False)
if __name__=='__main__':main()
