# North Star Radio-Jack Receiver

This is a receive-only software scaffold for a future VHF/UHF radio connected
to a PC line-in or microphone jack. It is separate from the North Star laser
program.

It does **not** currently decode real ISS APRS, NOAA APT, or North Star traffic.
Those modes return an explicit `not_implemented` result. Only the generated
synthetic tone fixtures have a working decoder.

## No-hardware test

```powershell
python -m radio_receiver.cli generate-fixtures
python -m radio_receiver.cli decode radio_receiver/fixtures/synthetic_1000hz.wav --mode SYNTHETIC_TONE
python -m radio_receiver.cli decode radio_receiver/fixtures/synthetic_1000hz.wav --mode AFSK1200
```

The same flow through the selectable input interface:

```powershell
python -m radio_receiver.cli receive --source wav --input radio_receiver/fixtures/synthetic_1000hz.wav --mode SYNTHETIC_TONE
```

The first decode succeeds because it targets the synthetic fixture format. The
AFSK command exits with a clear unimplemented result and never fakes success.

## Future sound-card capture

```powershell
python -m pip install -r requirements-radio.txt
python -m radio_receiver.cli list-devices
python -m radio_receiver.cli record capture.wav --seconds 15 --device 0
python -m radio_receiver.cli receive --source hardware --device 0 --seconds 15 --recording-output capture.wav --mode AFSK1200
```

`--source hardware` loads the optional `sounddevice` adapter. `--source wav`
uses no capture hardware and is suitable for fixtures or previously recorded
audio. A hardware capture can succeed while decoding still returns
`not_implemented`; capture and protocol decoding are separate capabilities.

Future hardware requires a legally operated/tuned VHF or UHF receiver with
demodulated audio output, a suitable cable or isolation interface, an antenna,
and correct input-level configuration. S-band, X-band, Ka-band, and optical
links cannot be received through an audio jack.
