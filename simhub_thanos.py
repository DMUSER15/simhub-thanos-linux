#!/usr/bin/env python3
"""simhub_thanos.py - connect a THANOS AMC motion controller (or any USB serial device) to SimHub
running in Wine on Linux: a fixed COM port in SimHub's prefix, and for the THANOS a controller
file to import in SimHub. See README.md and docs/.

  python3 simhub_thanos.py simhub [--apply]      guided SimHub install (linux-simracing-utils)
  python3 simhub_thanos.py list                  read-only: USB serial devices and COM ports
  python3 simhub_thanos.py plan  [options]       read-only: state of the chosen device(s)
  python3 simhub_thanos.py apply [options]       set up the chosen device(s); SimHub closed

Profiles (--profile):
  thanos  (default) THANOS AMC: FTDI 0403 devices; COM port + THANOS controller file
  serial  any USB serial device (FTDI, CH340, CDC-ACM, ...): COM port only, no file; e.g. an
          Arduino or WindSim fan controller that should keep its COM port when USB devices change

Options:
  --device ID    serial number (e.g. B001GRTL), tty name (ttyUSB2) or port:... key; repeatable
  --all          every device of the profile
  --com N        COM number for a device that has no registered port yet
                 (thanos: default next free from 69; serial: default its current automatic number)
  --replace      switch a port that uses /dev/ttyUSBn to the stable name, or re-point a
                 conflicting port, without asking
  --template F   thanos: your own SimHub controller export to use instead of the minimal one
  --prefix P     SimHub's Wine prefix (default: linux-simracing-utils, else the only one found)
  --wine W       the Wine that runs that prefix

Which device(s) without --device: thanos = your saved choice, else the FTDI device(s) already
registered in Wine's Ports registry, else the only FTDI device; apply shows a menu in a terminal.
Per device: 1 access (prints a sudo udev command if needed; never runs sudo), 2 registry
HKLM\\Software\\Wine\\Ports "COMnn" = stable /dev/serial/... name (wine reg add), 3 link
<prefix>/dosdevices/comnn, 4 file (thanos) ~/simhub-thanos/THANOS_AMC_COMnn.shmotioncontroller.
Exit codes: 0 ok/ready, 1 usage, 2 SimHub running, 3 nothing found / no prefix, 4 not ready,
5 choice needed/cancelled, 6 a step failed.
"""
import argparse, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import sht_prefix as P  # noqa: E402
import sht_serial as S  # noqa: E402
import sht_ui as U  # noqa: E402

VERSION = "0.1.1"
PROFILES = {
    "thanos": {"title": "THANOS AMC controller", "vid": "0403", "first_com": 69,
               "template": os.path.join(HERE, "templates", "thanos-amc-aasd15a.shmotioncontroller"),
               "file": "THANOS_AMC_%s.shmotioncontroller",
               "menu": "Which FTDI device is the THANOS? (other FTDI controllers, e.g. fan controllers, use the same chip)"},
    "serial": {"title": "USB serial device", "vid": None, "first_com": 70, "template": None, "file": None,
               "menu": "Which USB serial device(s) should get a stable COM port?"},
}


class Ctx:
    def __init__(self, prefix, wine):
        self.prefix, self.wine = prefix, wine
        self.dosdev = os.path.join(prefix, "dosdevices")
        self.sysreg = os.path.join(prefix, "system.reg")
        self.wineserver = os.path.join(os.path.dirname(wine), "wineserver") if wine else None

    def links(self):
        return S.com_links(self.dosdev)

    def regs(self):
        return S.reg_ports(self.sysreg)


# ----------------------------------------------------------------------------- template / file
def load_template(path):
    """(data, problem)"""
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data.get("Output", {}).get("Settings"), dict):
            return None, "%s has no Output.Settings (not a SimHub controller export?)" % path
        return data, None
    except OSError:
        return None, "%s not found" % path
    except ValueError as e:
        return None, "%s is not valid JSON (%s)" % (path, e)


def file_path(profile, com):
    return os.path.join(P.OUT_DIR, PROFILES[profile]["file"] % com)


def file_text(template, com):
    data, problem = load_template(template)
    if problem:
        return None, problem
    data["Output"]["Settings"]["SerialPort"] = com
    return json.dumps(data, indent=2) + "\n", None


def file_state(profile, com, template):
    text, problem = file_text(template, com)
    if problem:
        return "BLOCKED " + problem
    p = file_path(profile, com)
    if not os.path.isfile(p):
        return "NOT WRITTEN"
    with open(p, encoding="utf-8-sig") as f:
        return "DONE" if f.read() == text else "DIFFERS"


def template_for(a, cfg, d):
    if a.template:
        return os.path.abspath(a.template)
    return cfg.get("devices", {}).get(d["key"], {}).get("template") or PROFILES["thanos"]["template"]


# ----------------------------------------------------------------------------- state
def state(ctx, d, com):
    links, regs = ctx.links(), ctx.regs()
    stable = S.stable(d)

    def one(target):
        if not target:
            return "TODO"
        if not S.points_to(target, d):
            return "CONFLICT " + target
        return "DONE" if target == stable else "DONE-TTY " + target
    st = {"access": S.can_open(d), "registry": one(regs.get(com)), "link": one(links.get(com)),
          "stable": stable, "others": [k for k in S.coms_for(d, links, regs) if k != com]}
    st["ready"] = st["access"] and all(st[k].startswith("DONE") for k in ("registry", "link"))
    st["exact"] = st["ready"] and st["registry"] == "DONE" and st["link"] == "DONE"
    return st


def dup_lines(k, links, regs, ctx):
    if S.wine_auto(k, links, regs):
        return ["  NOTE        %s is Wine's automatic link to %s (made again at every prefix start; removing it"
                % (k, links[k]),
                "              does not last). Harmless while SimHub never opens it: keep %s disabled in" % k,
                "              SimHub's Arduino settings and \"scan all COM ports\" off."]
    return ["  WARNING     %s also points at this device. SimHub opening it twice can hang the setup;" % k,
            "              disable %s in SimHub (Arduino settings) or remove it: rm %s"
            % (k, os.path.join(ctx.dosdev, k.lower()))]


def report(ctx, d, com, profile, template):
    st = state(ctx, d, com)
    print("%s  ->  %s   (%s)" % (S.short(d), com, PROFILES[profile]["title"]))
    if st["access"]:
        print("  1 access    DONE (you can open %s)" % d["dev"])
    else:
        rules = S.udev_rule_files(d)
        print("  1 access    TODO: run this yourself, then unplug and replug the device:\n      " + S.udev_cmd(d) +
              ("\n      (rule files that mention %s:%s already: %s; being in the uucp group also works)"
               % (d["vid"], d["pid"], ", ".join(rules)) if rules else ""))
    for n, what in ((2, "registry"), (3, "link")):
        s = st[what]
        if s.startswith("DONE-TTY"):
            s = "DONE via %s (changes when devices re-enumerate; apply offers the stable %s)" % (s[9:], st["stable"])
        elif s.startswith("CONFLICT"):
            s = "CONFLICT: %s points at %s, another device (choose another number with --com)" % (com, s[9:])
        print("  %d %-9s %s" % (n, what, s))
    if PROFILES[profile]["file"]:
        fs = file_state(profile, com, template)
        hint = {"NOT WRITTEN": "  (apply writes it; only needed to import the controller in SimHub)",
                "DIFFERS": "  (apply rewrites it from %s; the old one is kept as .bak)" % template}.get(fs, "")
        print("  4 file      %s  %s%s" % (fs, file_path(profile, com), hint))
    links, regs = ctx.links(), ctx.regs()
    for k in st["others"]:
        print("\n".join(dup_lines(k, links, regs, ctx)))
    if st["ready"]:
        print("  READY       %s reaches %s%s" % (com, S.short(d), "" if st["exact"] else
                                                 " (via a ttyUSB name that can change: apply --replace)"))
    else:
        print("  NOT READY   steps above marked TODO/CONFLICT")
    return st


# ----------------------------------------------------------------------------- list
def show_ports(ctx, devs):
    print("USB serial devices:")
    for d in devs:
        print("  " + S.label(d))
    if not devs:
        print("  none")
    if not ctx:
        print()
        return
    links, regs = ctx.links(), ctx.regs()
    usb = sorted({k for k, t in list(links.items()) + list(regs.items()) if not re.match(r"/dev/ttyS\d+$", t or "")},
                 key=S.comnum)
    print("COM ports on USB devices in %s:" % ctx.prefix)
    for k in usb:
        reg = regs.get(k) or ("- (Wine automatic)" if S.wine_auto(k, links, regs) else "-")
        print("  %-6s link -> %-62s registry %s" % (k, links.get(k, "-"), reg))
    if not usb:
        print("  none")
    print()


def owner(target, devs):
    for d in devs:
        if S.points_to(target, d):
            return d
    return None


def cmd_list(ctx, devs):
    show_ports(ctx, devs)
    if not ctx:
        return 3
    links, regs = ctx.links(), ctx.regs()
    notes = 0
    for k, t in sorted(regs.items(), key=lambda kv: S.comnum(kv[0])):
        if not re.match(r"/dev/ttyS\d+$", t) and not S.exists(t):
            print("WARNING  %s is registered for %s, which is not connected now." % (k, t))
            notes += 1
    for k, t in sorted(links.items(), key=lambda kv: S.comnum(kv[0])):
        d = owner(t, devs)
        if not d or not S.wine_auto(k, links, regs):
            continue
        reg = [c for c, rt in regs.items() if S.points_to(rt, d)]
        if reg:
            print("NOTE     %s is Wine's automatic duplicate of %s (%s): keep %s disabled in SimHub."
                  % (k, ", ".join(sorted(reg, key=S.comnum)), S.short(d), k))
        else:
            print("NOTE     %s -> %s (%s) is a Wine automatic port. If SimHub uses %s (Arduino, fan controller,"
                  % (k, t, S.short(d), k))
            print("         custom serial device), it can point at another device after a USB change. Give it a")
            print("         stable port: python3 simhub_thanos.py apply --profile serial --device %s" % d["key"])
        notes += 1
    pred = [(c, t) for c, t in S.predict_auto(regs) if not t.startswith("/dev/ttyS")]
    if pred:
        print("\nWine's automatic ports at the next prefix start (Inferred from Wine's source):")
        for c, t in pred:
            d = owner(t, devs)
            print("  %-6s -> %s%s" % (c, t, "  (%s)" % S.short(d) if d else ""))
    print("\nIn SimHub's Arduino settings keep \"scan all COM ports\" off and enable only the ports you use.")
    return 0


# ----------------------------------------------------------------------------- choose
def candidates(profile, devs):
    vid = PROFILES[profile]["vid"]
    return [d for d in devs if not vid or d["vid"] == vid]


def choose(a, ctx, devs, cfg):
    """([(dev, COMnn)], None) or (None, problem)."""
    prof = PROFILES[a.profile]
    cands = candidates(a.profile, devs)
    links, regs = ctx.links(), ctx.regs()
    saved = cfg.get("devices", {})
    if not cands:
        return None, ("no FTDI (0403) USB serial device found. Plug in and power the controller"
                      if a.profile == "thanos" else "no USB serial device found")
    interactive_apply = a.cmd == "apply" and U.interactive()
    if a.device:
        chosen = []
        for s in a.device:
            m = [d for d in cands if S.matches(d, s)]
            if not m:
                return None, "no %s with id %s (found: %s)" % (
                    "FTDI device" if a.profile == "thanos" else "USB serial device", s, ", ".join(d["key"] for d in cands))
            chosen.append(m[0])
    elif a.all:
        chosen = cands
    else:
        mine = [d for d in cands if saved.get(d["key"], {}).get("profile") == a.profile]
        other = {k for k, v in saved.items() if v.get("profile") != a.profile}
        reg = [d for d in cands if d["key"] not in other and any(S.points_to(t, d) for t in regs.values())]
        if mine:
            guess, how = mine, "saved choice"
        elif a.profile == "thanos" and reg:
            guess, how = reg, "registered in Wine"
        elif a.profile == "thanos" and len(cands) == 1:
            guess, how = cands, "only FTDI device"
        else:
            guess, how = [], ""
        if interactive_apply and (len(cands) > 1 or not guess):
            rows = []
            for d in cands:
                have = S.coms_for(d, links, regs)
                rows.append(S.label(d) + ("   (now %s)" % ", ".join(have) if have else ""))
            picks = U.choose_many(prof["menu"], rows, [cands.index(d) for d in guess])
            if not picks:
                return None, "nothing chosen"
            chosen = [cands[i] for i in picks]
        elif guess and (a.cmd == "plan" or how == "saved choice" or len(cands) == 1):
            print("Device(s): %s (%s; --device to choose)\n" % (", ".join(S.short(d) for d in guess), how))
            chosen = guess
        else:
            return None, "CHOICE NEEDED: %d device(s) found: apply shows a menu, or use --device ID (or --all)" % len(cands)
    used = {S.comnum(k) for k in list(links) + list(regs)}
    nxt = a.com or prof["first_com"]
    out = []
    for d in chosen:
        regc = [k for k, t in regs.items() if S.points_to(t, d)]
        mycom = saved.get(d["key"], {}).get("com")
        if regc:
            out.append((d, mycom if mycom in regc else sorted(regc, key=S.comnum)[0]))
            continue
        own = [k for k in S.coms_for(d, links, regs) if S.wine_auto(k, links, regs)]
        if a.com is None and a.profile == "serial" and own:
            dflt = S.comnum(own[0])  # keep the number SimHub may already use for it
        else:
            while nxt in used:
                nxt += 1
            dflt = nxt
        com = dflt
        ownnums = {S.comnum(k) for k in own}
        while True:
            if interactive_apply:
                com = U.ask_int("COM number for %s" % S.short(d), dflt, 1, 255)
                if com is None:
                    return None, "cancelled"
            if com not in used or com in ownnums:
                break
            if not interactive_apply:
                return None, "COM%d is already used (choose another with --com)" % com
            print("  COM%d is already used by another device; choose another" % com)
        used.add(com)
        out.append((d, "COM%d" % com))
        if com >= nxt:
            nxt = com + 1
    return out, None


# ----------------------------------------------------------------------------- apply
def wine_reg_add(ctx, com, path):
    env = dict(os.environ, WINEPREFIX=ctx.prefix, WINEDEBUG="-all")
    r = subprocess.run([ctx.wine, "reg", "add", r"HKLM\Software\Wine\Ports", "/v", com, "/t", "REG_SZ",
                        "/d", path, "/f"], env=env, capture_output=True, text=True, timeout=120)
    if ctx.wineserver and os.path.exists(ctx.wineserver):
        subprocess.run([ctx.wineserver, "-w"], env=env, timeout=60, capture_output=True)  # flush system.reg
    return r.returncode == 0, (r.stdout + r.stderr).strip()[-200:]


def cmd_apply(a, ctx, plan, devs, cfg):
    if P.scan(P.SIMHUB_EXE):
        print("REFUSED: SimHub is running. Close it first (the registry is written by Wine in its prefix).")
        return 2
    if not ctx.wine or not os.path.exists(ctx.wine):
        print("REFUSED: Wine for %s not found (%s); use --wine PATH" % (ctx.prefix, ctx.wine))
        return 3
    fails = 0
    for d, com in plan:
        st = state(ctx, d, com)
        path = st["stable"]
        template = template_for(a, cfg, d) if a.profile == "thanos" else None
        print("%s -> %s (%s)" % (S.short(d), com, path))
        if not st["access"]:
            print("  1 access    NOT YET: run this yourself, then unplug and replug the device:\n      " + S.udev_cmd(d))
        else:
            print("  1 access    DONE")
        for n, what in ((2, "registry"), (3, "link")):
            s = st[what]
            if s == "DONE":
                print("  %d %-9s DONE" % (n, what))
                continue
            if s.startswith("CONFLICT"):
                if not (a.replace or U.confirm("  %s %s points at %s, not this device. Re-point it?" % (com, what, s[9:]))):
                    print("  %d %-9s left as it is (choose another COM number with --com)" % (n, what))
                    fails += 1
                    continue
            elif s.startswith("DONE-TTY"):
                if not (a.replace or U.confirm("  %s %s uses %s. Switch it to the stable %s?" % (com, what, s[9:], path),
                                               default=True)):
                    print("  %d %-9s kept (%s)" % (n, what, s[9:]))
                    continue
            if what == "registry":
                ok, out = wine_reg_add(ctx, com, path)
                ok = ok and ctx.regs().get(com) == path
                print("  2 registry  %s" % ("written" if ok else "FAILED: " + out))
            else:
                link = os.path.join(ctx.dosdev, com.lower())
                old = os.readlink(link) if os.path.islink(link) else None
                os.makedirs(ctx.dosdev, exist_ok=True)
                tmp = link + ".sht_tmp"
                if os.path.lexists(tmp):
                    os.remove(tmp)
                os.symlink(path, tmp)
                os.replace(tmp, link)
                ok = os.readlink(link) == path
                print("  3 link      %s%s" % ("written" if ok else "FAILED", " (was -> %s)" % old if old else ""))
            fails += 0 if ok else 1
        if template:
            fs = file_state(a.profile, com, template)
            p = file_path(a.profile, com)
            if fs == "DONE":
                print("  4 file      DONE  %s" % p)
            elif fs.startswith("BLOCKED"):
                print("  4 file      %s" % fs)
                fails += 1
            else:
                os.makedirs(P.OUT_DIR, exist_ok=True)
                if os.path.exists(p):
                    shutil.copyfile(p, p + ".bak")
                with open(p, "w") as f:
                    f.write(file_text(template, com)[0])
                print("  4 file      written %s" % p)
        links, regs = ctx.links(), ctx.regs()
        for k in state(ctx, d, com)["others"]:
            print("\n".join(dup_lines(k, links, regs, ctx)))
        entry = {"profile": a.profile, "com": com}
        if template and a.template:
            entry["template"] = template
        elif template and cfg.get("devices", {}).get(d["key"], {}).get("template"):
            entry["template"] = cfg["devices"][d["key"]]["template"]
        cfg.setdefault("devices", {})[d["key"]] = entry
    cfg["prefix"], cfg["wine"] = ctx.prefix, ctx.wine
    P.save_config(cfg)
    print()
    pred = [(c, t) for c, t in S.predict_auto(ctx.regs()) if not t.startswith("/dev/ttyS")]
    if pred:
        print("Wine's automatic ports at the next prefix start (Inferred; keep them disabled in SimHub):")
        for c, t in pred:
            o = owner(t, devs)
            print("  %-6s -> %s%s" % (c, t, "  (%s)" % S.short(o) if o else ""))
        print()
    if a.profile == "thanos":
        print("Next: start SimHub, add the THANOS platform, import the .shmotioncontroller file above, check every")
        print("setting (the minimal file only sets the COM port), then set up the axes. The port may still show")
        print("disconnected until you do (docs/THANOS.md). Arduino \"scan all COM ports\" off.")
    else:
        print("Next: in SimHub use the COM port above for this device (Arduino settings: enable only the ports")
        print("you use; \"scan all COM ports\" off). docs/SERIAL-PORTS.md")
    print("Saved choices: %s" % P.CONFIG)
    return 6 if fails else 0


# ----------------------------------------------------------------------------- main
def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("cmd", nargs="?")
    ap.add_argument("--profile", default="thanos")
    ap.add_argument("--com", type=int)
    ap.add_argument("--device", action="append")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--template")
    ap.add_argument("--prefix")
    ap.add_argument("--wine")
    ap.add_argument("--apply", action="store_true")
    a, extra = ap.parse_known_args(argv[1:])
    if a.cmd in ("version", "--version"):
        print("simhub-thanos-linux %s" % VERSION)
        return 0
    bad = (a.cmd not in ("simhub", "list", "plan", "apply") or extra or a.profile not in PROFILES
           or (a.com is not None and not 1 <= a.com <= 255) or (a.apply and a.cmd != "simhub")
           or (a.template and a.profile != "thanos"))
    if bad:
        print(__doc__)
        return 1
    if a.cmd == "simhub":
        if a.apply and not sys.stdin.isatty():
            print("REFUSED: --apply asks questions and needs a terminal.")
            return 2
        import sht_guide
        return sht_guide.run(a.apply)
    cfg = P.load_config()
    devs = S.usb_serial_devices()
    prefix, how, found, problem = P.choose_prefix(a.prefix, menu=a.cmd == "apply")
    if not prefix:
        show_ports(None, devs)
        print("BLOCKED: " + problem)
        for x in found:
            print("  found: %s  [%s]" % (x["prefix"], x["source"]))
        return 3
    wine, whow = P.choose_wine(prefix, a.wine)
    ctx = Ctx(prefix, wine)
    others = [x["prefix"] for x in found if os.path.realpath(x["prefix"]) != os.path.realpath(prefix)]
    print("SimHub prefix: %s (%s)%s" % (prefix, how, "; other SimHub copies: %s" % ", ".join(others) if others else ""))
    print("Wine:          %s (%s)\n" % (wine or "-", whow))
    if a.cmd == "list":
        return cmd_list(ctx, devs)
    show_ports(ctx, devs)
    plan, problem = choose(a, ctx, devs, cfg)
    if problem:
        print(problem)
        if a.cmd == "plan":
            links, regs = ctx.links(), ctx.regs()
            for d in candidates(a.profile, devs):
                have = S.coms_for(d, links, regs)
                reg = any(S.points_to(t, d) for t in regs.values())
                print("  %-22s %s%s" % (d["key"], "now " + ", ".join(have) if have else "no COM port yet",
                                        "  (registered in Wine)" if reg else ""))
        return 5 if devs else 3
    if a.template:
        _, tp = load_template(a.template)
        if tp:
            print("BLOCKED: " + tp)
            return 3
    if a.cmd == "plan":
        ready = True
        for d, com in plan:
            st = report(ctx, d, com, a.profile, template_for(a, cfg, d) if a.profile == "thanos" else None)
            ready = ready and st["ready"]
        return 0 if ready else 4
    return cmd_apply(a, ctx, plan, devs, cfg)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
