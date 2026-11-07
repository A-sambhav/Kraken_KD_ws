"""Wire and Kraken settings units in one place."""
UNITS = {
    'center_freq_hz': 'Hz on wire; settings.json center_freq is MHz',
    'vfo_freq_hz': 'Hz on wire and settings.json', 'vfo_bw_hz': 'Hz',
    'squelch_db': 'dB', 'gain_x10': '0.1 dB', 'bearing_cdeg': '0.01 degree',
    'rssi_ddb': '0.1 dB', 'freq_hz': 'Hz', 'lat_e7': 'degrees × 1e7',
    'lon_e7': 'degrees × 1e7', 'rel_alt_dm': '0.1 m', 'heading_cdeg': '0.01 degree',
    'groundspeed_cms': 'cm/s', 'array_dim_mm': 'mm', 'telem_doa_hz_x10': '0.1 Hz',
    'telem_spec_hz_x10': '0.1 Hz',
}

def center_hz_to_settings_mhz(hz: int) -> float: return hz / 1_000_000.0
def center_settings_mhz_to_hz(mhz: float) -> int: return round(float(mhz) * 1_000_000)
