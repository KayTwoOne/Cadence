#!/usr/bin/env python3
"""Builds Cadence for whichever machine you run it on.

    python packaging/build.py              exe (or binary) only
    python packaging/build.py --installer  and then wrap it for the platform
    python packaging/build.py --clean      throw away build leftovers first

Windows gets a PyInstaller exe and, with --installer, an Inno Setup installer.
Linux gets a binary plus a .desktop file, a tarball, and a .deb when dpkg-deb is
around.

Cross-building is not attempted. A PyInstaller binary is tied to the OS and CPU it
was produced on, so an ARM64 build has to happen on an ARM64 machine; the GitHub
workflow in .github/workflows does that on hosted runners.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from cadence.version import __version__, APP_NAME          # noqa: E402

DIST = os.path.join(ROOT, "dist")
BUILD = os.path.join(ROOT, "build")
ENTRY = os.path.join(ROOT, "Cadence.py")
ICON = os.path.join(ROOT, "cadence.ico")


def arch_tag():
    m = platform.machine().lower()
    return {"amd64": "x64", "x86_64": "x64", "arm64": "arm64",
            "aarch64": "arm64", "i386": "x86", "x86": "x86"}.get(m, m)


def run(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=True, **kw)


def clean():
    for d in (BUILD, os.path.join(ROOT, "__pycache__")):
        shutil.rmtree(d, ignore_errors=True)
    for spec in ("Cadence.spec",):
        p = os.path.join(ROOT, spec)
        if os.path.exists(p):
            os.remove(p)
    print("cleaned build leftovers")


def build_binary():
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile",
           "--name", APP_NAME, "--distpath", DIST, "--workpath", BUILD,
           "--specpath", BUILD]
    if sys.platform == "win32":
        cmd += ["--noconsole", "--icon", ICON]
    else:
        cmd += ["--windowed"]
    for mod in ("PIL", "numpy", "unittest", "pydoc", "pdb", "xml"):
        cmd += ["--exclude-module", mod]
    cmd.append(ENTRY)
    run(cmd)
    out = os.path.join(DIST, APP_NAME + (".exe" if sys.platform == "win32" else ""))
    print(f"built {out}  ({os.path.getsize(out) // 1024 // 1024} MB)")
    return out


# ---------------------------------------------------------------- windows
def find_iscc():
    """Locate the Inno Setup compiler, newest version first."""
    if shutil.which("iscc"):
        return shutil.which("iscc")
    for base in (os.environ.get("ProgramFiles", ""),
                 os.environ.get("ProgramFiles(x86)", "")):
        if not base:
            continue
        for name in ("Inno Setup 7", "Inno Setup 6", "Inno Setup 5"):
            p = os.path.join(base, name, "ISCC.exe")
            if os.path.exists(p):
                return p
    return None


def build_windows_installer():
    iscc = find_iscc()
    if not iscc:
        print("Inno Setup not found. Install it from https://jrsoftware.org/isdl.php "
              "and run this again, or take the portable exe from dist/.")
        return None
    run([iscc, os.path.join(ROOT, "packaging", "cadence.iss"),
         f"/DAppVersion={__version__}", f"/DArch={arch_tag()}"])
    name = f"{APP_NAME}-Setup-{__version__}-{arch_tag()}.exe"
    out = os.path.join(DIST, name)
    print(f"built {out}")
    return out


# ---------------------------------------------------------------- linux
DESKTOP = """[Desktop Entry]
Type=Application
Name=Cadence
GenericName=Controller Input Suite
Comment=Measure controller timing, test pads, and bind pad buttons to macros
Exec=/opt/cadence/Cadence
Icon=cadence
Terminal=false
Categories=Utility;Game;
Keywords=controller;gamepad;joystick;macro;input;
"""

CONTROL = """Package: cadence
Version: {version}
Section: utils
Priority: optional
Architecture: {debarch}
Maintainer: KayTwoOne <noreply@users.noreply.github.com>
Depends: libc6
Description: Controller input suite
 Measure the gaps between controller presses, check every pad the machine can
 see, and bind pad buttons to mouse and keyboard macros.
 .
 Reads controllers through the kernel joystick interface at /dev/input/js*.
 Your user needs to be in the "input" group to open those devices.
Homepage: https://github.com/KayTwoOne/Cadence
"""


def build_linux_packages(binary):
    made = []
    stage = os.path.join(BUILD, "linux")
    shutil.rmtree(stage, ignore_errors=True)
    opt = os.path.join(stage, "opt", "cadence")
    apps = os.path.join(stage, "usr", "share", "applications")
    icons = os.path.join(stage, "usr", "share", "icons", "hicolor")
    os.makedirs(opt, exist_ok=True)
    os.makedirs(apps, exist_ok=True)
    shutil.copy2(binary, os.path.join(opt, APP_NAME))
    os.chmod(os.path.join(opt, APP_NAME), 0o755)
    with open(os.path.join(apps, "cadence.desktop"), "w") as fh:
        fh.write(DESKTOP)
    for size in (16, 24, 32, 48, 64, 128, 256):
        src = os.path.join(ROOT, "assets", f"icon-{size}.png")
        if not os.path.exists(src):
            continue
        d = os.path.join(icons, f"{size}x{size}", "apps")
        os.makedirs(d, exist_ok=True)
        shutil.copy2(src, os.path.join(d, "cadence.png"))

    tar = os.path.join(DIST, f"{APP_NAME}-{__version__}-linux-{arch_tag()}.tar.gz")
    with tarfile.open(tar, "w:gz") as tf:
        tf.add(stage, arcname=f"{APP_NAME}-{__version__}")
    print(f"built {tar}")
    made.append(tar)

    if shutil.which("dpkg-deb"):
        debarch = {"x64": "amd64", "arm64": "arm64", "x86": "i386"}.get(
            arch_tag(), arch_tag())
        os.makedirs(os.path.join(stage, "DEBIAN"), exist_ok=True)
        with open(os.path.join(stage, "DEBIAN", "control"), "w") as fh:
            fh.write(CONTROL.format(version=__version__, debarch=debarch))
        deb = os.path.join(DIST, f"cadence_{__version__}_{debarch}.deb")
        run(["dpkg-deb", "--build", "--root-owner-group", stage, deb])
        print(f"built {deb}")
        made.append(deb)
    else:
        print("dpkg-deb not found, skipping the .deb (the tarball still works)")
    return made


def main():
    ap = argparse.ArgumentParser(description="Build Cadence.")
    ap.add_argument("--installer", action="store_true",
                    help="also produce an installer for this platform")
    ap.add_argument("--clean", action="store_true", help="remove build leftovers first")
    args = ap.parse_args()

    if args.clean:
        clean()
    os.makedirs(DIST, exist_ok=True)
    print(f"{APP_NAME} {__version__} for {sys.platform} {arch_tag()}")
    binary = build_binary()

    if args.installer:
        if sys.platform == "win32":
            build_windows_installer()
        else:
            build_linux_packages(binary)

    print("\nin dist/:")
    for f in sorted(os.listdir(DIST)):
        p = os.path.join(DIST, f)
        if os.path.isfile(p):
            print(f"  {f:48} {os.path.getsize(p) // 1024:7d} KB")


if __name__ == "__main__":
    main()
