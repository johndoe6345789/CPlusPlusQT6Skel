#!/usr/bin/env python3
"""Visual regression: render views headlessly and diff against references.

Uses the app's --capture mode with Qt's software renderer
(QT_QUICK_BACKEND=software, QT_QPA_PLATFORM=offscreen). GPU rasterisation
varies between machines and drivers, which would make image comparison
useless; the software path is bit-identical run to run, which was verified
before any reference was committed.

Layout bugs are what this is for. The breakages found by hand in this project
-- content clipped at half width, cards collapsed to nothing, a hero
overlapping the strip below it -- are all obvious in a picture and invisible
to a type checker.

    python3 scripts/visual-regression.py --app <path-to-binary>
    python3 scripts/visual-regression.py --app <path> --update-refs
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# References are per-platform. The software renderer is bit-identical run to
# run on one machine, but font rasterisation and the available font families
# differ between macOS and Linux, so a macOS reference will never match a
# Linux runner. Each platform keeps its own set; a platform with no references
# reports that rather than failing, so CI can adopt this incrementally.
PLATFORM = {"darwin": "macos", "linux": "linux", "win32": "windows"}.get(
    sys.platform, sys.platform)
REFS = ROOT / "tests" / "visual" / "refs" / PLATFORM

# Views reachable without authenticating, at the breakpoints that matter:
# phone, tablet, desktop.
# --capture-view sets currentView directly, so views the nav gates behind a
# login are still reachable for rendering.
VIEWS = [
    "frontpage", "login", "dashboard", "profile", "moderator", "admin",
    "god-panel", "supergod", "settings", "comments",
    "marketplace", "storybook", "watchtower", "analytics", "gallery",
]
SIZES = [("phone", 390, 844), ("tablet", 768, 1024), ("desktop", 1360, 860)]

# A handful of pixels can differ from font hinting on a different host; a real
# layout regression moves thousands.
TOLERANCE_PIXELS = 200


def capture(app: str, view: str, w: int, h: int, out: Path) -> bool:
    env = dict(os.environ,
               QT_QUICK_BACKEND="software",
               QT_QPA_PLATFORM="offscreen")
    proc = subprocess.run(
        [app, f"--capture-view={view}", f"--capture-size={w}x{h}",
         f"--capture-out={out}"],
        env=env, capture_output=True, text=True, timeout=120)
    if not out.exists():
        print(f"  !! capture failed for {view}@{w}x{h}")
        print("     " + (proc.stderr or proc.stdout or "").strip()[:300])
        return False
    return True


def compare(a: Path, b: Path) -> int:
    from PIL import Image, ImageChops
    ia = Image.open(a).convert("RGB")
    ib = Image.open(b).convert("RGB")
    if ia.size != ib.size:
        return -1
    diff = ImageChops.difference(ia, ib)
    return sum(1 for px in diff.getdata() if px != (0, 0, 0))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--app", required=True, help="path to the built binary")
    ap.add_argument("--update-refs", action="store_true")
    args = ap.parse_args()

    if not Path(args.app).exists():
        print(f"visual-regression: no such binary: {args.app}", file=sys.stderr)
        return 2
    REFS.mkdir(parents=True, exist_ok=True)

    failures, missing, checked = [], [], 0
    with tempfile.TemporaryDirectory() as tmp:
        for view in VIEWS:
            for label, w, h in SIZES:
                name = f"{view}-{label}.png"
                shot = Path(tmp) / name
                if not capture(args.app, view, w, h, shot):
                    failures.append((name, "capture failed"))
                    continue
                ref = REFS / name
                if args.update_refs:
                    ref.write_bytes(shot.read_bytes())
                    print(f"  wrote {name}")
                    continue
                if not ref.exists():
                    missing.append(name)
                    continue
                checked += 1
                n = compare(shot, ref)
                if n < 0:
                    failures.append((name, "size differs from reference"))
                elif n > TOLERANCE_PIXELS:
                    failures.append((name, f"{n} pixels differ"))

    if args.update_refs:
        print("\nvisual-regression: references updated")
        return 0
    if missing:
        if len(missing) == len(VIEWS) * len(SIZES):
            # No baseline for this platform at all. Not a regression -- say so
            # and skip, so adding a new runner OS does not read as a failure.
            print(f"visual-regression: no references for '{PLATFORM}' yet "
                  f"(skipping). Generate them on this platform with "
                  f"--update-refs.")
            return 0
        print("visual-regression: no reference for: " + ", ".join(missing))
        print("Run with --update-refs to create them.")
        return 2
    if failures:
        print(f"visual-regression: FAILED ({len(failures)} of {checked})\n")
        for name, why in failures:
            print(f"  {name}: {why}")
        print("\nIf the change is intentional, re-run with --update-refs "
              "and review the image diff in the commit.")
        return 1
    print(f"visual-regression: clean ({checked} views matched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
