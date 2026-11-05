"""KLF v1 frame and COBS codecs (stdlib only)."""
from dataclasses import dataclass
import struct

MAGIC = 0xA7
VERSION = 1
MAX_FRAME_SIZE = 128
MAX_PAYLOAD = 120
RETRY = 0x01

class FrameError(ValueError):
    """Malformed or unsupported KLF frame."""

def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc

@dataclass(frozen=True)
class Frame:
    type: int
    seq: int
    payload: bytes = b""
    retry: bool = False
    version: int = VERSION

    def encode(self) -> bytes:
        if not 0 <= self.type <= 255 or not 0 <= self.seq <= 65535:
            raise ValueError("type or seq outside wire range")
        if self.version != VERSION:
            raise ValueError("only KLF version 1 can be encoded")
        if len(self.payload) > MAX_PAYLOAD:
            raise ValueError("payload exceeds 120 bytes")
        header = struct.pack("<BBBBH", MAGIC, (VERSION << 4) | (RETRY if self.retry else 0), self.type, len(self.payload), self.seq)
        body = header + self.payload
        return body + struct.pack("<H", crc16_ccitt_false(body))

def encode_frame(frame_or_type, seq=None, payload=b"", retry=False) -> bytes:
    frame = frame_or_type if isinstance(frame_or_type, Frame) else Frame(frame_or_type, seq, bytes(payload), retry)
    return frame.encode()

def decode_frame(data: bytes) -> Frame:
    data = bytes(data)
    if len(data) < 8: raise FrameError("truncated")
    magic, vf, typ, length, seq = struct.unpack_from("<BBBBH", data)
    if magic != MAGIC: raise FrameError("magic")
    if vf >> 4 != VERSION or vf & 0x0E: raise FrameError("version")
    if length > MAX_PAYLOAD: raise FrameError("length")
    if len(data) != length + 8: raise FrameError("size")
    expected, = struct.unpack_from("<H", data, len(data)-2)
    if crc16_ccitt_false(data[:-2]) != expected: raise FrameError("crc")
    return Frame(typ, seq, data[6:-2], bool(vf & RETRY))

def cobs_encode(data: bytes) -> bytes:
    data = bytes(data); out = bytearray([0]); code_index = 0; code = 1
    for b in data:
        if b == 0:
            out[code_index] = code; code_index = len(out); out.append(0); code = 1
        else:
            out.append(b); code += 1
            if code == 0xFF:
                out[code_index] = code; code_index = len(out); out.append(0); code = 1
    out[code_index] = code
    return bytes(out)

def cobs_decode(data: bytes) -> bytes:
    data = bytes(data)
    if not data or 0 in data: raise ValueError("COBS input must be nonempty and omit delimiter")
    out = bytearray(); i = 0
    while i < len(data):
        code = data[i]
        if code == 0 or i + code > len(data) + 1: raise ValueError("invalid COBS code")
        i += 1; out.extend(data[i:i+code-1]); i += code-1
        if code < 0xFF and i < len(data): out.append(0)
    return bytes(out)
