"""Typed application messages for KLF v1."""
from dataclasses import dataclass
import struct

DOA, SPECTRUM, STATUS, POSE, SETTINGS, CMD, ACK, PING, PONG = 1,2,3,4,5,0x10,0x11,0x20,0x21

class MessageError(ValueError): pass
def _pack(fmt, *values):
    try: return struct.pack('<'+fmt, *values)
    except struct.error as e: raise MessageError(str(e)) from e
def _unpack(fmt, data, size):
    if len(data) != size: raise MessageError(f"expected {size} payload bytes, got {len(data)}")
    return struct.unpack('<'+fmt, data)

@dataclass(frozen=True)
class DOAMessage:
    vfo:int; flags:int; kraken_ts_ms:int; bearing_cdeg:int; confidence:int; rssi_ddb:int; freq_hz:int; latency_ms:int; fc_heading_cdeg:int
    TYPE=DOA
    def encode(self): return _pack('BBQHBhIHH',self.vfo,self.flags,self.kraken_ts_ms,self.bearing_cdeg,self.confidence,self.rssi_ddb,self.freq_hz,self.latency_ms,self.fc_heading_cdeg)
    @classmethod
    def decode(cls,b): return cls(*_unpack('BBQHBhIHH',b,23))

@dataclass(frozen=True)
class SpectrumMessage:
    vfo:int; kraken_ts_ms:int; peak_ddb:int; bins:bytes
    TYPE=SPECTRUM
    def encode(self):
        if len(self.bins)!=72: raise MessageError('spectrum requires 72 bins')
        return _pack('BQH',self.vfo,self.kraken_ts_ms,self.peak_ddb)+bytes(self.bins)
    @classmethod
    def decode(cls,b):
        if len(b)!=83: raise MessageError('expected 83 payload bytes')
        v,t,p=_unpack('BQH',b[:11],11); return cls(v,t,p,b[11:])

@dataclass(frozen=True)
class StatusMessage:
    bridge_state:int; kraken_state:int; link_state:int; center_freq_hz:int; gain_x10:int; active_vfos:int; doa_method:int; en_doa:int; kraken_data_age_ms:int; cpu_temp_c:int; cpu_load_pct:int; uptime_s:int; last_cmd_id:int; last_cmd_result:int; tx_dropped:int; rx_bad:int; flags:int
    TYPE=STATUS
    def encode(self): return _pack('BBB I H BBB H b B I H B H H B'.replace(' ',''),self.bridge_state,self.kraken_state,self.link_state,self.center_freq_hz,self.gain_x10,self.active_vfos,self.doa_method,self.en_doa,self.kraken_data_age_ms,self.cpu_temp_c,self.cpu_load_pct,self.uptime_s,self.last_cmd_id,self.last_cmd_result,self.tx_dropped,self.rx_bad,self.flags)
    @classmethod
    def decode(cls,b): return cls(*_unpack('BBBIHBBBHbBIH BHHB'.replace(' ',''),b,28))

@dataclass(frozen=True)
class PoseMessage:
    fc_time_boot_ms:int; lat_e7:int; lon_e7:int; rel_alt_dm:int; heading_cdeg:int; groundspeed_cms:int; fix_type:int; sats:int
    TYPE=POSE
    def encode(self): return _pack('I i i h H H B B'.replace(' ',''),self.fc_time_boot_ms,self.lat_e7,self.lon_e7,self.rel_alt_dm,self.heading_cdeg,self.groundspeed_cms,self.fix_type,self.sats)
    @classmethod
    def decode(cls,b): return cls(*_unpack('Iii hHHBB'.replace(' ',''),b,20))

@dataclass(frozen=True)
class SettingsMessage:
    cmd_id:int; part:int; parts:int
    # Part 0 globals; parts 1/2 carry exactly eight (freq,bw,squelch) tuples.
    body:bytes
    TYPE=SETTINGS
    def encode(self):
        want=19 if self.part==0 else 72
        if self.part not in (0,1,2) or self.parts!=3 or len(self.body)!=want: raise MessageError('invalid SETTINGS part/body')
        return _pack('HBB',self.cmd_id,self.part,self.parts)+self.body
    @classmethod
    def decode(cls,b):
        if len(b)<4: raise MessageError('short SETTINGS header')
        cmd,part,parts=_unpack('HBB',b[:4],4); obj=cls(cmd,part,parts,b[4:]); obj.encode(); return obj
    @classmethod
    def globals(cls,cmd_id,center_freq_hz,gain_x10,doa_method,array_type,array_dim_mm,en_doa,active_vfos,output_vfo,dsp_decimation,doa_data_format_ok,telem_doa_hz_x10,telem_spec_hz_x10):
        body=_pack('I H B B H B B B B B H H',center_freq_hz,gain_x10,doa_method,array_type,array_dim_mm,en_doa,active_vfos,output_vfo,dsp_decimation,doa_data_format_ok,telem_doa_hz_x10,telem_spec_hz_x10)
        return cls(cmd_id,0,3,body)
    @classmethod
    def vfos(cls,cmd_id,part,values):
        if part not in (1,2) or len(values)!=8: raise MessageError('VFO SETTINGS part requires eight records')
        return cls(cmd_id,part,3,b''.join(_pack('IIb',*v) for v in values))

@dataclass(frozen=True)
class CommandMessage:
    cmd_id:int; opcode:int; params:bytes=b''
    TYPE=CMD
    def encode(self):
        if len(self.params)>16: raise MessageError('CMD params exceed 16 bytes')
        return _pack('HB',self.cmd_id,self.opcode)+bytes(self.params)
    @classmethod
    def decode(cls,b):
        if not 3<=len(b)<=19: raise MessageError('CMD payload must be 3..19 bytes')
        cmd,op=_unpack('HB',b[:3],3); return cls(cmd,op,b[3:])

@dataclass(frozen=True)
class AckMessage:
    cmd_id:int; opcode:int; result:int; reason:int; detail:int=0; elapsed_ds:int=0
    TYPE=ACK
    def encode(self): return _pack('HBBBBH',self.cmd_id,self.opcode,self.result,self.reason,self.detail,self.elapsed_ds)
    @classmethod
    def decode(cls,b): return cls(*_unpack('HBBBBH',b,8))

@dataclass(frozen=True)
class PingMessage:
    ground_time_ms:int; ground_rx_count:int
    TYPE=PING
    def encode(self): return _pack('IH',self.ground_time_ms,self.ground_rx_count)
    @classmethod
    def decode(cls,b): return cls(*_unpack('IH',b,6))
@dataclass(frozen=True)
class PongMessage:
    ground_time_ms:int; bridge_uptime_ms:int; bridge_rx_count:int
    TYPE=PONG
    def encode(self): return _pack('IIH',self.ground_time_ms,self.bridge_uptime_ms,self.bridge_rx_count)
    @classmethod
    def decode(cls,b): return cls(*_unpack('IIH',b,10))

DECODERS={c.TYPE:c.decode for c in (DOAMessage,SpectrumMessage,StatusMessage,PoseMessage,SettingsMessage,CommandMessage,AckMessage,PingMessage,PongMessage)}
def decode_message(msg_type,payload):
    try: return DECODERS[msg_type](payload)
    except KeyError: raise MessageError(f'unknown message type {msg_type:#x}')
def encode_message(message): return message.TYPE,message.encode()
