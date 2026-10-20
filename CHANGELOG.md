# Changelog

## 0.1.1 (2026-10-19)

- Tests no longer see the real process list (env `SIMHUB_THANOS_PROC`, stand-in only). With SimHub open on the test machine, every test `apply` was refused and the run crashed.
- Tests report a missing file as FAIL instead of stopping with a traceback.

## 0.1.0 (2026-10-19)

First version, split out of a larger private motion project as its own tool.

- `simhub_thanos.py simhub|list|plan|apply`. `plan` and `list` are read-only, `apply` asks with menus, and every choice is also available as an option for scripts.
- Profiles: `thanos` (FTDI devices, COM port plus controller file) and `serial` (any USB serial device, COM port only).
- Finds SimHub's prefix (linux-simracing-utils default, `~/.wine`, Steam, Bottles, `--prefix`) and its Wine.
- Recognises Wine's automatic COM ports: NOTE instead of WARNING, predicts where they will be at the next prefix start, and suggests a registered port for a device SimHub uses through an automatic one.
- Stable names: `/dev/serial/by-id/` for devices with a serial number, `/dev/serial/by-path/` for devices without one.
- Saved choices in `~/.config/simhub-thanos/config.json`.
- Minimal THANOS template (only the COM port); `--template` for your own export.
- Tests on stand-in machines (`tests/run_tests.py`).
- Licence GPL-3.0.
