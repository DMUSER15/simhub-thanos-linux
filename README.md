# simhub-thanos-linux

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-dmuser15-FFDD00?logo=buymeacoffee&logoColor=black)](https://www.buymeacoffee.com/dmuser15)

Connect a **THANOS AMC** motion controller to **SimHub running in Wine on Linux**. The same tool also gives **any USB serial device** (an Arduino, a fan controller, a CH340 or CDC-ACM board) a COM port in SimHub that stays put when USB devices change.

What it does, read-only first and nothing as root:

1. Installs SimHub with [linux-simracing-utils](https://github.com/srounce/linux-simracing-utils), guided.
2. Finds your USB serial devices and tells the THANOS (FTDI FT232R, `0403:6001`) apart from other controllers with the same chip.
3. Checks that you can open the device. If you can't, it prints the udev command for you to run with sudo.
4. Registers a fixed COM port in SimHub's Wine prefix: a `HKLM\Software\Wine\Ports` entry plus a `dosdevices` link to the stable `/dev/serial/by-id/` name.
5. Explains Wine's **automatic** COM ports. These are duplicates that come back at every prefix start, and the tool tells you which ones to keep disabled in SimHub.
6. For the THANOS, writes a controller file to import in SimHub, with your COM port filled in.

Tested so far on CachyOS with SimHub 9.13.2 (linux-simracing-utils prefix) and a THANOS AMC (AASD-15A drives). Other distributions should work the same way; reports are welcome.

> **Safety.** A motion platform can injure. Keep the E-stop within reach. Have the motion power (cabinet) **off** while you change COM ports or SimHub's controller settings, and while SimHub starts and connects. Nobody sits in the rig for the first test after any change.

## Requirements

- Linux with Python 3.8 or newer. The tool uses the standard library only.
- `git`, `wine`, `curl`, `unzip`: needed by linux-simracing-utils.
- SimHub in a Wine prefix. The default is `~/linux-simracing-utils/pfx`; other prefixes work with `--prefix`.

## Install

```fish
git clone https://github.com/DMUSER15/simhub-thanos-linux ~/simhub-thanos-linux
cd ~/simhub-thanos-linux
python3 tests/run_tests.py          # optional: tests on a stand-in machine, never touch yours
```

## Step by step

All commands are run from the repository folder. `plan` and `list` never change anything.

**1. SimHub** (skip if SimHub already runs from linux-simracing-utils):

```fish
python3 simhub_thanos.py simhub              # read-only: what is done, what is left
python3 simhub_thanos.py simhub --apply      # asks before each step
```

**2. See what is connected.** Plug in and power the controller, then:

```fish
python3 simhub_thanos.py list
```

**3. Plan the THANOS.** The tool picks the THANOS for you when only one FTDI device is connected, or when one is already registered in Wine:

```fish
python3 simhub_thanos.py plan
```

Several FTDI devices and none registered yet? Unplug the other controllers and run `list` again to see which serial number belongs to the THANOS. Then use `--device SERIAL`, or let `apply` show a menu.

**4. Apply.** Close SimHub and switch the cabinet OFF first.

```fish
python3 simhub_thanos.py apply
```

`apply` asks which device is the THANOS and which COM number to use (Enter = 69). If a port uses `/dev/ttyUSBn`, it also offers to switch it to the stable name. It prints the udev command if you can't open the device; run that one yourself, then unplug and replug the controller. Run `plan` again until every step shows `DONE` and the last line is `READY`.

**5. SimHub.** Import `~/simhub-thanos/THANOS_AMC_COM69.shmotioncontroller`, then set up the axes. [docs/THANOS.md](docs/THANOS.md) covers this, the start order and what to do when SimHub hangs.

**6. Wine's automatic COM ports.** In SimHub's **Arduino** settings, turn **off** "scan all COM ports" and enable only the ports you really use. Keep the automatic duplicate of the THANOS (COM33 on a typical desktop) disabled. Why: [docs/SERIAL-PORTS.md](docs/SERIAL-PORTS.md).

### Other USB serial devices (any controller)

The `serial` profile does steps 1–4 for any USB serial device: COM port only, no controller file.

```fish
python3 simhub_thanos.py plan  --profile serial --device A50285BI
python3 simhub_thanos.py apply --profile serial --device A50285BI
```

By default it keeps the COM number SimHub already uses for that device (its current automatic number), so SimHub's settings don't need to change. `--com N` picks another number. Devices without a serial number (many CH340 boards) are named by their USB port (`/dev/serial/by-path/`), so keep them in the same USB socket. Details: [docs/SERIAL-PORTS.md](docs/SERIAL-PORTS.md).

## Reference

```
python3 simhub_thanos.py simhub [--apply] | list | plan [options] | apply [options] | version
  --profile thanos|serial   --device ID (repeatable)   --all   --com N   --replace
  --template FILE (thanos)  --prefix PATH              --wine PATH
```

| Exit code | Meaning |
|---|---|
| 0 | ok / ready |
| 1 | usage |
| 2 | SimHub is running (apply) |
| 3 | nothing found, or no SimHub prefix |
| 4 | not ready (plan): a step is TODO or CONFLICT |
| 5 | choice needed, or cancelled |
| 6 | a step failed (apply) |

| What | Where |
|---|---|
| Saved choices (prefix, Wine, which device has which profile and COM port) | `~/.config/simhub-thanos/config.json` (env `SIMHUB_THANOS_CONFIG`) |
| Controller files | `~/simhub-thanos/` (env `SIMHUB_THANOS_OUT`) |
| Prefix / Wine override | env `SIMHUB_THANOS_PREFIX`, `SIMHUB_THANOS_WINE` |
| Test stand-ins for /sys, /dev, /etc and the process list | env `SIMHUB_THANOS_SYS_ROOT`, `SIMHUB_THANOS_PROC` (tests only) |

The tool never runs sudo. It never changes anything outside SimHub's prefix, its own config file and `~/simhub-thanos/`. In the prefix it changes only Wine's `Ports` registry key (through the prefix's own `wine reg add`) and `dosdevices/comNN` links.

## Support

This tool is free and stays free. If it saved you an evening with Wine and COM ports, you can [buy me a coffee](https://www.buymeacoffee.com/dmuser15). Bug reports and test results from other distributions and controllers help just as much.

## Licence

GPL-3.0 (see [LICENSE](LICENSE)). You may use, change, fork and share it, also commercially. Anyone who distributes it or a changed version must pass on the full source under the same licence.

Credits: the manual procedure was worked out with help from the linux-simracing-utils Discord.
