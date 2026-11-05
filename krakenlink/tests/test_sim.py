import json
import time

from krakenlink.sim.__main__ import DEFAULT_SETTINGS, KrakenSimulator


def _wait_for(predicate, timeout=3.0):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate(): return True
        time.sleep(0.02)
    return False


def test_direct_settings_write_triggers_calibration_pause_and_resume(tmp_path):
    sim=KrakenSimulator(tmp_path,calibration_gap=1.0,poll_interval=0.1)
    sim.start()
    try:
        assert _wait_for(lambda: sim.doa_path.exists())
        initial=sim.doa_path.read_text()
        initial_fields=initial.splitlines()[0].split(',')
        assert len(initial_fields)==377
        assert initial_fields[5]=='UCA' and initial_fields[12]=='GPS'
        assert initial_fields[13:17]==['R']*4

        with sim.lock:
            settings=sim._read_settings()
            settings.update(center_freq=433.1,active_vfos=2,vfo_freq_1=433_100_000,ext_upd_flag=True)
            sim.settings_path.write_text(json.dumps(settings),encoding='utf-8')

        assert _wait_for(lambda: sim._read_settings().get('ext_upd_flag') is False)
        paused=sim.doa_path.read_text()
        time.sleep(0.35)
        assert sim.doa_path.read_text()==paused
        assert _wait_for(lambda: sim.doa_path.read_text()!=paused,timeout=1.5)
        # Both active VFOs are represented after the pause, with their own frequencies.
        lines=sim.doa_path.read_text().splitlines()
        assert len(lines)==2
        assert [line.split(',')[4] for line in lines]==['433000000','433100000']
    finally:
        sim.stop()


def test_simulator_validates_named_doa_methods_and_root_music_geometry():
    settings=dict(DEFAULT_SETTINGS)
    assert KrakenSimulator.is_valid(settings)
    for method in ('Bartlett','Capon','MEM','TNA','MUSIC','ROOT-MUSIC'):
        candidate=dict(settings,doa_method=method,ant_arrangement='ULA')
        assert KrakenSimulator.is_valid(candidate)
    assert not KrakenSimulator.is_valid(dict(settings,doa_method='unknown'))
    assert not KrakenSimulator.is_valid(dict(settings,doa_method='ROOT-MUSIC',ant_arrangement='UCA'))
