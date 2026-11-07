import time
import ctypes

from krakenlink.tools.kraken_view.app import create_app
from krakenlink.tools.kraken_view.source import channel_status, make_readers
import krakenlink.tools.kraken_view.source as source_module
from krakenlink.tools.kraken_view.rtl import RTLSDR


def test_channel_status_boundaries():
    assert channel_status(None, 2_400_000, 2_400_000) == "NO DATA"
    assert channel_status(1.0, 2_400_000, 2_400_000) == "NO DATA"
    assert channel_status(.999, 2_159_999, 2_400_000) == "SLOW"
    assert channel_status(.999, 2_160_000, 2_400_000) == "DATA OK"


def test_fake_app_layout_and_refresh_cards():
    readers = make_readers(fake=True, fake_dead=3)
    app = None
    try:
        app = create_app(readers, 5)
        time.sleep(1.2)
        result = app.kraken_refresh(1)
        assert len(result[1]) == 5
        assert [card.children[1].children for card in result[1]] == ["DATA OK", "DATA OK", "DATA OK", "NO DATA", "DATA OK"]
        assert app.layout is not None
    finally:
        for reader in readers:
            reader.close()


def test_fake_source_rate_is_measured_close_to_configured_rate():
    readers = make_readers(fake=True, rate=240_000, count=1)
    try:
        time.sleep(1.6)
        row = readers[0].snapshot()
        assert abs(row["sps"] - 240_000) <= 24_000
    finally:
        for reader in readers:
            reader.close()


def test_open_failure_produces_no_data_reader_with_error(monkeypatch):
    class MockRTL:
        def count(self): return 1
        def usb_strings(self, index): return ("maker", "product", "serial")

    monkeypatch.setattr(source_module, "RTLSource", lambda index: (_ for _ in ()).throw(RuntimeError("error -3")))
    monkeypatch.setattr(source_module, "RTLSDR", MockRTL)
    readers = make_readers()
    assert len(readers) == 1
    row = readers[0].snapshot()
    assert row["status"] == "NO DATA"
    assert "error -3" in row["error"]
    readers[0].close()


def test_zero_devices_page_message():
    app = create_app([], 0)
    summary = app.kraken_refresh(1)[0]
    assert "No KrakenSDR found (0 devices with USB ID 0bda:2838)" in summary.children


def test_rtl_read_sync_uses_string_at_and_reuses_buffer(monkeypatch):
    api = RTLSDR.__new__(RTLSDR)
    api._read_buffers = {}
    class MockLib:
        def rtlsdr_read_sync(self, handle, buffer, length, actual_ptr):
            ctypes.memmove(buffer, b"abcd", 4)
            ctypes.cast(actual_ptr, ctypes.POINTER(ctypes.c_int))[0] = 4
            return 0
    api.lib = MockLib()
    calls = []
    monkeypatch.setattr(ctypes, "string_at", lambda buffer, length: calls.append(length) or b"abcd")
    assert api.read_sync(None, 16) == b"abcd"
    allocated = api._read_buffers[16]
    assert api.read_sync(None, 16) == b"abcd"
    assert api._read_buffers[16] is allocated
    assert calls == [4, 4]
