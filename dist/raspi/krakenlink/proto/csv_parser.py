"""Parser for the 377-column Kraken App DOA_value.html record."""
from dataclasses import dataclass

FIELD_COUNT = 377

class CSVLineError(ValueError): pass

@dataclass(frozen=True)
class KrakenDOA:
    timestamp_ms:int; bearing_deg:float; confidence:float; rssi_db:float; freq_hz:int
    array_value:str; latency_ms:int; station:str; latitude:float; longitude:float
    heading:float; heading2:float; gps:str; radii:tuple; spectrum:tuple

def parse_doa_line(line: str) -> KrakenDOA:
    fields = line.strip().split(',')
    if len(fields) != FIELD_COUNT: raise CSVLineError(f'expected 377 fields, got {len(fields)}')
    try:
        bearing = float(fields[1]) % 360.0
        # Field 6 is the Kraken array label/value (the simulator writes UCA/ULA).
        return KrakenDOA(int(float(fields[0])), bearing, float(fields[2]), float(fields[3]), int(float(fields[4])), fields[5], int(float(fields[6])), fields[7], float(fields[8]), float(fields[9]), float(fields[10]), float(fields[11]), fields[12], tuple(fields[13:17]), tuple(float(x) for x in fields[17:377]))
    except (ValueError, OverflowError) as e: raise CSVLineError('invalid numeric field') from e

def spectrum_bins(theta_values, peak=None):
    """Rotate theta-domain degrees to compass and max-pool into 72 5-degree bins."""
    if len(theta_values) != 360: raise ValueError('spectrum requires 360 theta samples')
    compass = [0.0] * 360
    for i, val in enumerate(theta_values): compass[(360-i) % 360] = float(val)
    peak_value = max(compass) if peak is None else float(peak)
    if peak_value <= 0: return 0, bytes(72)
    bins=[]
    for k in range(72):
        # Five compass degrees centered on 5k, wrapping across north.
        v=max(compass[(k*5+offset) % 360] for offset in (-2,-1,0,1,2))
        bins.append(max(0,min(255,round(255*v/peak_value))))
    return max(0,min(65535,round(peak_value*10))), bytes(bins)

def parse_doa_with_spectrum(line: str):
    sample=parse_doa_line(line); peak,bins=spectrum_bins(sample.spectrum)
    return sample,peak,bins

def read_line_with_retry(path, delay_s=0.020):
    """Read a single file snapshot, retrying a partial write once."""
    import time
    for attempt in range(2):
        try:
            with open(path,'r',encoding='utf-8') as f: line=f.readline()
            return parse_doa_line(line)
        except (OSError, CSVLineError):
            if attempt: raise
            time.sleep(delay_s)
