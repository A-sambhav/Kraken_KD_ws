import random, struct
import pytest
from krakenlink.proto.frame import *
from krakenlink.proto.messages import *
from krakenlink.proto.csv_parser import *
from krakenlink.proto.validate import *

def test_crc_vector_and_single_bit_corruption():
    assert crc16_ccitt_false(b'123456789') == 0x29B1
    raw=encode_frame(Frame(1,42,b'payload'))
    for i in range(len(raw)):
        damaged=bytearray(raw); damaged[i]^=1
        with pytest.raises(FrameError): decode_frame(damaged)

def test_frame_round_trip_and_rejections():
    for msg in [DOAMessage(15,7,2**64-1,35999,255,-32768,0xffffffff,65535,35999),
        SpectrumMessage(15,2**64-1,65535,bytes(range(72))),
        StatusMessage(255,4,2,0xffffffff,65535,255,5,1,65535,-128,100,0xffffffff,65535,4,65535,65535,255),
        PoseMessage(0xffffffff,-2147483648,2147483647,-32768,35999,65535,255,255),
        SettingsMessage.globals(65535,0xffffffff,65535,5,2,2000,1,16,255,255,1,65535,65535),
        SettingsMessage.vfos(1,1,[(0xffffffff,0xffffffff,-128)]*8),
        SettingsMessage.vfos(1,2,[(0,100,-128)]*8),
        CommandMessage(65535,255,b'0123456789abcdef'), AckMessage(65535,255,4,11,255,65535),
        PingMessage(0xffffffff,65535),PongMessage(0xffffffff,0xffffffff,65535)]:
        kind,payload=encode_message(msg); frame=decode_frame(encode_frame(Frame(kind,65535,payload,retry=True)))
        assert frame.seq==65535 and frame.retry
        assert decode_message(kind,frame.payload)==msg
        assert len(encode_frame(Frame(kind,0,payload)))<=128
    good=encode_frame(Frame(1,1,b'x'))
    for bad in [b'\x00'+good[1:], bytes([0xa7,0x20])+good[2:], good[:3]+b'\xff'+good[4:],good[:-1],good+b'\0']:
        with pytest.raises(FrameError): decode_frame(bad)
    with pytest.raises(FrameError): decode_frame(bytes([0xa7,0x10,1,121,0,0])+bytes(123)+bytes(2))

def test_cobs_round_trip_with_zeroes():
    for data in (b'',b'\0',b'abc',bytes(range(256)),b'a\0b\0\0c'):
        assert cobs_decode(cobs_encode(data))==data

def make_line(bearing='360', spectrum=None):
    fields=['1000',bearing,'88','-30','433000000','0','12','sim','1','2','3','4','gps','0','0','0','0']
    fields += [str(x) for x in (spectrum if spectrum is not None else [0]*360)]
    return ','.join(fields)

def test_csv_count_partial_and_360_normalization():
    sample=parse_doa_line(make_line())
    assert sample.bearing_deg==0
    with pytest.raises(CSVLineError): parse_doa_line('1,2,3')

def test_spectrum_rotation_and_max_pool():
    theta=[0]*360; theta[359]=1.0
    peak,bins=spectrum_bins(theta)
    assert peak==10 and bins[0]==255 and sum(bins)==255
    # i=90 maps to compass 270, which is bin 54.
    theta=[0]*360; theta[90]=4
    _,bins=spectrum_bins(theta)
    assert bins[54]==255 and bins[0]==0

def test_spectrum_bins_are_centered_and_wrap_at_north():
    theta=[0]*360; theta[2]=1.0  # compass 358 belongs to the bin centered at 0
    _,bins=spectrum_bins(theta)
    assert bins[0]==255 and sum(bins)==255
    theta=[0]*360; theta[357]=1.0  # compass 3 belongs to the bin centered at 5
    _,bins=spectrum_bins(theta)
    assert bins[1]==255 and bins[0]==0

def settings(**kw):
    s={'center_freq':433.0,'active_vfos':1,'dsp_decimation':1,'ant_arrangement':'UCA','vfo_freq_0':433000000,'vfo_bw_0':100000,'vfo_squelch_0':-100}
    s.update(kw); return s

def cmd(op,*vals):
    formats={1:'<I',2:'<H',3:'<BBIIb',4:'<BB',5:'<B',6:'<BH',7:'<B',8:'',9:'<HH'}
    return struct.pack(formats[op],*vals)

@pytest.mark.parametrize('op,valid,bad',[
 (1,(24000000,),(23999999,)),(2,(0,),(1,)),(3,(0,1,433000000,100000,-100),(0,0,433000000,100000,-100)),
 (4,(1,0),(0,0)),(5,(0,),(6,)),(6,(0,20),(3,20)),(7,(0,),(2,)),(8,(),()),(9,(2,0),(1,0))])
def test_opcode_lengths_min_and_range(op,valid,bad):
    if op==1: # center valid at low edge; existing VFO outside this new window, so allow retune
        res=validate_command(op,cmd(op,*valid),settings(),retune_vfo_policy='allow')
    elif op==3:
        res=validate_command(op,cmd(op,*valid),settings())
    else: res=validate_command(op,cmd(op,*valid),settings())
    assert isinstance(res,dict),res
    if bad:
        assert isinstance(validate_command(op,cmd(op,*bad),settings()),Nack)
    if op==8:
        assert validate_command(op,b'',settings())=={}
        assert validate_command(op,b'\0',settings()).reason==NackReason.BAD_LEN
    else:
        assert isinstance(validate_command(op,b'',settings()),Nack)

def test_gain_full_set_and_nonmember():
    for gain in GAIN_X10: assert validate_command(2,cmd(2,gain),settings())=={'uniform_gain':gain/10}
    assert validate_command(2,cmd(2,150),settings())==Nack(NackReason.OUT_OF_RANGE)

@pytest.mark.parametrize('dec', [1,2])
def test_vfo_window_edge_pass_and_one_hz_fail(dec):
    fs=2_400_000/dec; edge=int(fs/2-50_000)
    assert isinstance(validate_command(3,cmd(3,0,1,433_000_000+int(edge),100_000,-100),settings(dsp_decimation=dec)),dict)
    assert validate_command(3,cmd(3,0,1,433_000_000+int(edge)+1,100_000,-100),settings(dsp_decimation=dec)).reason==NackReason.VFO_OUT_OF_WINDOW

def test_center_retune_policy_root_music_and_units():
    s=settings(vfo_freq_0=433000000)
    assert validate_command(1,cmd(1,435000000),s).reason==NackReason.VFO_OUT_OF_WINDOW
    assert validate_command(1,cmd(1,435000000),s,retune_vfo_policy='allow')=={'center_freq':435.0}
    assert validate_command(5,cmd(5,5),s).reason==NackReason.INCOMPATIBLE
    assert validate_command(5,cmd(5,5),settings(ant_arrangement='ULA'))=={'doa_method':'ROOT-MUSIC'}
    assert validate_command(5,cmd(5,0),s)=={'doa_method':'Bartlett'}
    assert validate_command(1,cmd(1,433123000),s)=={'center_freq':433.123}
    assert validate_command(3,cmd(3,0,1,433000000,100000,-100),s)=={'vfo_freq_0':433000000}

def test_remaining_opcode_ranges_and_bad_opcodes():
    assert validate_command(4,cmd(4,16,255),settings())=={'active_vfos':16,'output_vfo':255}
    assert isinstance(validate_command(4,cmd(4,1,1),settings()),Nack)
    assert validate_command(6,cmd(6,1,2000),settings())['ant_spacing_meters']==2.0
    assert isinstance(validate_command(6,cmd(6,0,19),settings()),Nack)
    assert validate_command(7,cmd(7,1),settings())=={'en_doa':True}
    assert isinstance(validate_command(9,cmd(9,100,20),settings()),dict)
    assert isinstance(validate_command(9,cmd(9,100,21),settings()),Nack)
    assert validate_command(99,b'',settings()).reason==NackReason.BAD_OPCODE

