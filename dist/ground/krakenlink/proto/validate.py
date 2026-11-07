"""Pure command validation and settings-key whitelist generation."""
from dataclasses import dataclass
from enum import IntEnum
import math, struct

class NackReason(IntEnum):
    OK=0; BAD_OPCODE=1; BAD_LEN=2; OUT_OF_RANGE=3; VFO_OUT_OF_WINDOW=4; INCOMPATIBLE=5; BUSY=6; KRAKEN_DOWN=7; WRITE_FAILED=8; NOT_CONSUMED=9; CALIB_TIMEOUT=10; VFO_MOVED=11

@dataclass(frozen=True)
class Nack:
    reason:NackReason
    detail:int=0

OPS={1:4,2:2,3:11,4:2,5:1,6:3,7:1,8:0,9:4}
GAIN_X10={0,9,14,27,37,77,87,125,144,157,166,197,207,229,254,280,297,328,338,364,372,386,402,421,434,439,445,480,496}
DOA_METHODS=('Bartlett','Capon','MEM','TNA','MUSIC','ROOT-MUSIC')

def _bad(reason,detail=0): return Nack(reason,detail)
def _settings_value(key, value): return {key:value}

def validate_command(opcode:int, params:bytes, settings:dict, *, daq_fs=2_400_000, retune_vfo_policy='reject', busy=False):
    """Return Nack or a dict containing only approved settings keys.

    For SET_TELEM_RATE the returned keys are bridge-local telemetry settings.
    """
    p=bytes(params)
    if opcode not in OPS: return _bad(NackReason.BAD_OPCODE)
    if len(p)!=OPS[opcode]: return _bad(NackReason.BAD_LEN)
    if busy: return _bad(NackReason.BUSY)
    active=int(settings.get('active_vfos',1)); center=float(settings.get('center_freq',0))*1_000_000
    dec=max(1,int(settings.get('dsp_decimation',1))); fs_eff=float(daq_fs)/dec
    arr=settings.get('ant_arrangement','UCA')
    if opcode==1:
        (hz,)=struct.unpack('<I',p)
        if not 24_000_000<=hz<=1_766_000_000 or hz%1000: return _bad(NackReason.OUT_OF_RANGE)
        bad=[]
        for i in range(active):
            f=int(settings.get(f'vfo_freq_{i}',round(center))); bw=int(settings.get(f'vfo_bw_{i}',100))
            if abs(f-hz)+bw/2>fs_eff/2: bad.append(i)
        if bad and retune_vfo_policy!='allow': return _bad(NackReason.VFO_OUT_OF_WINDOW,bad[0])
        return _settings_value('center_freq',hz/1_000_000.0)
    if opcode==2:
        (gain,)=struct.unpack('<H',p)
        if gain not in GAIN_X10: return _bad(NackReason.OUT_OF_RANGE)
        return _settings_value('uniform_gain',gain/10.0)
    if opcode==3:
        idx,mask,freq,bw,sq=struct.unpack('<BBIIb',p)
        if idx>15 or mask==0 or mask&~7: return _bad(NackReason.OUT_OF_RANGE)
        if mask&1 and not 0<=freq<=0xffffffff: return _bad(NackReason.OUT_OF_RANGE)
        if mask&2 and not 100<=bw<=fs_eff: return _bad(NackReason.OUT_OF_RANGE)
        if mask&4 and not -150<=sq<=0: return _bad(NackReason.OUT_OF_RANGE)
        newf=freq if mask&1 else int(settings.get(f'vfo_freq_{idx}',center)); newbw=bw if mask&2 else int(settings.get(f'vfo_bw_{idx}',100))
        postcenter=center
        if abs(newf-postcenter)+newbw/2>fs_eff/2: return _bad(NackReason.VFO_OUT_OF_WINDOW,idx)
        out={}
        if mask&1: out[f'vfo_freq_{idx}']=freq
        if mask&2: out[f'vfo_bw_{idx}']=bw
        if mask&4: out[f'vfo_squelch_{idx}']=sq
        return out
    if opcode==4:
        count,out=struct.unpack('<BB',p)
        if not 1<=count<=16 or not (out==255 or out<count): return _bad(NackReason.OUT_OF_RANGE)
        return {'active_vfos':count,'output_vfo':out}
    if opcode==5:
        (method,)=p
        if method>5: return _bad(NackReason.OUT_OF_RANGE)
        if method==5 and str(arr).upper()!='ULA': return _bad(NackReason.INCOMPATIBLE)
        return {'doa_method':DOA_METHODS[method]}
    if opcode==6:
        typ,dim=struct.unpack('<BH',p)
        if typ not in (0,1) or not 20<=dim<=2000: return _bad(NackReason.OUT_OF_RANGE)
        return {'ant_arrangement':'UCA' if typ==0 else 'ULA','ant_spacing_meters':dim/1000.0}
    if opcode==7:
        (on,)=p
        if on not in (0,1): return _bad(NackReason.OUT_OF_RANGE)
        return {'en_doa':bool(on)}
    if opcode==8: return {}
    doa,spec=struct.unpack('<HH',p)
    if not 2<=doa<=100 or not 0<=spec<=20: return _bad(NackReason.OUT_OF_RANGE)
    return {'telem_doa_hz_x10':doa,'telem_spec_hz_x10':spec}

validate = validate_command
