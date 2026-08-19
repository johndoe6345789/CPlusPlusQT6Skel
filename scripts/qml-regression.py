#!/usr/bin/env python3
"""Regression gate for QML correctness, built on Qt's own qmllint.

qmllint knows the type system, so it catches things a textual check cannot:
assigning a property a component does not have, incompatible types, and
layout-positioning misuse. That is the class of bug that has repeatedly
reached a release build here.

The codebase does not start clean, so this ratchets rather than demanding
zero: counts per category are compared against scripts/qmllint-baseline.json
and any increase fails. Decreases are reported so the baseline can be lowered
as the backlog is worked off -- that is the mechanism that stops the count
drifting back up.

Only high-signal categories are gated. `unqualified` is excluded on purpose:
3000+ hits, dominated by ordinary unqualified id access, so gating it would
bury the categories that matter.

Usage:
    python3 scripts/qml-regression.py                  # check
    python3 scripts/qml-regression.py --update-baseline
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = Path(__file__).resolve().parent / "qmllint-baseline.json"

# Categories worth failing a build over.
GATED = [
    "missing-property",
    "incompatible-type",
    "unresolved-type",
    "Quick.layout-positioning",
    "property-override",
    "unreachable-code",
]


def find_qmllint() -> str:
    for cand in ("qmllint", "/opt/homebrew/opt/qt/bin/qmllint"):
        path = shutil.which(cand) or (cand if Path(cand).exists() else None)
        if path:
            return path
    print("qml-regression: qmllint not found on PATH", file=sys.stderr)
    sys.exit(2)


def run_qmllint() -> str:
    files = sorted(
        [str(p) for p in (ROOT / "qml").rglob("*.qml")]
        + [str(p) for p in (ROOT / "packages").rglob("*.qml")]
    )
    if not files:
        print("qml-regression: no QML files found", file=sys.stderr)
        sys.exit(2)
    proc = subprocess.run(
        [find_qmllint(), "-I", str(ROOT / "imports")] + files,
        capture_output=True, text=True,
    )
    # qmllint exits non-zero when it reports warnings; that is expected here.
    return proc.stdout + proc.stderr


def categorise(output: str) -> Counter:
    counts = Counter()
    for line in output.splitlines():
        m = re.search(r"\[([A-Za-z.-]+)\]\s*$", line)
        if m and m.group(1) in GATED:
            counts[m.group(1)] += 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--update-baseline", action="store_true",
                    help="record current counts as the new ceiling")
    args = ap.parse_args()

    counts = categorise(run_qmllint())

    if args.update_baseline:
        BASELINE.write_text(json.dumps(
            {k: counts.get(k, 0) for k in GATED}, indent=2) + "\n")
        print("qml-regression: baseline updated")
        for k in GATED:
            print(f"  {k:26s} {counts.get(k, 0)}")
        return 0

    if not BASELINE.exists():
        print("qml-regression: no baseline; run with --update-baseline")
        return 2

    base = json.loads(BASELINE.read_text())
    worse, better = [], []
    for cat in GATED:
        now, was = counts.get(cat, 0), base.get(cat, 0)
        if now > was:
            worse.append((cat, was, now))
        elif now < was:
            better.append((cat, was, now))

    for cat, was, now in better:
        print(f"  improved: {cat} {was} -> {now}")
    if better and not worse:
        print("\nqml-regression: baseline can be lowered "
              "(scripts/qml-regression.py --update-baseline)")

    if worse:
        print("\nqml-regression: FAILED — new issues introduced\n")
        for cat, was, now in worse:
            print(f"  {cat}: {was} -> {now}  (+{now - was})")
        print("\nRun qmllint locally to see them:")
        print("  qmllint -I imports $(find qml packages -name '*.qml')")
        return 1

    print("qml-regression: clean (no category above baseline)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
