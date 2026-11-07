import numpy as np

from krakenlink.tools.kraken_view.dsp import clip_fraction, dc_offset, iq_from_u8, power_dbfs, spectrum_db


def test_u8_iq_scaling_and_power():
    raw = np.array([0, 255, 127, 128], dtype=np.uint8).tobytes()
    iq = iq_from_u8(raw)
    assert iq.dtype == np.complex64
    assert iq[0].real == -1 and iq[0].imag == 1
    assert np.allclose(iq[1], complex(-.5 / 127.5, .5 / 127.5))
    tone = np.exp(2j * np.pi * np.arange(4096) / 64).astype(np.complex64)
    assert abs(power_dbfs(tone) - 0) < .01
    amplitude_half = .5 * tone
    assert abs(power_dbfs(amplitude_half) - (-6.0206)) < .02


def test_clip_fraction_spectrum_and_dc():
    raw = np.array([0, 1, 255, 254, 0, 255], dtype=np.uint8).tobytes()
    assert clip_fraction(raw) == 4 / 6
    nfft = 1024
    iq = np.exp(2j * np.pi * 37 * np.arange(nfft * 4) / nfft)
    spec = spectrum_db(iq, nfft)
    assert len(spec) == nfft
    assert abs(int(np.argmax(spec)) - (nfft // 2 + 37)) <= 1
    assert abs(dc_offset(iq)) < 1e-12
    assert abs(dc_offset(iq + (.2 - .1j)) - (.2 - .1j)) < 1e-12


def test_full_scale_iq_tone_power_convention():
    # A real full-scale ADC sinusoid has mean-square power 1/2, or -3.01 dBFS.
    iq = np.cos(2 * np.pi * np.arange(8192) / 64).astype(np.complex64)
    assert abs(power_dbfs(iq) - (-3.0103)) < .01
