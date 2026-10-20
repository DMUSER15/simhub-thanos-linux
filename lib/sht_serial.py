"""sht_serial.py - USB serial devices (sysfs) and the COM ports of a Wine prefix. Read-only.

Test override: env SIMHUB_THANOS_SYS_ROOT is put in front of /sys, /dev and /etc (stand-ins only).

Wine's automatic COM ports (from Wine's dlls/mountmgr.sys, read 2026-10-19): at every prefix start
Wine reads HKLM\\Software\\Wine\\Ports (COMn = device; those numbers count as used and get links to
their device), then maps every /dev/ttyS0.., then /dev/ttyUSB0.., then /dev/ttyACM0.. (each list
stops at the first missing number) to COM1, COM2, ... skipping used numbers. It does not skip a
device that a registry entry already uses, so a registered device also gets an automatic port.
Removing an automatic link does not last.
"""
import glob, os, re

R = os.environ.get("SIMHUB_THANOS_SYS_ROOT", "")
AUTO_RE = re.compile(r"/dev/tty(S|USB|ACM)\d+$")
UDEV_DIRS = ("/etc/udev/rules.d", "/usr/lib/udev/rules.d", "/lib/udev/rules.d")


def _read(p):
    try:
        with open(p) as f:
            return f.read().strip()
    except OSError:
        return ""


def _unroot(p):
    return p[len(R):] if R and p.startswith(R) else p


def _links(kind):
    out = {}
    for link in sorted(glob.glob(R + "/dev/serial/%s/*" % kind)):
        out.setdefault(os.path.basename(os.path.realpath(link)), _unroot(link))
    return out


def usb_serial_devices():
    """[{tty, dev, byid, bypath, vid, pid, serial, product, manufacturer, key}] per ttyUSB/ttyACM."""
    byid, bypath = _links("by-id"), _links("by-path")
    out = []
    ttys = glob.glob(R + "/sys/class/tty/ttyUSB*") + glob.glob(R + "/sys/class/tty/ttyACM*")
    for t in sorted(ttys, key=lambda p: (re.sub(r"\d+$", "", os.path.basename(p)),
                                         int(re.search(r"(\d+)$", p).group(1)))):
        name = os.path.basename(t)
        d = os.path.realpath(os.path.join(t, "device"))
        info = {}
        while d and d != "/" and len(d) > len(R):
            if os.path.isfile(os.path.join(d, "idVendor")):
                info = {k: _read(os.path.join(d, k)) for k in ("idVendor", "idProduct", "serial", "product", "manufacturer")}
                break
            d = os.path.dirname(d)
        dev = {"tty": name, "dev": "/dev/" + name, "byid": byid.get(name, ""), "bypath": bypath.get(name, ""),
               "vid": info.get("idVendor", ""), "pid": info.get("idProduct", ""), "serial": info.get("serial", ""),
               "product": info.get("product", ""), "manufacturer": info.get("manufacturer", "")}
        dev["key"] = dev["serial"] or (("port:" + os.path.basename(dev["bypath"])) if dev["bypath"] else name)
        out.append(dev)
    return out


def stable(d):
    """Best name for a COM port: by-id when the device has a serial number (unique, follows the
    device to any USB port), else by-path (fixed USB port), else the plain tty."""
    if d["serial"] and d["byid"]:
        return d["byid"]
    return d["bypath"] or d["byid"] or d["dev"]


def matches(d, s):
    return bool(s) and s in (d["serial"], d["tty"], d["key"], d["dev"])


def com_links(dosdev):
    out = {}
    for p in glob.glob(os.path.join(dosdev, "com*")):
        n = os.path.basename(p)
        if re.fullmatch(r"com\d+", n, re.I) and os.path.islink(p):
            out[n.upper()] = os.readlink(p)
    return out


def reg_ports(system_reg):
    """{'COM69': '/dev/...'} from HKLM\\Software\\Wine\\Ports in system.reg."""
    out = {}
    try:
        lines = open(system_reg, errors="replace").read().splitlines()
    except OSError:
        return out
    inside = False
    for line in lines:
        if line.startswith("["):
            inside = line.lower().startswith("[software\\\\wine\\\\ports]")
            continue
        if inside:
            m = re.match(r'"(COM\d+)"="(.*)"\s*$', line, re.I)
            if m:
                out[m.group(1).upper()] = m.group(2).replace("\\\\", "\\")
    return out


def points_to(target, d):
    if not target:
        return False
    if target in (d["byid"], d["bypath"], d["dev"]):
        return True
    return os.path.basename(os.path.realpath(R + target)) == d["tty"]


def exists(target):
    return os.path.exists(R + target)


def wine_auto(com, links, regs):
    """A link Wine made by itself: no registry entry and a plain /dev/ttyS|USB|ACMn target."""
    return com not in regs and bool(AUTO_RE.match(links.get(com) or ""))


def comnum(k):
    return int(k[3:])


def coms_for(d, links, regs):
    """COM ports (registry or link) that reach this device: registry ones first, then links."""
    r = sorted([k for k, t in regs.items() if points_to(t, d)], key=comnum)
    l_ = sorted([k for k, t in links.items() if points_to(t, d) and k not in r], key=comnum)
    return r + l_


def predict_auto(regs):
    """[(COMn, /dev/x)] Wine's automatic ports at the next prefix start (Inferred from Wine's source)."""
    used = {comnum(k) for k in regs}
    out, n = [], 1
    for pat in ("ttyS", "ttyUSB", "ttyACM"):
        i = 0
        while os.path.exists(R + "/dev/%s%d" % (pat, i)):
            while n in used:
                n += 1
            out.append(("COM%d" % n, "/dev/%s%d" % (pat, i)))
            n += 1
            i += 1
    return out


def can_open(d):
    return os.access(R + d["dev"], os.R_OK | os.W_OK)


def udev_rule_files(d):
    """Rule files that mention this device's vendor and product id."""
    hits = []
    for base in UDEV_DIRS:
        for f in sorted(glob.glob(R + base + "/*.rules")):
            t = _read(f).lower()
            if d["vid"] and d["pid"] and d["vid"].lower() in t and d["pid"].lower() in t:
                hits.append(_unroot(f))
    return hits


def udev_rule_name(d):
    if (d["vid"], d["pid"]) == ("0403", "6001"):
        return "/etc/udev/rules.d/70-ftdi-ft232.rules"
    return "/etc/udev/rules.d/70-simhub-serial-%s-%s.rules" % (d["vid"] or "x", d["pid"] or "x")


def udev_cmd(d):
    rule = 'SUBSYSTEM=="tty", ATTRS{idVendor}=="%s", ATTRS{idProduct}=="%s", TAG+="uaccess"' % (d["vid"], d["pid"])
    return ("echo '%s' | sudo tee %s && sudo udevadm control --reload-rules && "
            "sudo udevadm trigger --subsystem-match=tty" % (rule, udev_rule_name(d)))


def label(d):
    name = d["serial"] or "(no serial)"
    return "%-7s %s:%s  %-18s %s" % (d["tty"], d["vid"] or "????", d["pid"] or "????", name[:18],
                                     stable(d) if stable(d) != d["dev"] else "(no /dev/serial link)")


def short(d):
    return d["serial"] or "%s %s:%s" % (d["tty"], d["vid"], d["pid"])
