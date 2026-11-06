"""Dash ground station; importing/building layout does not start a server."""
import math
import struct
from pathlib import Path

STATUS_COLORS = {'UP': '#7ccc63', 'OK': '#7ccc63', 'RUNNING': '#7ccc63', 'NO': '#7ccc63', 'DEGRADED': '#f39c12',
                 'STALE': '#f39c12', 'CALIBRATING': '#f39c12',
                 'APPLYING': '#f39c12', 'WAIT_KRAKEN': '#f39c12',
                 'LOST': '#e74c3c', 'DOWN': '#e74c3c', 'FORMAT_WRONG': '#e74c3c',
                 'YES': '#e74c3c', 'NACK': '#e74c3c'}

def status_color(status):
    return STATUS_COLORS.get(str(status).upper(), '#ffffff')

def status_names(kraken_state, bridge_state, doa_method, uptime_s, last_cmd_id, last_cmd_result):
    """Return display-ready names for numeric STATUS fields."""
    kraken = ('OK', 'STALE', 'CALIBRATING', 'DOWN', 'FORMAT_WRONG')
    bridge = ('RUNNING', 'APPLYING', 'WAIT_KRAKEN')
    methods = ('Bartlett', 'Capon', 'MEM', 'TNA', 'MUSIC', 'ROOT-MUSIC')
    results = ('ACCEPTED', 'DONE', 'NACK', 'TIMEOUT', 'DONE_WITH_WARNING')
    def named(values, value):
        value = int(value)
        return values[value] if 0 <= value < len(values) else f'UNKNOWN({value})'
    uptime_s = int(uptime_s)
    uptime = f'{uptime_s // 3600}:{(uptime_s % 3600) // 60:02d}:{uptime_s % 60:02d}'
    return {
        'kraken_state': named(kraken, kraken_state),
        'bridge_state': named(bridge, bridge_state),
        'doa_method': named(methods, doa_method),
        'uptime': uptime,
        'last_command': f'id {int(last_cmd_id)} · {named(results, last_cmd_result)}',
    }

def field_row(label, value):
    from dash import html
    return html.Div([html.Span(str(label),className='field-label'),html.Span(str(value),className='field-value',style={'color':status_color(value) if str(value).upper() in STATUS_COLORS else '#ffffff'})],className='field')

def mhz_to_hz(value):
    return int(round(float(value) * 1_000_000))

def metres_to_mm(value):
    return int(round(float(value) * 1000))

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
        fig.add_trace(go.Scatterpolar(theta=[i*5 for i in range(72)],r=[max(.01,x/255) for x in spectrum.bins],mode='lines',fill='toself',name=f'Spectrum VFO {spectrum.vfo}'))
    fig.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      polar={'angularaxis':{'direction':'clockwise','rotation':90}},title='Bearing and spectrum',height=700)
    return fig

def build_trends_figure(link):
    go=_plotly(); fig=go.Figure()
    for vfo, queue in sorted(link.samples.items()):
        rows=list(queue)
        if rows:
            x=[s['wall_time'] for s in rows]
            fig.add_trace(go.Scatter(x=x,y=[s['rssi_db'] for s in rows],mode='lines',name=f'VFO {vfo} RSSI (dB)'))
            fig.add_trace(go.Scatter(x=x,y=[s['confidence'] for s in rows],mode='lines',name=f'VFO {vfo} confidence',yaxis='y2'))
    fig.update_layout(template='plotly_dark',paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',title='Last 5 minutes',yaxis={'title':'RSSI (dB)'},yaxis2={'title':'Confidence','overlaying':'y','side':'right'})
    return fig

def build_map_figure(link):
    go=_plotly(); fig=go.Figure(); pose=link.pose
    if pose:
        lat,lon=pose.lat_e7/1e7,pose.lon_e7/1e7
        fig.add_trace(go.Scatter(x=[lon],y=[lat],mode='markers',name='Drone POSE',marker={'size':10}))
        doa=link.last_good_doa
        if doa:
            heading=doa['fc_heading_cdeg']/100 if doa['flags']&1 else 0
            bearing=absolute_bearing(doa['bearing_deg'],getattr(link,'array_offset_cfg',0),heading)
            dist=0.5; rad=math.radians(bearing)
            end_lat=lat+dist*math.cos(rad)/111.32
            end_lon=lon+dist*math.sin(rad)/(111.32*max(.01,math.cos(math.radians(lat))))
            fig.add_trace(go.Scatter(x=[lon,end_lon],y=[lat,end_lat],mode='lines',name='Bearing (~500 m)'))
    fig.update_layout(template='plotly_dark',paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',title='Drone map',
                      xaxis={'title':'Longitude','scaleanchor':'y','scaleratio':1},yaxis={'title':'Latitude'},
                      annotations=[] if pose else [{'text':'No position from flight controller yet','xref':'paper','yref':'paper','x':.5,'y':.5,'showarrow':False,'font':{'color':'#ffffff','size':18}}])
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
    def number(id,label,**kw):return html.Div([html.Span(label,className='field-label'),dcc.Input(id=id,type='number',**kw)],className='field')
    def card(title, children, **kwargs): return html.Section([html.H2(title),*children],className=kwargs.pop('className','card'),**kwargs)
    center=number('center-freq','Center frequency (MHz)',step=.001,placeholder='MHz')
    controls=[card('RF Receiver',[center,dcc.Dropdown(id='gain',options=gain,placeholder='Gain'),html.Button('Set center',id='set-center',className='btn'),html.Button('Set gain',id='set-gain',className='btn')])]
    controls += [card('VFO',[number('vfo-idx','VFO index',min=0,max=15),number('vfo-freq','Frequency (MHz)',step=.001),number('vfo-bw','Bandwidth (Hz)'),number('vfo-squelch','Squelch (dB)'),dcc.Checklist(id='vfo-fields',options=[{'label':x,'value':x} for x in ('frequency','bandwidth','squelch')]),number('active-vfos','Active VFOs',min=1,max=16),number('output-vfo','Output VFO (255 = all)',min=0,max=255),html.Button('Set VFO',id='set-vfo',className='btn'),html.Button('Set active/output VFOs',id='set-active',className='btn')])]
    controls += [card('DoA Configuration',[dcc.Dropdown(id='doa-method',options=[{'label':x,'value':i} for i,x in enumerate(('Bartlett','Capon','MEM','TNA','MUSIC','ROOT-MUSIC'))],placeholder='Method'),dcc.Dropdown(id='array-type',options=[{'label':'UCA','value':0},{'label':'ULA','value':1}],placeholder='Array type'),number('array-dim','Array radius / spacing (m)',min=.02,max=2,step=.001),dcc.RadioItems(id='doa-enable',options=[{'label':'Disabled','value':0},{'label':'Enabled','value':1}]),html.Button('Set method',id='set-method',className='btn'),html.Button('Set array',id='set-array',className='btn'),html.Button('Set DOA enable',id='set-doa',className='btn')])]
    controls += [card('Telemetry',[number('telem-doa','DOA rate (Hz)',min=.2,max=10,step=.1),number('telem-spec','Spectrum rate (Hz)',min=0,max=2,step=.1),html.Button('Set telemetry rates',id='set-rates',className='btn')])]
    settings=[card('Current Settings',[html.Button('Request snapshot',id='request-snapshot',className='btn snapshot'),html.Pre(id='settings-snapshot')]),card('Command table',[html.Div(id='command-table'),html.Div(id='command-message')])]
    status=html.Div([card('Link Status',[html.Div(id='link-panel')]),card('Kraken Status',[html.Div(id='kraken-panel')]),card('Latest DoA',[html.Div(id='doa-panel')])])
    doa=html.Div([card('Compass',[html.Div(id='max-doa'),dcc.Graph(id='compass',figure=empty,config={'displayModeBar':False})],className='card doa-card'),card('RSSI and confidence',[dcc.Graph(id='trends',figure=empty)])])
    map_page=html.Div([card('Map',[dcc.Graph(id='map-panel',figure=empty)],className='card map-card')])
    tabs=dcc.Tabs(id='pages',value='status',className='tabs',children=[dcc.Tab(label=label,value=value,children=content) for label,value,content in [('Status','status',status),('DoA Estimation','doa',doa),('Settings','settings',html.Div(controls+settings)),('Map','map',map_page)]])
    return html.Div([dcc.Interval(id='refresh',interval=500,n_intervals=0),html.Header(html.H1('KrakenLink Ground')),tabs])

def create_app(link=None, commands=None, cfg=None):
    from dash import Dash, Input, Output, State, ctx, no_update
    import json
    app=Dash(__name__,assets_folder=str(Path(__file__).with_name('assets'))); app.layout=create_layout(link,commands); cfg=cfg or {}
    @app.callback(Output('link-panel','children'),Output('compass','figure'),Output('trends','figure'),Output('map-panel','figure'),Output('command-table','children'),Output('settings-snapshot','children'),Output('kraken-panel','children'),Output('doa-panel','children'),Output('max-doa','children'),Input('refresh','n_intervals'))
    def refresh(_):
        if link is None:return ('LOST',build_compass_figure(type('L',(),{'samples':{},'spectrum':None})(),cfg),build_trends_figure(type('L',(),{'samples':{}})()),build_map_figure(type('L',(),{'pose':None,'last_good_doa':None})()),_command_rows(commands), '', '', '', '')
        state=link.update(); status=link.status
        state_name={0:'UP',1:'DEGRADED',2:'LOST'}[state]
        status_text='kraken_state unavailable · bridge_state unavailable'
        if status:status_text=f'kraken_state {status.kraken_state} · bridge_state {status.bridge_state}'
        packet='never' if link.last_good_packet is None else time_text(link.last_good_packet.get('wall_time'))
        link.array_offset_cfg=cfg.get('array_offset_cfg',0)
        from dash import html
        rtt='—' if link.rtt_ms is None else f'{round(link.rtt_ms):.0f} ms'
        panel=html.Div([field_row('State',state_name),field_row('Link age',f'{link.link_age:.1f}s'),field_row('Last good packet',packet),field_row('Loss',f'{link.loss_pct:.1f}%'),field_row('Frames/s',f'{link.frames_per_s:.1f}'),field_row('B/s',f'{link.bytes_per_s:.0f}'),field_row('RTT',rtt),field_row('rx_bad',link.rx_bad),field_row('Switch advised','Yes' if link.switch_advised else 'No')],className='field-list')
        k=status
        names=status_names(k.kraken_state,k.bridge_state,k.doa_method,k.uptime_s,k.last_cmd_id,k.last_cmd_result) if k else None
        kraken=html.Div([field_row('Kraken state',names['kraken_state'] if k else '—'),field_row('Bridge state',names['bridge_state'] if k else '—'),field_row('Center frequency',f'{k.center_freq_hz/1e6:.3f} MHz' if k else '—'),field_row('Gain',f'{k.gain_x10/10:.1f} dB' if k else '—'),field_row('Active VFOs',getattr(k,'active_vfos','—')),field_row('DoA method',names['doa_method'] if k else '—'),field_row('Data age',f'{k.kraken_data_age_ms} ms' if k else '—'),field_row('CPU temp/load',f'{k.cpu_temp_c}°C / {k.cpu_load_pct}%' if k else '—'),field_row('Uptime',names['uptime'] if k else '—'),field_row('Last command',names['last_command'] if k else '—')])
        rows=[]
        for vfo, samples in sorted(link.samples.items()):
            if samples:
                s=samples[-1]; heading=s['fc_heading_cdeg']/100 if s['flags']&1 else 0
                rows.extend([html.H3(f'VFO {vfo}',className='vfo-heading'),field_row('Bearing (rel)',f"{s['bearing_deg']:.1f}°"),field_row('Bearing (abs)',f"{absolute_bearing(s['bearing_deg'],cfg.get('array_offset_cfg',0),heading):.1f}°"),field_row('Confidence',f"{s['confidence']}%"),field_row('RSSI',f"{s['rssi_db']:.1f} dB"),field_row('Frequency',f"{s['freq_hz']/1e6:.3f} MHz")])
        latest=html.Div(rows or [field_row('DoA','No samples')])
        angle=f"MAX DOA Angle: {link.last_good_doa['bearing_deg']:.1f}°" if link.last_good_doa else 'MAX DOA Angle: —'
        return panel,build_compass_figure(link,cfg),build_trends_figure(link),build_map_figure(link),_command_rows(commands),json.dumps(link.settings,indent=2,default=str) if link.settings else '',kraken,latest,angle
    buttons=['set-center','set-gain','set-vfo','set-active','set-method','set-array','set-doa','request-snapshot','set-rates']
    states=[State('center-freq','value'),State('gain','value'),State('vfo-idx','value'),State('vfo-freq','value'),State('vfo-bw','value'),State('vfo-squelch','value'),State('vfo-fields','value'),State('active-vfos','value'),State('output-vfo','value'),State('doa-method','value'),State('array-type','value'),State('array-dim','value'),State('doa-enable','value'),State('telem-doa','value'),State('telem-spec','value')]
    @app.callback(Output('command-message','children'),[Input(x,'n_clicks') for x in buttons],states,prevent_initial_call=True)
    def submit(*args):
        if commands is None:return 'Command client unavailable'
        vals=args[len(buttons):]; (center,gain,idx,freq,bw,sq,mask,active,out,method,arr,dim,en,dr,sr)=vals
        op=ctx.triggered_id
        try:
            if op=='set-center':opcode,p=1,struct.pack('<I',mhz_to_hz(center))
            elif op=='set-gain':opcode,p=2,struct.pack('<H',int(gain))
            elif op=='set-vfo':
                mask=mask or []; m=(1 if 'frequency' in mask else 0)|(2 if 'bandwidth' in mask else 0)|(4 if 'squelch' in mask else 0)
                opcode,p=3,struct.pack('<BBIIb',int(idx),m,mhz_to_hz(freq or 0),int(bw or 0),int(sq or 0))
            elif op=='set-active':opcode,p=4,struct.pack('<BB',int(active),int(out))
            elif op=='set-method':opcode,p=5,bytes([int(method)])
            elif op=='set-array':opcode,p=6,struct.pack('<BH',int(arr),metres_to_mm(dim))
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
