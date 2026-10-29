r"""Builds the Windows release: MerchantsRise.exe, which needs nothing installed.

Usage:
    py build_tools\Release\build_release.py 0.1.0
    py build_tools\Release\build_release.py 0.1.0 --no-smoke-test

Writes release\MerchantsRise-<version>-windows.zip. It holds one folder,
MerchantsRise/, with MerchantsRise.exe, a short README.txt and _internal/: a
PyInstaller build (one folder, no console) with its own Python, pygame,
pytmx, the code and the assets. Unzip it, double-click the exe.

Only the assets git tracks go in (so a build here and on GitHub's runner are
the same), without what the game never loads: the GIMP sources (.xcf), the
sketches, the raw sound recordings, the old pictures and the readme gif.
Saves and settings.json are not shipped; the game makes them in _internal/
when played, so unzipping a newer release over an old one keeps them.

The build runs in its own venv, build_tools/Release/.venv, made on first use
from requirements.txt here (the game's packages plus PyInstaller), so nothing
from the dev venv (numpy, the Sprite Manager's packages) is bundled. Before
zipping, the exe is started with MERCHANTS_RISE_SMOKE_TEST (see main.py): it
starts a new game, plays a few seconds and quits, which catches a module or
an asset that did not make it in.

.github/workflows/release.yml runs this on GitHub when a tag like v0.1.0 is
pushed and publishes the zip as a release.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import venv
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VENV = HERE / ".venv"
VENV_PYTHON = VENV / "Scripts" / "python.exe"
NAME = "MerchantsRise"
ICON = ROOT / "assets" / "pictures" / "Icon.png"

# Tracked assets the game never loads
EXCLUDED_SUFFIXES = (".xcf", ".gif")
EXCLUDED_FOLDERS = frozenset({"sketches", "raw materials", "old"})  # lower case
EXCLUDED_FOLDER_PREFIXES = ("sketch",)  # houses/Sketches/Sketch...

SMOKE_TEST_PLAY_SECONDS = 8
SMOKE_TEST_TIMEOUT_S = 180.0

README = """\
Merchant's Rise {version}

Double-click MerchantsRise.exe to play. Nothing needs to be installed.

Windows may say "Windows protected your PC" the first time, because the game
is not signed: click "More info", then "Run anyway".

Keep MerchantsRise.exe and the _internal folder together; the game needs
both. Your saves are kept in _internal/saves. To update, unzip a newer
release over this folder: your saves stay.

If the game closes with an error, a crash.log appears next to the exe.
Please send it along.
"""


def run(command: list[str], **kwargs) -> None:
    """Runs a command, stopping the build if it fails."""
    print("$", " ".join(command), flush=True)
    subprocess.run(command, check=True, **kwargs)


def ensure_build_venv() -> None:
    """Re-runs this script in the build venv, making it first if needed."""
    if Path(sys.prefix).resolve() == VENV.resolve():
        return
    if not VENV_PYTHON.is_file():
        print(f"Making the build venv in {VENV} ...", flush=True)
        venv.create(VENV, with_pip=True)
    run([str(VENV_PYTHON), "-m", "pip", "install", "--disable-pip-version-check", "--quiet",
         "-r", str(HERE / "requirements.txt")])
    sys.exit(subprocess.run([str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]]).returncode)


def is_excluded(path: str) -> bool:
    """Tells whether a tracked asset (a path relative to the repo) stays out."""
    *folders, file = path.split("/")
    lowered = [f.lower() for f in folders]
    return (file.lower().endswith(EXCLUDED_SUFFIXES)
            or any(f in EXCLUDED_FOLDERS for f in lowered)
            or any(f.startswith(EXCLUDED_FOLDER_PREFIXES) for f in lowered))


def stage_assets(target: Path) -> int:
    """Copies the tracked assets the game needs into ``target``/assets.

    Returns:
        How many files were copied.
    """
    listed = subprocess.run(["git", "ls-files", "-z", "assets"], cwd=ROOT, check=True,
                            capture_output=True).stdout.decode("utf-8")
    copied = 0
    for path in filter(None, listed.split("\0")):
        if is_excluded(path):
            continue
        source = ROOT / path
        if not source.is_file():  # tracked but deleted in the working tree
            continue
        destination = target / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied += 1
    return copied


def build_exe(assets: Path, work: Path) -> Path:
    """Builds MerchantsRise.exe with PyInstaller: one folder, no console.

    Returns:
        The folder holding MerchantsRise.exe and _internal/.
    """
    run([sys.executable, "-m", "PyInstaller",
         "--noconfirm", "--clean", "--log-level", "WARN",
         "--onedir", "--windowed",
         "--name", NAME,
         "--icon", str(ICON),  # PyInstaller turns it into an .ico with Pillow
         "--distpath", str(work / "dist"),
         "--workpath", str(work / "build"),
         "--specpath", str(work),
         "--paths", str(ROOT),
         "--collect-submodules", "src",
         "--add-data", f"{assets}{os.pathsep}assets",
         str(ROOT / "main.py")])
    return work / "dist" / NAME


def smoke_test(folder: Path) -> None:
    """Starts the exe, lets it play a new game for a few seconds and checks it quit cleanly."""
    exe = folder / f"{NAME}.exe"
    env = {**os.environ,
           "MERCHANTS_RISE_SMOKE_TEST": str(SMOKE_TEST_PLAY_SECONDS),
           "SDL_AUDIODRIVER": os.environ.get("SDL_AUDIODRIVER", "dummy")}
    started = time.monotonic()
    try:
        code = subprocess.run([str(exe)], env=env, timeout=SMOKE_TEST_TIMEOUT_S).returncode
    except subprocess.TimeoutExpired:
        sys.exit(f"Smoke test failed: {exe.name} did not quit within {SMOKE_TEST_TIMEOUT_S:.0f} s.")
    crash_log = folder / "crash.log"
    if code != 0:
        details = crash_log.read_text(encoding="utf-8") if crash_log.is_file() else "(no crash.log)"
        sys.exit(f"Smoke test failed: {exe.name} exited with {code}.\n{details}")
    print(f"{exe.name} started a new game, played and quit ({time.monotonic() - started:.0f} s).")


def write_zip(target: Path, entries: list[tuple[Path, str]], readme: str) -> None:
    """Writes the release zip in a fixed order."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(f"{NAME}/README.txt", readme.replace("\n", "\r\n"))
        for source, arcname in sorted(entries, key=lambda e: e[1]):
            archive.write(source, arcname)


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("version", help="the release's version, e.g. 0.1.0")
    parser.add_argument("--out", type=Path, default=ROOT / "release", help="output folder")
    parser.add_argument("--no-smoke-test", action="store_true",
                        help="zip without starting the exe first")
    parser.add_argument("--work", type=Path,
                        help="build in this (empty) folder and keep it, to look into the build")
    args = parser.parse_args()
    if sys.platform != "win32":
        sys.exit("MerchantsRise.exe can only be built on Windows.")
    ensure_build_venv()

    with tempfile.TemporaryDirectory(prefix="merchants-rise-") as tmp:
        work = args.work.resolve() if args.work else Path(tmp)
        print("Staging the assets ...", flush=True)
        print(f"{stage_assets(work)} files.")
        folder = build_exe(work / "assets", work)
        # Listed before the smoke test, so the saves and settings it writes stay out
        entries = [(path, f"{NAME}/{path.relative_to(folder).as_posix()}")
                   for path in sorted(folder.rglob("*")) if path.is_file()]
        if not args.no_smoke_test:
            smoke_test(folder)
        target = args.out / f"{NAME}-{args.version}-windows.zip"
        print(f"Writing {target} ...", flush=True)
        write_zip(target, entries, README.format(version=args.version))
    print(f"{target} ({target.stat().st_size // (1024 * 1024)} MB, {len(entries) + 1} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
