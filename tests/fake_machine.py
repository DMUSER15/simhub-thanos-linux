#!/usr/bin/env python3
"""fake_machine.py - build a stand-in Linux machine for the tests (never touches the real one).

  python3 tests/fake_machine.py ROOT [--devices thanos-rig|thanos|none] [--prefix configured|fresh|none]
                                     [--udev] [--extra-prefix]

ROOT/home   is used as HOME          ROOT/sys-root  as SIMHUB_THANOS_SYS_ROOT (/sys, /dev, /etc)
Device sets:
  thanos-rig  ttyUSB0 FTDI 0403:6001 B001GRTL, ttyUSB1 FTDI 0403:6001 A50285BI,
              ttyUSB2 CH340 1a86:7523 (no serial)   (a rig with a THANOS, a fan controller and a CH340)
  thanos      ttyUSB0 FTDI B001GRTL only            none   no USB serial device
Prefix (linux-simracing-utils layout, stub wine that implements `wine reg add`):
  configured  COM69 in the registry + by-id link; Wine automatic com33-35 (com33 only with one device)
  fresh       SimHub installed, only Wine's automatic links    none  no SimHub at all
Always 32 /dev/ttyS ports (com1-32 links in a prefix), as on a typical desktop.
"""
import argparse, os, shutil, sys

STUB_WINE = r'''#!/usr/bin/env python3
# stand-in wine: logs every call; implements `wine reg add HKLM\Software\Wine\Ports /v N /t REG_SZ /d D /f`
import os, sys, time
pfx = os.environ.get("WINEPREFIX", "")
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "wine.log"), "a") as f:
    f.write(repr(sys.argv[1:]) + " WINEPREFIX=" + pfx + "\n")
a = sys.argv[1:]
if a[:2] == ["reg", "add"] and a[2].lower() == r"hklm\software\wine\ports":
    name, data = a[a.index("/v") + 1], a[a.index("/d") + 1]
    reg = os.path.join(pfx, "system.reg")
    lines = open(reg).read().splitlines() if os.path.exists(reg) else ["WINE REGISTRY Version 2", ";; All keys relative to \\\\Machine", ""]
    head = "[Software\\\\Wine\\\\Ports]"
    val = '"%s"="%s"' % (name, data.replace("\\", "\\\\"))
    out, i, done = [], 0, False
    while i < len(lines):
        l = lines[i]
        out.append(l)
        if l.startswith(head):
            i += 1
            while i < len(lines) and not lines[i].startswith("["):
                if not lines[i].startswith('"%s"=' % name):
                    if lines[i].strip() == "" and not done:
                        out.append(val)
                        done = True
                    out.append(lines[i])
                elif not done:
                    out.append(val)
                    done = True
                i += 1
            if not done:
                out.append(val)
                done = True
            continue
        i += 1
    if not done:
        out += ["", "%s %d" % (head, int(time.time())), "#time=1dc0000000000000", val]
    open(reg, "w").write("\n".join(out) + "\n")
    print("The operation completed successfully")
sys.exit(0)
'''

DEVICES = {
    "B001GRTL": dict(tty="ttyUSB0", vid="0403", pid="6001", serial="B001GRTL", product="FT232R USB UART",
                     manufacturer="FTDI", byid="usb-FTDI_FT232R_USB_UART_B001GRTL-if00-port0", port="2.3"),
    "A50285BI": dict(tty="ttyUSB1", vid="0403", pid="6001", serial="A50285BI", product="FT232R USB UART",
                     manufacturer="FTDI", byid="usb-FTDI_FT232R_USB_UART_A50285BI-if00-port0", port="2.2"),
    "CH340": dict(tty="ttyUSB2", vid="1a86", pid="7523", serial="", product="USB Serial", manufacturer="",
                  byid="usb-1a86_USB_Serial-if00-port0", port="1.4"),
}
SETS = {"thanos-rig": ["B001GRTL", "A50285BI", "CH340"], "thanos": ["B001GRTL"], "none": []}


def w(path, text, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    if mode:
        os.chmod(path, mode)


def make_device(sr, d):
    usb = os.path.join(sr, "sys", "devices", "pci0000:00", "0000:00:08.1", "0000:2a:00.1", "usb1", "1-" + d["port"])
    for k in ("idVendor", "idProduct", "serial", "product", "manufacturer"):
        v = {"idVendor": d["vid"], "idProduct": d["pid"]}.get(k, d.get(k, ""))
        if k == "serial" and not v:
            continue  # a CH340 has no serial attribute at all
        w(os.path.join(usb, k), v + "\n")
    intf = os.path.join(usb, "1-%s:1.0" % d["port"])
    port = os.path.join(intf, d["tty"])
    os.makedirs(os.path.join(port, "tty", d["tty"]), exist_ok=True)
    cls = os.path.join(sr, "sys", "class", "tty")
    os.makedirs(cls, exist_ok=True)
    os.symlink(os.path.join(port, "tty", d["tty"]), os.path.join(cls, d["tty"]))
    os.symlink(port, os.path.join(port, "tty", d["tty"], "device"))
    w(os.path.join(sr, "dev", d["tty"]), "")
    os.chmod(os.path.join(sr, "dev", d["tty"]), 0o660)
    for kind, name in (("by-id", d["byid"]), ("by-path", "pci-0000:2a:00.1-usb-0:%s:1.0-port0" % d["port"])):
        os.makedirs(os.path.join(sr, "dev", "serial", kind), exist_ok=True)
        os.symlink("../../" + d["tty"], os.path.join(sr, "dev", "serial", kind, name))


def make_prefix(pfx, simhub=True):
    if simhub:
        w(os.path.join(pfx, "drive_c", "Program Files (x86)", "SimHub", "SimHubWPF.exe"), "stand-in exe\n")
    os.makedirs(os.path.join(pfx, "dosdevices"), exist_ok=True)
    os.symlink("../drive_c", os.path.join(pfx, "dosdevices", "c:"))
    os.symlink("/", os.path.join(pfx, "dosdevices", "z:"))
    for i in range(32):
        os.symlink("/dev/ttyS%d" % i, os.path.join(pfx, "dosdevices", "com%d" % (i + 1)))
    w(os.path.join(pfx, "system.reg"), "WINE REGISTRY Version 2\n;; All keys relative to \\\\Machine\n\n"
      "#arch=win64\n\n[Software\\\\Wine] 1760000000\n#time=1dc0000000000000\n\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--devices", default="thanos-rig", choices=sorted(SETS))
    ap.add_argument("--prefix", default="configured", choices=("configured", "fresh", "none"))
    ap.add_argument("--udev", action="store_true", help="add /etc/udev/rules.d/70-ftdi-ft232.rules")
    ap.add_argument("--extra-prefix", action="store_true", help="a second SimHub copy in ~/.wine")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    if os.path.exists(root):
        shutil.rmtree(root)
    home, sr = os.path.join(root, "home"), os.path.join(root, "sys-root")
    os.makedirs(home)
    for i in range(32):
        w(os.path.join(sr, "dev", "ttyS%d" % i), "")
    os.makedirs(os.path.join(sr, "sys", "class", "tty"), exist_ok=True)
    devs = [DEVICES[k] for k in SETS[a.devices]]
    for d in devs:
        make_device(sr, d)
    if a.udev:
        w(os.path.join(sr, "etc", "udev", "rules.d", "70-ftdi-ft232.rules"),
          'SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", TAG+="uaccess"\n')
    lsu = os.path.join(home, "linux-simracing-utils")
    if a.prefix != "none":
        w(os.path.join(lsu, "install.sh"), "#!/bin/sh\necho stand-in\n", 0o755)
        bin_ = os.path.join(lsu, "var", "wine", "bin")
        w(os.path.join(bin_, "wine"), STUB_WINE, 0o755)
        w(os.path.join(bin_, "wineserver"), "#!/bin/sh\nexit 0\n", 0o755)
        pfx = os.path.join(lsu, "pfx")
        make_prefix(pfx)
        dd = os.path.join(pfx, "dosdevices")
        for n, d in enumerate(devs):  # Wine's automatic links: ttyUSB0.. after the 32 ttyS ports
            os.symlink("/dev/" + d["tty"], os.path.join(dd, "com%d" % (33 + n)))
        if a.prefix == "configured" and devs:
            byid = "/dev/serial/by-id/" + DEVICES["B001GRTL"]["byid"]
            os.symlink(byid, os.path.join(dd, "com69"))
            with open(os.path.join(pfx, "system.reg"), "a") as f:
                f.write('[Software\\\\Wine\\\\Ports] 1760000000\n#time=1dc0000000000000\n"COM69"="%s"\n\n' % byid)
    if a.extra_prefix:
        make_prefix(os.path.join(home, ".wine"))
    print("HOME=%s\nSIMHUB_THANOS_SYS_ROOT=%s" % (home, sr))


if __name__ == "__main__":
    sys.exit(main())
