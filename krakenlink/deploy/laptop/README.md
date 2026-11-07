# KrakenSDR laptop raw-data viewer

On Ubuntu 22.04 or newer, connect the KrakenSDR to its own 5 V supply and plug
its USB cable into the laptop. From any directory, run
`deploy/laptop/kraken_view.sh`. The script installs `librtlsdr0` and `rtl-sdr`
if needed, checks the detected receiver count, then opens the viewer at
`http://127.0.0.1:8090`. Use `--fake --fake-dead 3 --no-browser` to inspect the
interface without hardware.

Green **DATA OK** means samples are arriving at the selected rate; amber
**SLOW** means they are arriving below 90% of that rate; red **NO DATA** means
there has been no successful read for a second. The charts show per-channel
power and spectrum.

If a DVB driver has claimed the receivers, the launcher offers to unload it
and blacklist it. If device access is denied, install `rtl-sdr` udev rules and
unplug/replug the KrakenSDR. If fewer than five devices appear, check the
KrakenSDR power supply and USB cable.
