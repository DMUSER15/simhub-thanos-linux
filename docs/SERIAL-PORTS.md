# USB serial devices and COM ports in SimHub under Wine

## Two kinds of COM port

SimHub sees serial ports as `COM1`, `COM2` and so on. In a Wine prefix each one is a link in `<prefix>/dosdevices/comNN` to a Linux device. They come from two places.

**Registered ports (yours).** These are entries in `HKLM\Software\Wine\Ports`, such as `"COM69"="/dev/serial/by-id/usb-FTDI_…"`. They point at whatever name you give, so a stable `/dev/serial/…` name keeps them on the right device. The tool writes these.

**Wine's automatic ports.** At **every prefix start** Wine creates a COM port for each serial device it finds, by itself. This comes from Wine's `dlls/mountmgr.sys`, read 2026-10-19:

1. First it reads the `Ports` registry. Those COM numbers count as used.
2. Then it maps `/dev/ttyS0`, `ttyS1`, …, then `/dev/ttyUSB0`, …, then `/dev/ttyACM0`, …. Each list stops at the first missing number. The devices get the free COM numbers in order from COM1.
3. It skips registered COM *numbers*, but not a *device* a registry entry already uses. So a registered device also gets an automatic duplicate.

A typical desktop has 32 `ttyS` ports, so they take COM1–32. The first USB serial device becomes **COM33**, the next COM34, and so on.

What follows from that (inferred from Wine's source; the first point was also seen on a real machine):

- **Deleting an automatic link doesn't last.** It comes back at the next prefix start.
- **An automatic port follows the enumeration order, not the device.** COM34 is "the second ttyUSB device". If a device is unplugged, switched off at boot or moved to another USB socket, COM34 can become a different device. In the worst case it becomes your motion controller.
- **Registering a COM number removes it from the automatic list.** The automatic ports after it move up. `list` and `apply` print where they will be at the next prefix start.

## What to do in SimHub

- **Arduino settings:** turn **off** "scan all COM ports" and enable only the ports you really use. A scan that opens the motion controller's port, even its automatic duplicate, can stop the controller from enabling.
- **Keep automatic duplicates of registered devices disabled.** `plan` prints a `NOTE` for each one.
- **If SimHub uses an automatic port for a device** (a fan controller, an Arduino, a custom serial device), give that device a registered port:

  ```fish
  python3 simhub_thanos.py plan  --profile serial --device A50285BI
  python3 simhub_thanos.py apply --profile serial --device A50285BI     # SimHub closed
  ```

  By default this keeps the number SimHub already uses (for example COM34), now registered and linked to the device's stable name, so SimHub's setting stays the same. To use a separate number, add `--com 70`. In that case, change the port in SimHub to match.

  Because it is a connection change: motion power OFF, then start SimHub and check that **every** controller connects (the motion controller and the device you changed) before the normal start.

## Stable names

| Device | Name the tool uses | Notes |
|---|---|---|
| Has a USB serial number (FTDI, most CDC-ACM boards) | `/dev/serial/by-id/usb-…` | unique; follows the device to any USB socket |
| No serial number (many CH340 boards) | `/dev/serial/by-path/pci-…-usb-…-port0` | tied to the USB socket: keep it plugged into the same one |
| Neither link | `/dev/ttyUSBn` | can change; the tool says so |

`--device` accepts the serial number (`A50285BI`), the tty name (`ttyUSB2`) or the `port:…` id that `list` shows.

## Access

You need read and write access to the device. Either:

- add a udev rule (the tool prints the command; you run it with sudo, then replug), or
- join the `uucp` group (Arch) or the `dialout` group (Debian/Ubuntu), then log out and in.
