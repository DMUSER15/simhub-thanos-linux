"""sht_guide.py - guided SimHub install with linux-simracing-utils (`simhub_thanos.py simhub`).

Steps:
  1 tools     wine, curl, unzip, git (prints the install line)
  2 download  git clone https://github.com/srounce/linux-simracing-utils ~/linux-simracing-utils
  3 install   bash install.sh in that folder (it asks its own questions; answer yes for SimHub)
  4 check     SimHub in ~/linux-simracing-utils/pfx; other SimHub copies are listed
Without --apply read-only. With --apply it asks before each step that changes something ([y/N]).
Nothing runs as root; commands that need sudo are printed for you to run.
"""
import os, shutil, subprocess

import sht_prefix as P


class Guide:
    def __init__(self, apply):
        self.apply = apply
        self.left = 0

    def step(self, n, name, state, detail):
        print("  %-2s %-10s %-8s %s" % (n, name, state, detail))
        if state in ("TODO", "BLOCKED"):
            self.left += 1

    def ask(self, question):
        try:
            a = input("     %s [y/N] " % question).strip().lower()
        except EOFError:
            a = ""
        if a not in ("y", "yes"):
            print("     stopped; nothing more was changed.")
            raise SystemExit(5)
        return True


def run(apply):
    g = Guide(apply)
    try:
        _run(g)
    except SystemExit as e:
        return e.code
    return 5 if g.left and not apply else 0


def _run(g):
    print("SimHub with linux-simracing-utils%s" % ("" if g.apply else "  [read-only]"))
    miss = [t for t in ("wine", "curl", "unzip", "git") if not shutil.which(t)]
    g.step(1, "tools", "BLOCKED" if miss else "DONE",
           ("missing %s. Arch/CachyOS: sudo pacman -S --needed wine curl unzip git "
            "(other distributions: the same packages with their package manager)" % ", ".join(miss))
           if miss else "wine, curl, unzip, git")
    if miss:
        return
    if os.path.isfile(os.path.join(P.LSU, "install.sh")):
        g.step(2, "download", "DONE", P.LSU)
    else:
        g.step(2, "download", "TODO", "git clone %s %s" % (P.LSU_URL, P.LSU))
        if os.path.exists(P.LSU):
            print("     %s exists but has no install.sh; move it away first." % P.LSU)
            return
        if g.apply and g.ask("Download linux-simracing-utils with git now?"):
            if subprocess.run(["git", "clone", P.LSU_URL, P.LSU]).returncode:
                return
    exe = P.simhub_exe(P.LSU_PREFIX)
    if exe and os.path.exists(P.LSU_WINE):
        g.step(3, "install", "DONE", "SimHub installed")
    else:
        g.step(3, "install", "TODO", "cd %s; bash install.sh   (answer yes for SimHub)" % P.LSU)
        if g.apply and os.path.isfile(os.path.join(P.LSU, "install.sh")) and \
                g.ask("Run linux-simracing-utils' install.sh now? (it asks its own questions)"):
            subprocess.run(["bash", "install.sh"], cwd=P.LSU)
            exe = P.simhub_exe(P.LSU_PREFIX)
    others = [x["prefix"] for x in P.find_prefixes() if os.path.realpath(x["prefix"]) != os.path.realpath(P.LSU_PREFIX)]
    ok = bool(exe) and os.path.exists(P.LSU_WINE)
    g.step(4, "check", "DONE" if ok else "BLOCKED",
           (exe if ok else "SimHub not found in %s" % P.LSU_PREFIX) +
           ("; other SimHub copies (use --prefix to pick one): %s" % ", ".join(others) if others else ""))
    if ok:
        print("\nNext: python3 simhub_thanos.py plan")
