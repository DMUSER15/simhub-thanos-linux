"""sht_prefix.py - find SimHub's Wine prefix and its Wine, running processes, saved settings.
Read-only except save_config().

Which prefix is used (first that applies):
  1 --prefix PATH                 2 env SIMHUB_THANOS_PREFIX
  3 saved in the config file      4 linux-simracing-utils default (~/linux-simracing-utils/pfx)
  5 the only SimHub prefix found  6 a menu (apply, in a terminal) when several are found
Which Wine: --wine, env SIMHUB_THANOS_WINE, saved for that prefix, linux-simracing-utils' own Wine
for its prefix, else `wine` from PATH.
"""
import glob, json, os, shutil

HOME = os.path.expanduser("~")
USER = os.path.basename(HOME)
LSU = os.path.join(HOME, "linux-simracing-utils")
LSU_URL = "https://github.com/srounce/linux-simracing-utils"
LSU_PREFIX = os.path.join(LSU, "pfx")
LSU_WINE = os.path.join(LSU, "var", "wine", "bin", "wine")
CONFIG = os.environ.get("SIMHUB_THANOS_CONFIG") or os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "simhub-thanos", "config.json")
OUT_DIR = os.environ.get("SIMHUB_THANOS_OUT") or os.path.join(HOME, "simhub-thanos")
SIMHUB_EXE = "simhubwpf.exe"
SIMHUB_REL = (("Program Files (x86)", "SimHub", "SimHubWPF.exe"), ("Program Files", "SimHub", "SimHubWPF.exe"))


def load_config():
    try:
        with open(CONFIG) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    tmp = CONFIG + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, CONFIG)


def simhub_exe(prefix):
    for rel in SIMHUB_REL:
        exe = os.path.join(prefix, "drive_c", *rel)
        if os.path.isfile(exe):
            return exe
    return None


def _roots():
    roots = [(LSU_PREFIX, "linux-simracing-utils"), (os.path.join(HOME, ".wine"), "~/.wine")]
    roots += [(p, "~/Games") for p in sorted(glob.glob(os.path.join(HOME, "Games", "*")))]
    steams = (os.path.join(HOME, ".local", "share", "Steam"), os.path.join(HOME, ".steam", "steam"),
              os.path.join(HOME, ".var", "app", "com.valvesoftware.Steam", ".local", "share", "Steam"))
    for steam in steams:
        roots += [(p, "Steam") for p in sorted(glob.glob(os.path.join(steam, "steamapps", "compatdata", "*", "pfx")))]
    for base in sorted(glob.glob("/run/media/%s/*" % USER)) + sorted(glob.glob("/mnt/*")):
        for pat in (("steamapps", "compatdata", "*", "pfx"), ("*", "steamapps", "compatdata", "*", "pfx")):
            roots += [(p, "Steam library") for p in sorted(glob.glob(os.path.join(base, *pat)))]
    for b in (os.path.join(HOME, ".local", "share", "bottles", "bottles"),
              os.path.join(HOME, ".var", "app", "com.usebottles.bottles", "data", "bottles", "bottles")):
        roots += [(p, "Bottles") for p in sorted(glob.glob(os.path.join(b, "*")))]
    return roots


def find_prefixes(extra=()):
    """[{"prefix", "exe", "source"}] for every Wine/Proton prefix with SimHub, de-duplicated."""
    seen, out = set(), []
    for p, src in list(extra) + _roots():
        exe = simhub_exe(p)
        if not exe:
            continue
        rp = os.path.realpath(p)
        if rp in seen:
            continue
        seen.add(rp)
        out.append({"prefix": os.path.abspath(p), "exe": exe, "source": src})
    return out


def choose_prefix(option=None, menu=False):
    """(prefix or None, how, all_found, problem)."""
    import sht_ui as U
    found = find_prefixes()
    for value, how in ((option, "--prefix"), (os.environ.get("SIMHUB_THANOS_PREFIX"), "env SIMHUB_THANOS_PREFIX"),
                       (load_config().get("prefix"), "saved in %s" % CONFIG)):
        if value:
            if simhub_exe(value):
                return os.path.abspath(value), how, found, None
            return None, how, found, "%s (%s) has no SimHub (drive_c/Program Files (x86)/SimHub/SimHubWPF.exe)" % (value, how)
    if simhub_exe(LSU_PREFIX):
        return LSU_PREFIX, "linux-simracing-utils default", found, None
    if len(found) == 1:
        return found[0]["prefix"], "only SimHub prefix found (%s)" % found[0]["source"], found, None
    if not found:
        return None, "", found, "no SimHub prefix found. Install SimHub first: python3 simhub_thanos.py simhub"
    if menu and U.interactive():
        i = U.choose_one("Several SimHub prefixes found. Which one does SimHub run from?",
                         ["%s  [%s]" % (x["prefix"], x["source"]) for x in found], 0)
        if i is None:
            return None, "", found, "no prefix chosen"
        return found[i]["prefix"], "chosen in the menu", found, None
    return None, "", found, "%d SimHub prefixes found: apply shows a menu, or use --prefix PATH" % len(found)


def choose_wine(prefix, option=None):
    """(path or None, how)."""
    cfg = load_config()
    for value, how in ((option, "--wine"), (os.environ.get("SIMHUB_THANOS_WINE"), "env SIMHUB_THANOS_WINE")):
        if value:
            return value, how
    if cfg.get("wine") and cfg.get("prefix") and os.path.realpath(cfg["prefix"]) == os.path.realpath(prefix):
        return cfg["wine"], "saved"
    if os.path.realpath(prefix) == os.path.realpath(LSU_PREFIX) and os.path.exists(LSU_WINE):
        return LSU_WINE, "linux-simracing-utils"
    w = shutil.which("wine")
    return (w, "wine from PATH") if w else (None, "no Wine found (use --wine PATH)")


def _base(arg):
    return arg.replace("\\", "/").rsplit("/", 1)[-1].lower()


def _program(argv):
    first = _base(argv[0])
    if first.startswith("python"):
        for a in argv[1:]:
            if not a.startswith("-"):
                return _base(a)
    return first


PROC = os.environ.get("SIMHUB_THANOS_PROC") or "/proc"  # test override: a stand-in process list


def scan(*needles):
    """[(pid, cmdline)] of processes whose program is one of needles (lower case)."""
    me = os.getpid()
    hits = []
    try:
        pids = os.listdir(PROC)
    except OSError:
        return hits
    for d in pids:
        if not d.isdigit() or int(d) == me:
            continue
        try:
            with open(os.path.join(PROC, d, "cmdline"), "rb") as f:
                raw = f.read()
        except OSError:
            continue
        argv = [a.decode("utf-8", "replace") for a in raw.split(b"\0") if a]
        if argv and _program(argv) in needles:
            hits.append((int(d), " ".join(argv)))
    return hits
