#!/usr/bin/env python3
"""run_tests.py - tests of simhub_thanos.py on stand-in machines (tests/fake_machine.py).
Never touches the real machine: HOME, the prefix and /sys,/dev,/etc are all inside a temp folder.

  python3 tests/run_tests.py            all tests; prints PASS/FAIL per test, exit 0 when all pass
  python3 tests/run_tests.py -v         also show the tool's output for failed tests
"""
import hashlib, json, os, shutil, subprocess, sys, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(REPO, "simhub_thanos.py")
FAKE = os.path.join(REPO, "tests", "fake_machine.py")
BYID0 = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_B001GRTL-if00-port0"
BYID1 = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A50285BI-if00-port0"
VERBOSE = "-v" in sys.argv
RESULTS = []


class Machine:
    def __init__(self, base, name, *opts):
        self.root = os.path.join(base, name)
        subprocess.run([sys.executable, FAKE, self.root] + list(opts), check=True, capture_output=True)
        self.home = os.path.join(self.root, "home")
        self.sr = os.path.join(self.root, "sys-root")
        self.pfx = os.path.join(self.home, "linux-simracing-utils", "pfx")

    def env(self, **extra):
        e = {k: v for k, v in os.environ.items() if not k.startswith("SIMHUB_THANOS_")}
        self.proc = os.path.join(self.root, "proc")
        os.makedirs(self.proc, exist_ok=True)
        e.update(HOME=self.home, SIMHUB_THANOS_SYS_ROOT=self.sr, SIMHUB_THANOS_PROC=self.proc,
                 XDG_CONFIG_HOME=os.path.join(self.home, ".config"))
        e.update(extra)
        return e

    def run(self, *args, **extra):
        r = subprocess.run([sys.executable, TOOL] + list(args), env=self.env(**extra), capture_output=True,
                           text=True, stdin=subprocess.DEVNULL, timeout=120)
        return r.returncode, r.stdout + r.stderr

    def tree(self):
        """sha256 of every file and link target under the machine (to prove read-only commands)."""
        h = {}
        for d, dirs, files in os.walk(self.root):
            for n in dirs + files:
                p = os.path.join(d, n)
                if os.path.islink(p):
                    h[p] = "->" + os.readlink(p)
                elif os.path.isfile(p):
                    h[p] = hashlib.sha256(open(p, "rb").read()).hexdigest()
        return h

    def reg(self):
        return open(os.path.join(self.pfx, "system.reg")).read()

    def link(self, com):
        p = os.path.join(self.pfx, "dosdevices", com.lower())
        return os.readlink(p) if os.path.islink(p) else None

    def config(self):
        p = os.path.join(self.home, ".config", "simhub-thanos", "config.json")
        return json.load(open(p)) if os.path.exists(p) else None


def check(name, ok, out=""):
    RESULTS.append((name, bool(ok)))
    print("%s  %s" % ("PASS" if ok else "FAIL", name))
    if not ok and VERBOSE:
        print("    " + out.replace("\n", "\n    "))


def load_json(p):
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return {}


def has(out, *parts):
    return all(p in out for p in parts)


def main():
    base = tempfile.mkdtemp(prefix="sht-test-")
    try:
        tests(base)
        access_test()
    finally:
        shutil.rmtree(base, ignore_errors=True)
    bad = [n for n, ok in RESULTS if not ok]
    print("\n%d passed, %d failed" % (len(RESULTS) - len(bad), len(bad)))
    return 1 if bad else 0


def tests(base):
    # ---------------------------------------------------------------- the configured rig, read-only
    m = Machine(base, "rig", "--udev", "--extra-prefix")
    before = m.tree()
    code, out = m.run("list")
    check("list: exit 0", code == 0, out)
    check("list: COM33 = automatic duplicate of COM69", has(out, "COM33 is Wine's automatic duplicate of COM69 (B001GRTL)"), out)
    check("list: COM34 fan controller gets the stable-port hint",
          has(out, "COM34 -> /dev/ttyUSB1 (A50285BI) is a Wine automatic port", "--profile serial --device A50285BI"), out)
    check("list: predicted automatic ports COM33-35", has(out, "COM33  -> /dev/ttyUSB0", "COM34  -> /dev/ttyUSB1",
                                                          "COM35  -> /dev/ttyUSB2"), out)
    check("list: other SimHub copy named", has(out, "other SimHub copies: " + os.path.join(m.home, ".wine")), out)
    code, out = m.run("plan")
    check("plan: exit 0 (ready)", code == 0, out)
    check("plan: picks the registered THANOS", has(out, "Device(s): B001GRTL (registered in Wine"), out)
    check("plan: steps 1-3 DONE", has(out, "1 access    DONE", "2 registry  DONE", "3 link      DONE"), out)
    check("plan: file NOT WRITTEN (optional)", has(out, "4 file      NOT WRITTEN"), out)
    check("plan: COM33 NOTE, no WARNING", has(out, "NOTE        COM33 is Wine's automatic link") and "WARNING" not in out, out)
    check("plan: READY COM69", has(out, "READY       COM69 reaches B001GRTL"), out)
    code, out = m.run("plan", "--profile", "serial")
    check("plan serial without --device: choice needed (5)", code == 5 and has(out, "CHOICE NEEDED"), out)
    code, out = m.run("plan", "--profile", "serial", "--device", "A50285BI")
    check("plan serial A50285BI: keeps COM34, registry TODO, not ready (4)",
          code == 4 and has(out, "A50285BI  ->  COM34", "2 registry  TODO", "3 link      DONE via /dev/ttyUSB1"), out)
    code, out = m.run("plan", "--profile", "serial", "--device", "ttyUSB2")
    check("plan serial CH340 by tty name: by-path stable name offered",
          code == 4 and has(out, "COM35", "apply offers the stable /dev/serial/by-path/"), out)
    code, out = m.run("plan", "--device", "NOPE")
    check("plan unknown device: 5", code == 5 and has(out, "no FTDI device with id NOPE"), out)
    check("read-only commands changed nothing", m.tree() == before)
    for args in (["bogus"], ["plan", "--profile", "x"], ["plan", "--com", "0"], ["plan", "--apply"],
                 ["plan", "--profile", "serial", "--template", "x"], ["plan", "extra"], []):
        code, out = m.run(*args)
        check("usage error %s: exit 1" % (args,), code == 1, out)

    # ---------------------------------------------------------------- apply on the rig (THANOS)
    code, out = m.run("apply")
    check("apply without terminal, 2 FTDI, nothing saved: choice needed (5)", code == 5 and has(out, "CHOICE NEEDED"), out)
    code, out = m.run("apply", "--device", "B001GRTL")
    check("apply THANOS: exit 0", code == 0, out)
    check("apply THANOS: steps DONE, file written", has(out, "2 registry  DONE", "3 link      DONE", "4 file      written"), out)
    check("apply THANOS: no wine reg call needed", not os.path.exists(os.path.join(m.home, "linux-simracing-utils", "var", "wine", "bin", "wine.log")), out)
    f = os.path.join(m.home, "simhub-thanos", "THANOS_AMC_COM69.shmotioncontroller")
    data = load_json(f)
    st = data.get("Output", {}).get("Settings", {})
    check("file: SerialPort COM69, nothing else in Settings", st == {"SerialPort": "COM69"}, json.dumps(data))
    check("file: THANOS output type", data.get("Output", {}).get("TypeName") == "ThanosAMCControllerOutput")
    cfg = m.config() or {}
    check("config saved: B001GRTL thanos COM69, prefix",
          cfg.get("devices", {}).get("B001GRTL") == {"profile": "thanos", "com": "COM69"} and cfg.get("prefix") == m.pfx,
          json.dumps(cfg))
    code, out = m.run("apply")
    check("apply again (saved choice, no terminal): exit 0, all DONE",
          code == 0 and has(out, "saved choice", "4 file      DONE") and "written" not in out, out)
    code, out = m.run("plan")
    check("plan after apply: file DONE, READY", code == 0 and has(out, "4 file      DONE", "READY       COM69"), out)

    # ---------------------------------------------------------------- serial profile: the fan controller
    code, out = m.run("apply", "--profile", "serial", "--device", "A50285BI")
    check("apply serial A50285BI: exit 0", code == 0, out)
    check("apply serial: registry COM34 = by-id", '"COM34"="%s"' % BYID1 in m.reg(), m.reg())
    check("apply serial: link com34 -> by-id", m.link("COM34") == BYID1, str(m.link("COM34")))
    check("apply serial: COM69 untouched", '"COM69"="%s"' % BYID0 in m.reg() and m.link("COM69") == BYID0)
    check("apply serial: predicted automatic ports move (COM35/36)",
          has(out, "COM33  -> /dev/ttyUSB0", "COM35  -> /dev/ttyUSB1", "COM36  -> /dev/ttyUSB2"), out)
    check("apply serial: no file written", not os.path.exists(os.path.join(m.home, "simhub-thanos", "THANOS_AMC_COM34.shmotioncontroller")))
    code, out = m.run("plan", "--profile", "serial")
    check("plan serial (saved choice): READY COM34", code == 0 and has(out, "READY       COM34 reaches A50285BI"), out)
    code, out = m.run("plan")
    check("plan thanos still picks only B001GRTL", code == 0 and has(out, "Device(s): B001GRTL (saved choice") and "A50285BI  ->" not in out, out)
    code, out = m.run("list")
    check("list: COM34 no longer automatic", "COM34 -> /dev/ttyUSB1 (A50285BI) is a Wine automatic port" not in out
          and has(out, "COM34  link -> " + BYID1), out)

    # ---------------------------------------------------------------- your own export as template
    own = os.path.join(base, "my-export.shmotioncontroller")
    json.dump({"Output": {"Settings": {"SerialPort": "COM3", "ParkDurationMS": 4000}, "TypeName": "ThanosAMCControllerOutput"}},
              open(own, "w"))
    code, out = m.run("apply", "--device", "B001GRTL", "--template", own)
    data = load_json(f)
    check("--template: file rewritten from own export, .bak kept",
          code == 0 and data.get("Output", {}).get("Settings") == {"SerialPort": "COM69", "ParkDurationMS": 4000}
          and os.path.exists(f + ".bak"), out)
    code, out = m.run("plan")
    check("plan uses the saved template: file DONE", code == 0 and has(out, "4 file      DONE"), out)
    bad = os.path.join(base, "bad.json")
    open(bad, "w").write("{nope")
    code, out = m.run("plan", "--template", bad)
    check("bad template: BLOCKED (3)", code == 3 and has(out, "not valid JSON"), out)

    # ---------------------------------------------------------------- SimHub running
    m.env()  # creates the stand-in process list
    fake = os.path.join(m.proc, "4242")
    os.makedirs(fake)
    with open(os.path.join(fake, "cmdline"), "wb") as fh:
        fh.write(b"C:\\Program Files (x86)\\SimHub\\SimHubWPF.exe\0")
    try:
        code, out = m.run("apply", "--device", "B001GRTL")
        check("apply while SimHub runs: refused (2)", code == 2 and has(out, "REFUSED: SimHub is running"), out)
    finally:
        shutil.rmtree(fake)
    code, out = m.run("plan")
    check("real SimHub on this machine does not affect the tests", code == 0, out)

    # ---------------------------------------------------------------- fresh machine, no SimHub
    f0 = Machine(base, "fresh0", "--prefix", "none")
    code, out = f0.run("plan")
    check("fresh, no prefix: BLOCKED (3), devices still listed",
          code == 3 and has(out, "BLOCKED: no SimHub prefix found", "B001GRTL", "A50285BI"), out)
    code, out = f0.run("simhub")
    check("simhub guide read-only runs (0 or 5)", code in (0, 5) and "SimHub with linux-simracing-utils" in out, out)

    # ---------------------------------------------------------------- fresh SimHub prefix, nothing registered
    f1 = Machine(base, "fresh1", "--prefix", "fresh")
    before = f1.tree()
    code, out = f1.run("plan")
    check("fresh prefix, 2 FTDI, nothing registered: choice needed (5)",
          code == 5 and has(out, "CHOICE NEEDED", "B001GRTL", "now COM33"), out)
    code, out = f1.run("plan", "--device", "B001GRTL")
    check("fresh plan B001GRTL: COM69 TODO, NOT READY (4), COM33 NOTE",
          code == 4 and has(out, "B001GRTL  ->  COM69", "2 registry  TODO", "3 link      TODO", "NOT READY",
                            "NOTE        COM33"), out)
    check("fresh plan changed nothing", f1.tree() == before)
    code, out = f1.run("apply", "--device", "B001GRTL")
    check("fresh apply: registry + link written, exit 0",
          code == 0 and has(out, "2 registry  written", "3 link      written", "4 file      written")
          and '"COM69"="%s"' % BYID0 in f1.reg() and f1.link("COM69") == BYID0, out)
    wl = open(os.path.join(f1.home, "linux-simracing-utils", "var", "wine", "bin", "wine.log")).read()
    check("fresh apply: wine reg add used with the prefix", "reg" in wl and "WINEPREFIX=" + f1.pfx in wl, wl)
    code, out = f1.run("plan")
    check("fresh plan after apply: READY", code == 0 and has(out, "READY       COM69"), out)

    # ---------------------------------------------------------------- one THANOS only, no --device needed
    one = Machine(base, "one", "--devices", "thanos", "--prefix", "fresh")
    code, out = one.run("apply")
    check("single FTDI device: apply without --device works", code == 0 and has(out, "only FTDI device", "COM69"), out)

    # ---------------------------------------------------------------- no devices
    nd = Machine(base, "nodev", "--devices", "none")
    code, out = nd.run("plan")
    check("no USB serial devices: exit 3", code == 3 and has(out, "no FTDI (0403) USB serial device found"), out)

    # ---------------------------------------------------------------- several prefixes, no linux-simracing-utils
    mp = Machine(base, "multi", "--prefix", "none", "--extra-prefix")
    os.makedirs(os.path.join(mp.home, "Games"))
    shutil.copytree(os.path.join(mp.home, ".wine"), os.path.join(mp.home, "Games", "simhub"), symlinks=True)
    code, out = mp.run("plan")
    check("2 prefixes, none chosen: BLOCKED (3) with list", code == 3 and has(out, "2 SimHub prefixes found"), out)
    code, out = mp.run("plan", "--prefix", os.path.join(mp.home, ".wine"), "--wine", "/bin/true", "--device", "B001GRTL")
    check("--prefix picks one", code == 4 and has(out, "SimHub prefix: %s (--prefix)" % os.path.join(mp.home, ".wine")), out)

    # ---------------------------------------------------------------- interactive menu (Enter accepts the default)
    if shutil.which("script"):
        mi = Machine(base, "menu", "--udev")
        cmd = "%s %s apply" % (sys.executable, TOOL)
        r = subprocess.run(["script", "-qec", cmd, "/dev/null"], input="\n", env=mi.env(), capture_output=True,
                           text=True, timeout=60)
        out = r.stdout
        check("menu: THANOS pre-selected, Enter accepts, exit 0",
              r.returncode == 0 and has(out, "Which FTDI device is the THANOS?", "* 1) ttyUSB0", "4 file      written"), out)
    else:
        print("SKIP  menu test (no `script`)")

    # ---------------------------------------------------------------- names from other projects
    words = ("star citizen", "starcitizen", "d-box", "dbox", "livemotion", "sc_haptics", "sc-motion", "lug-helper",
             "haptisync", "dmuser", "scm_", "sc_thanos")
    hits = []
    for d, dirs, files in os.walk(REPO):
        dirs[:] = [x for x in dirs if x not in (".git", "__pycache__")]
        for n in files:
            if n == "LICENSE":
                continue
            t = open(os.path.join(d, n), errors="replace").read().lower()
            hits += ["%s: %s" % (n, w) for w in words if w in t and not (n == "run_tests.py")]
    check("no names from other projects in the repository", not hits, "\n".join(hits))


def access_test():
    """Step 1 TODO when you can't open the device. Needs a non-root user: as root, runs the tool as
    'nobody' on a copy in a world-readable temp folder; as a normal user, removes the permission."""
    tmp = tempfile.mkdtemp(prefix="sht-acc-", dir="/tmp")
    try:
        os.chmod(tmp, 0o755)
        repo = os.path.join(tmp, "repo")
        shutil.copytree(REPO, repo, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        m = Machine(tmp, "acc", "--prefix", "fresh")
        if os.geteuid() == 0:
            if not shutil.which("setpriv"):
                print("SKIP  access test (root without setpriv)")
                return
            for d, dirs, files in os.walk(tmp):
                for n in dirs + files:
                    p = os.path.join(d, n)
                    if not os.path.islink(p):
                        os.chmod(p, 0o755 if os.path.isdir(p) or os.access(p, os.X_OK) else 0o644)
            os.chmod(os.path.join(m.sr, "dev", "ttyUSB0"), 0o600)
            pre = ["setpriv", "--reuid=65534", "--regid=65534", "--clear-groups"]
        else:
            os.chmod(os.path.join(m.sr, "dev", "ttyUSB0"), 0o000)
            pre = []
        r = subprocess.run(pre + [sys.executable, os.path.join(repo, "simhub_thanos.py"), "plan", "--device", "B001GRTL"],
                           env=m.env(), capture_output=True, text=True, timeout=60)
        out = r.stdout + r.stderr
        check("no access: step 1 TODO with the udev command, NOT READY (4)",
              r.returncode == 4 and has(out, "1 access    TODO", "sudo tee /etc/udev/rules.d/70-ftdi-ft232.rules"), out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
