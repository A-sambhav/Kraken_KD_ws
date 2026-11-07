"""Threaded channel sources; fake mode has the same reader interface as RTL hardware."""
from collections import deque
import threading
import time

import numpy as np

from .dsp import clip_fraction, dc_offset, iq_from_u8, power_dbfs, spectrum_db
from .rtl import RTLSDR


def channel_status(last_ok_age, sps, set_rate):
    if last_ok_age is None or last_ok_age >= 1.0 or set_rate <= 0:
        return "NO DATA"
    if sps < 0.9 * set_rate:
        return "SLOW"
    return "DATA OK"


class ChannelReader:
    def __init__(self, source, index, serial, product, center_freq=433_000_000, gain=280, sample_rate=2_400_000, dead=False, error=None):
        self.source, self.index, self.serial, self.product = source, index, serial, product
        self.center_freq, self.gain, self.sample_rate, self.dead = center_freq, gain, sample_rate, dead
        self.raw = b""
        self.samples = 0
        self.sps = 0.0
        self.read_errors = 0
        self.error = error
        self.last_ok = None
        self.history = deque(maxlen=120)
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name=f"kraken-reader-{index}", daemon=True)
        self._configured = None

    def start(self):
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)
        if self.source is not None:
            self.source.close()

    def retune(self, center_freq=None, gain=None, sample_rate=None):
        with self.lock:
            if center_freq is not None: self.center_freq = int(center_freq)
            if gain is not None: self.gain = int(gain)
            if sample_rate is not None: self.sample_rate = int(sample_rate)

    def snapshot(self):
        with self.lock:
            raw, samples, sps, errors, last_ok, error = self.raw, self.samples, self.sps, self.read_errors, self.last_ok, self.error
            freq, rate, gain, history = self.center_freq, self.sample_rate, self.gain, list(self.history)
        iq = iq_from_u8(raw) if raw else np.array([], dtype=np.complex64)
        return {"index": self.index, "serial": self.serial, "product": self.product, "center_freq": freq,
                "sample_rate": rate, "gain": gain, "samples": samples, "sps": sps, "read_errors": errors,
                "last_ok": last_ok, "error": error, "age": None if last_ok is None else max(0.0, time.monotonic() - last_ok),
                "status": channel_status(None if last_ok is None else max(0.0, time.monotonic() - last_ok), sps, rate),
                "power_dbfs": power_dbfs(iq), "clip_fraction": clip_fraction(raw), "dc_offset": dc_offset(iq),
                "spectrum": spectrum_db(iq), "history": history}

    def _run(self):
        if self.source is None:
            return
        last_measure = time.monotonic()
        samples_since = 0
        while not self.stop_event.is_set():
            try:
                with self.lock:
                    freq, rate, gain = self.center_freq, self.sample_rate, self.gain
                current = (freq, gain, rate)
                if current != self._configured and hasattr(self.source, "configure"):
                    self.source.configure(freq, gain, rate)
                    self._configured = current
                raw = self.source.read_sync(2 ** 18)
                if raw:
                    count = len(raw) // 2
                    samples_since += count
                    now = time.monotonic()
                    with self.lock:
                        self.raw, self.samples, self.last_ok = raw, self.samples + count, now
                        if now - last_measure >= 1:
                            self.sps = samples_since / (now - last_measure)
                            samples_since, last_measure = 0, now
                        iq = iq_from_u8(raw)
                        self.history.append((time.time(), power_dbfs(iq)))
            except Exception as exc:
                with self.lock:
                    self.read_errors += 1
                    self.error = str(exc)
                self.stop_event.wait(.05)


class RTLSource:
    def __init__(self, index):
        from .rtl import RTLSDR
        self.api = RTLSDR()
        self.handle = self.api.open(index)
        self.api.set_tuner_gain_mode(self.handle, 1)
        self.gains = self.api.get_tuner_gains(self.handle)

    def configure(self, center_freq, gain, sample_rate):
        self.api.set_center_freq(self.handle, center_freq)
        self.api.set_tuner_gain(self.handle, gain)
        self.api.set_sample_rate(self.handle, sample_rate)
        self.api.reset_buffer(self.handle)

    def read_sync(self, length): return self.api.read_sync(self.handle, length)
    def close(self): self.api.close(self.handle)


class FakeSource:
    def __init__(self, index, rate=2_400_000):
        self.index, self.rate, self.phase, self.closed = index, rate, 0, False
        self.center_freq, self.gain = 433_000_000, 280
        self.deadline = time.monotonic()

    def configure(self, center_freq, gain, sample_rate):
        self.center_freq, self.gain, self.rate = int(center_freq), int(gain), int(sample_rate)
        self.deadline = time.monotonic()

    def read_sync(self, length):
        if self.closed: return b""
        n = int(length) // 2
        self.deadline += n / self.rate
        delay = self.deadline - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        phase = self.phase + np.arange(n, dtype=np.float32) * (index_tone(self.index) / self.rate)
        self.phase = float((phase[-1] + index_tone(self.index) / self.rate) % 1) if n else self.phase
        rng = np.random.default_rng(self.index * 1009 + int(time.monotonic() * 10))
        signal = .5 * np.exp(2j * np.pi * phase) + .025 * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
        out = np.empty(n * 2, dtype=np.uint8)
        out[0::2] = np.clip(np.rint(signal.real * 127.5 + 127.5), 0, 255).astype(np.uint8)
        out[1::2] = np.clip(np.rint(signal.imag * 127.5 + 127.5), 0, 255).astype(np.uint8)
        return out.tobytes()

    def close(self): self.closed = True


def index_tone(index): return (index - 2) * 100_000.0


def make_readers(fake=False, fake_dead=None, freq=433.0, gain=280, rate=2_400_000, count=5):
    readers = []
    gains = []
    if fake:
        for i in range(5):
            readers.append(ChannelReader(FakeSource(i, rate), i, str(1000 + i), "Fake RTL2832U", int(freq * 1e6), gain, rate, dead=(i == fake_dead)))
    else:
        api = RTLSDR()
        count = api.count()
        for i in range(count):
            maker = product = serial = ""
            try:
                maker, product, serial = api.usb_strings(i)
                src = RTLSource(i)
                src.configure(int(freq * 1e6), gain, rate)
                gains = src.gains
                readers.append(ChannelReader(src, i, serial or str(i), product or maker, int(freq * 1e6), gain, rate))
            except Exception as exc:
                detail = str(exc)
                error = f"open failed: {detail}; try replugging / DVB driver / udev rules"
                readers.append(ChannelReader(None, i, serial or str(i), product or maker or "RTL2832U", int(freq * 1e6), gain, rate, error=error))
    if fake:
        gains = [0, 9, 14, 27, 37, 77, 87, 125, 144, 157, 166, 197, 207, 229, 254, 280, 297, 328, 338, 364, 372, 386, 402, 421, 434, 439, 445, 480, 496]
    if not fake:
        # Present the hardware's supported gain steps, shared across tuners.
        for reader in readers:
            reader.gain_options = gains
    for reader in readers:
        if reader.dead:
            continue
        reader.start()
    return readers
