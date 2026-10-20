# THANOS AMC controller with SimHub on Linux

How the THANOS AMC motion controller (AASD-15A servo drives) is made to connect to SimHub running in Wine (linux-simracing-utils). Worked out with help from the linux-simracing-utils Discord. `simhub_thanos.py` does steps 1–4 below and writes the file for step 5.

## Summary

The THANOS talks to SimHub over a USB serial chip: an FTDI FT232R, USB ID `0403:6001`. Under Wine that port has to be:

1. **openable by you:** a udev rule;
2. **known to Wine as a fixed COM port:** a registry value plus a `dosdevices` link;
3. **named in SimHub's controller setup:** an export with the right `"SerialPort"`, imported into SimHub.

SimHub may still show the COM port as disconnected, but motion works once you set up the axes or press Start Motion.

## With the tool

```fish
python3 simhub_thanos.py plan     # read-only
python3 simhub_thanos.py apply    # asks with menus; SimHub closed, cabinet OFF
```

`apply` asks:

1. **Which FTDI device is the THANOS.** The THANOS and some fan controllers use the same FT232R chip, so they look alike. A device already registered in Wine is pre-selected. If unsure, unplug the other controller, run `list`, and see which serial number is left.
2. **A COM number**, only for a device that has none registered yet. Enter accepts the next free one from 69.
3. **Whether to switch to the stable name.** If the COM port points at `/dev/ttyUSB0`, it offers the stable `/dev/serial/by-id/` name (Enter = yes). ttyUSB numbers change when devices re-enumerate.

Then, per device:

| Step | What |
|---|---|
| 1 access | checks you can open the port; if not, prints the udev command below for you to run (the tool never uses sudo) |
| 2 registry | `HKLM\Software\Wine\Ports`: `"COM69"="/dev/serial/by-id/usb-FTDI_…"` (the prefix's own `wine reg add`) |
| 3 link | `<prefix>/dosdevices/com69 → /dev/serial/by-id/usb-FTDI_…` |
| 4 file | `~/simhub-thanos/THANOS_AMC_COM69.shmotioncontroller`: the controller setup to import in SimHub |

Your choice is saved in `~/.config/simhub-thanos/config.json`, so `plan` and `apply` know the THANOS next time without asking.

### The import file

`templates/thanos-amc-aasd15a.shmotioncontroller` is a **minimal** SimHub THANOS export. It holds only the controller type and `"SerialPort"`, plus SimHub's review flags for "connection" and "mapping". Everything rig-specific has been removed: actuator order and roles, spike filters, park and unpark timings, and the output id.

- After importing it, **check every THANOS setting in SimHub** and set the actuator order for your rig. Fields missing from the file are expected to take SimHub's own defaults (Inferred, not yet confirmed on a real import).
- If you already have a working export, from Windows or an earlier SimHub, use that instead. The tool only changes its `"SerialPort"` and remembers the template for that device:
  ```fish
  python3 simhub_thanos.py apply --device B001GRTL --template ~/Downloads/my-thanos.shmotioncontroller
  ```

If SimHub already has the THANOS set up and working, you don't need the file. `plan` shows it as `NOT WRITTEN`, and that doesn't stop `READY`.

## Manual (what the tool does, step by step)

1. **Find the device.** `lsusb` shows `Future Technology Devices International, Ltd FT232 Serial (UART) IC`, ID `0403:6001`. `command ls -l /dev/serial/by-id/` shows its stable name.

2. **udev permissions.** Only needed if you can't open the port; being in the `uucp` group (Arch) or `dialout` group (Debian/Ubuntu) also works.
   ```fish
   echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/70-ftdi-ft232.rules && sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=tty
   ```
   Then unplug and replug the controller.

3. **Wine registry.** Open the prefix's registry editor:
   ```fish
   env WINEPREFIX=$HOME/linux-simracing-utils/pfx $HOME/linux-simracing-utils/var/wine/bin/wine regedit
   ```
   Under `HKEY_LOCAL_MACHINE\Software\Wine\Ports`, add a string value named `COM69` with the device as data. Prefer `/dev/serial/by-id/usb-FTDI_…`; `/dev/ttyUSB0` also works but can change.

4. **dosdevices link.**
   ```fish
   ln -sfn /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_YOURSERIAL-if00-port0 ~/linux-simracing-utils/pfx/dosdevices/com69
   ```

5. **SimHub controller setup.** At this point SimHub still shows the THANOS as disconnected.
   1. Export your current controller setup from SimHub's motion settings (or use a known-working export from Windows, as long as the syntax is right).
   2. In the exported file, find `"SerialPort":` and set it to your COM port: `"SerialPort": "COM69",`
   3. Save the file and reopen SimHub.
   4. Set up your platform again and import the modified file.
   5. The COM port may still show as disconnected. Set up your axes as you normally would: it connects and allows motion for setup and testing. It also connects when you press **Start Motion**.

## Start order every time

1. E-stop within reach. Cabinet **OFF**.
2. Start SimHub. It connects to the THANOS.
3. Cabinet **ON**. If SimHub shows "Actuator is unpowered", reset the connection.
4. Wait until SimHub shows the controller connected, not stuck on "Starting".

## If it hangs or won't enable

| Symptom | Cause | Fix |
|---|---|---|
| Hangs at the screen that defines the platform axis config | COM port conflict: another SimHub device, such as a **custom serial device**, uses the same COM port | disable that device (on the working rig it hung until the custom serial interface on the same port was disabled) |
| Motion stuck on "Starting", log "Enabling output took too long" | SimHub's Arduino scan probing every COM port, including the THANOS's automatic duplicate | Arduino settings: turn **off** "scan all COM ports", enable only the ports you use ([SERIAL-PORTS.md](SERIAL-PORTS.md)) |
| "Actuator is unpowered" | the cabinet was off when SimHub connected, or was switched off | reset the connection after the cabinet is on |
| Port missing after a replug | `/dev/ttyUSBn` changed | use the `/dev/serial/by-id/` name (the tool does) |
| Permission denied opening the port | no udev rule / not in `uucp` or `dialout` | step 2 |
