"""Checks GitHub for a newer release and installs it if you say yes.

Nothing here runs without being asked. The check is a single unauthenticated GET to
the releases API, it happens on a background thread so a slow or blocked network never
holds up the window, and every failure is swallowed into "no update" rather than
thrown at someone who only wanted to use the app.

Installing depends on how Cadence got onto the machine:

  installer build  the new installer is downloaded and launched, and it handles the
                   replacement the same way the first install did
  portable exe     Windows will not let a running exe overwrite itself, so a small
                   batch file waits for this process to exit, swaps the file and
                   starts the new one
  source checkout  nothing is downloaded, because git already does this job
"""

import os
import re
import sys
import json
import tempfile
import threading
import subprocess
import urllib.error
import urllib.request

from .version import __version__, RELEASES_API, REPO

USER_AGENT = f"Cadence/{__version__} (+https://github.com/{REPO})"
TIMEOUT = 8


def parse_version(text):
    """Turn 'v1.2.3' into (1, 2, 3). Anything unparseable sorts lowest."""
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - len(nums[:3]))


def is_newer(candidate, current=__version__):
    return parse_version(candidate) > parse_version(current)


def install_kind():
    """How this copy was installed, which decides how it can be replaced."""
    if not getattr(sys, "frozen", False):
        return "source"
    exe = os.path.abspath(sys.executable)
    # The installer puts Cadence under Program Files or the per-user equivalent.
    for marker in (os.environ.get("ProgramFiles", ""),
                   os.environ.get("ProgramFiles(x86)", ""),
                   os.environ.get("LOCALAPPDATA", "")):
        if marker and exe.lower().startswith(os.path.join(marker, "Cadence").lower()):
            return "installed"
    return "portable"


def fetch_latest():
    """Ask GitHub for the newest release. Returns a dict or None."""
    req = urllib.request.Request(RELEASES_API, headers={
        "User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.load(r)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    tag = data.get("tag_name") or ""
    if not tag or data.get("draft"):
        return None
    assets = [{"name": a.get("name", ""), "url": a.get("browser_download_url", ""),
               "size": a.get("size", 0)} for a in data.get("assets", [])]
    return {"version": tag.lstrip("vV"),
            "tag": tag,
            "notes": (data.get("body") or "").strip(),
            "page": data.get("html_url", f"https://github.com/{REPO}/releases"),
            "assets": assets,
            "prerelease": bool(data.get("prerelease"))}


def pick_asset(assets, kind=None):
    """Choose the right download for this machine.

    Names are matched loosely because release assets get renamed over time; the only
    hard rule is that an installed copy takes an installer and a portable copy takes a
    bare exe."""
    kind = kind or install_kind()
    want_setup = kind == "installed"
    exes = [a for a in assets if a["name"].lower().endswith(".exe")]
    setups = [a for a in exes if "setup" in a["name"].lower()
              or "install" in a["name"].lower()]
    plain = [a for a in exes if a not in setups]
    order = (setups + plain) if want_setup else (plain + setups)
    return order[0] if order else None


def download(asset, on_progress=None, dest_dir=None):
    """Fetch an asset to a temp file, reporting progress as a 0..1 fraction."""
    dest_dir = dest_dir or tempfile.mkdtemp(prefix="cadence-update-")
    path = os.path.join(dest_dir, asset["name"])
    req = urllib.request.Request(asset["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as fh:
        total = int(r.headers.get("Content-Length") or asset.get("size") or 0)
        done = 0
        while True:
            chunk = r.read(64 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if on_progress and total:
                on_progress(min(1.0, done / total))
    if on_progress:
        on_progress(1.0)
    return path


SWAP_SCRIPT = """@echo off
rem Wait for Cadence to exit, swap the exe, start it again.
:wait
tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait
)
move /y "{new}" "{target}" >nul
start "" "{target}"
del "%~f0"
"""


def apply_update(downloaded, on_status=None):
    """Install what was downloaded. Returns True if the app should now quit."""
    kind = install_kind()
    say = on_status or (lambda _m: None)
    if kind == "source":
        say("Running from source - use git pull instead.")
        return False
    if downloaded.lower().endswith(".exe") and (
            "setup" in os.path.basename(downloaded).lower()
            or "install" in os.path.basename(downloaded).lower()):
        say("Starting the installer...")
        subprocess.Popen([downloaded], close_fds=True)
        return True
    target = os.path.abspath(sys.executable)
    bat = os.path.join(tempfile.mkdtemp(prefix="cadence-swap-"), "swap.bat")
    with open(bat, "w", encoding="ascii") as fh:
        fh.write(SWAP_SCRIPT.format(pid=os.getpid(), new=downloaded, target=target))
    say("Restarting to finish the update...")
    subprocess.Popen(["cmd", "/c", bat], close_fds=True,
                     creationflags=0x08000000)      # CREATE_NO_WINDOW
    return True


class UpdateCheck(threading.Thread):
    """Runs one check off the UI thread and hands the result back."""

    def __init__(self, on_result, allow_prerelease=False):
        super().__init__(daemon=True)
        self.on_result = on_result
        self.allow_prerelease = allow_prerelease
        self.result = None

    def run(self):
        latest = fetch_latest()
        if latest and latest["prerelease"] and not self.allow_prerelease:
            latest = None
        if latest and not is_newer(latest["version"]):
            latest = None
        self.result = latest
        try:
            self.on_result(latest)
        except Exception:
            pass
