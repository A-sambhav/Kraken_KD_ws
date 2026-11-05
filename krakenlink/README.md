# KrakenLink Phase 2, step 1

This directory contains the stdlib-only KLF v1 protocol package, command
validator, Kraken App CSV parser, and a file/HTTP simulator. It implements
the protocol and simulator portion of `SPEC.md`; it does not contain the
bridge, ground application, transports, or firmware.

## Run the tests

From this directory:

```sh
python -m pytest -q tests
```

## Run the simulator

```sh
python -m krakenlink.sim --directory ./sim-data --port 8081
```

The simulator creates `settings.json` and continuously rewrites
`DOA_value.html` (except during its default eight-second calibration pause).
It serves `/DOA_value.html` and `/settings.json`, and accepts full settings
objects at `POST /settings`. Options include `--calibration-gap SECONDS` and
`--crash-on-invalid`. The simulator's Python API is
`krakenlink.sim.__main__.KrakenSimulator`; `apply_settings()` is a convenient
test/control hook that accepts only a valid settings candidate.

## Protocol API

`krakenlink.proto.Frame`, `encode_frame`, and `decode_frame` implement KLF
framing and CRC-16/CCITT-FALSE. Message dataclasses and `decode_message()` /
`encode_message()` live in `krakenlink.proto.messages`. COBS functions omit
the UART `0x00` delimiter; the transport owns delimiter framing.

`validate_command(opcode, params, settings, ...)` returns either a `Nack`
with a `NackReason` and optional detail index, or a dict limited to the
settings keys approved by §5. Center frequency is converted to MHz for
`settings.json`; VFO frequencies and bandwidths remain Hz. Frequency units
are listed in `krakenlink.proto.UNITS`.
