"""Lazy ctypes binding to the system librtlsdr library."""
import ctypes
import ctypes.util


class RTLSDR:
    def __init__(self):
        name = ctypes.util.find_library("rtlsdr") or "librtlsdr.so.0"
        try:
            self.lib = ctypes.CDLL(name)
        except OSError as exc:
            raise RuntimeError("librtlsdr is missing; install with: sudo apt install librtlsdr0") from exc
        self._declare()
        self._read_buffers = {}

    def _declare(self):
        lib = self.lib
        lib.rtlsdr_get_device_count.restype = ctypes_uint
        lib.rtlsdr_get_device_usb_strings.argtypes = [ctypes_uint, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
        lib.rtlsdr_open.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes_uint]
        lib.rtlsdr_close.argtypes = [ctypes.c_void_p]
        for name in ("rtlsdr_set_sample_rate", "rtlsdr_set_center_freq", "rtlsdr_set_tuner_gain_mode", "rtlsdr_set_tuner_gain", "rtlsdr_reset_buffer"):
            getattr(lib, name).argtypes = [ctypes.c_void_p, ctypes.c_uint]
        lib.rtlsdr_get_tuner_gains.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        lib.rtlsdr_read_sync.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]

    def count(self):
        return int(self.lib.rtlsdr_get_device_count())

    def usb_strings(self, index):
        buffers = [ctypes.create_string_buffer(256) for _ in range(3)]
        rc = self.lib.rtlsdr_get_device_usb_strings(index, *(ctypes.cast(x, ctypes.c_char_p) for x in buffers))
        return tuple(x.value.decode(errors="replace") for x in buffers) if rc == 0 else ("", "", "")

    def open(self, index):
        handle = ctypes.c_void_p()
        rc = self.lib.rtlsdr_open(ctypes.byref(handle), int(index))
        if rc != 0:
            raise RuntimeError(f"could not open RTL-SDR device {index} (error {rc})")
        return handle

    def close(self, handle):
        self.lib.rtlsdr_close(handle)

    def _call(self, function, handle, value):
        rc = getattr(self.lib, function)(handle, int(value))
        if rc != 0:
            raise RuntimeError(f"{function} failed with error {rc}")

    def set_sample_rate(self, handle, rate): self._call("rtlsdr_set_sample_rate", handle, rate)
    def set_center_freq(self, handle, freq): self._call("rtlsdr_set_center_freq", handle, freq)
    def set_tuner_gain_mode(self, handle, mode): self._call("rtlsdr_set_tuner_gain_mode", handle, mode)
    def set_tuner_gain(self, handle, gain): self._call("rtlsdr_set_tuner_gain", handle, gain)
    def reset_buffer(self, handle): self._call("rtlsdr_reset_buffer", handle, 0)

    def get_tuner_gains(self, handle):
        count = self.lib.rtlsdr_get_tuner_gains(handle, None)
        values = (ctypes.c_int * count)()
        self.lib.rtlsdr_get_tuner_gains(handle, values)
        return list(values)

    def read_sync(self, handle, length):
        length = int(length)
        buffer = self._read_buffers.get(length)
        if buffer is None:
            buffer = (ctypes.c_ubyte * length)()
            self._read_buffers[length] = buffer
        actual = ctypes.c_int()
        rc = self.lib.rtlsdr_read_sync(handle, buffer, length, ctypes.byref(actual))
        if rc != 0:
            raise RuntimeError(f"rtlsdr_read_sync failed with error {rc}")
        return ctypes.string_at(buffer, actual.value)


ctypes_uint = __import__("ctypes").c_uint
