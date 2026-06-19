# North Star Laser-Link Program

This is intentionally separate from `radio_receiver/`. An audio jack can carry
demodulated VHF/UHF receiver audio; it cannot receive an optical carrier.

The program currently provides:

- an optical channel registry;
- optical windows derived from real predicted orbital passes;
- configurable pointing-acquisition time;
- explicit cloud-blocked pass removal; and
- separate socket sender/receiver commands for software integration testing.

It does **not** drive or claim compatibility with a real laser, telescope,
tracking mount, beacon, photodetector, modem, or safety interlock.

Inspect optical windows:

```powershell
python -m laser_link.cli profile --blocked-pass 1
```

Test the software terminal on localhost:

```powershell
# Terminal 1
python -m laser_link.cli receive

# Terminal 2
python -m laser_link.cli send laser_payload.bin --generate-bytes 1048576
```

Real optical work would require eye-safe and aviation-safe operation, legal and
site approval, precision acquisition/tracking/pointing, optical modulation and
coding hardware, and a weather-aware ground terminal.
