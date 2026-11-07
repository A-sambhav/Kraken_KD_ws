"""Small, dependency-light DSP helpers for RTL-SDR unsigned IQ samples."""
import numpy as np


def iq_from_u8(raw):
    values = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
    if values.size % 2:
        values = values[:-1]
    i = (values[0::2] - 127.5) / 127.5
    q = (values[1::2] - 127.5) / 127.5
    return (i + 1j * q).astype(np.complex64)


def power_dbfs(iq):
    iq = np.asarray(iq)
    if not iq.size:
        return float("nan")
    return float(10 * np.log10(max(float(np.mean(np.abs(iq) ** 2)), 1e-20)))


def clip_fraction(raw_u8):
    values = np.frombuffer(raw_u8, dtype=np.uint8)
    return float(np.count_nonzero((values == 0) | (values == 255)) / values.size) if values.size else 0.0


def spectrum_db(iq, nfft=1024):
    iq = np.asarray(iq)
    nfft = int(nfft)
    if nfft <= 0:
        raise ValueError("nfft must be positive")
    frames = iq.size // nfft
    if not frames:
        return np.full(nfft, -200.0, dtype=np.float64)
    window = np.hanning(nfft)
    blocks = iq[:frames * nfft].reshape(frames, nfft)
    power = np.mean(np.abs(np.fft.fft(blocks * window, axis=1)) ** 2, axis=0) / max(np.sum(window ** 2), 1.0)
    return (10 * np.log10(np.maximum(np.fft.fftshift(power), 1e-20))).astype(np.float64)


def dc_offset(iq):
    iq = np.asarray(iq)
    return complex(np.mean(iq)) if iq.size else 0j
