#!/usr/bin/env python3
"""Guard against layout and resource bugs that have already shipped once.

Every check here corresponds to a defect that reached a release build and
produced a visibly broken UI. They are cheap textual checks, not a QML parser:
the point is to stop a known-bad pattern reappearing, not to prove correctness.

Run: python3 scripts/lint-qml.py    (exits non-zero on any finding)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
findings: list[str] = []


def report(path: Path, line: int, msg: str) -> None:
    findings.append(f"{path.relative_to(ROOT)}:{line}: {msg}")


def qml_files():
    for d in ("qml", "packages"):
        yield from sorted((ROOT / d).rglob("*.qml"))


def js_files():
    for d in ("qml", "packages"):
        yield from sorted((ROOT / d).rglob("*.js"))


def check_scrollview_contentwidth() -> None:
    """A ScrollView whose child binds width to parent.width needs an explicit
    contentWidth, or the two bind circularly and the view collapses to an
    implicit width -- clipping content at roughly half the window."""
    for f in qml_files():
        text = f.read_text(errors="ignore")
        if "ScrollView" not in text:
            continue
        for m in re.finditer(r"ScrollView\s*\{", text):
            # Look at the declaration body only (up to the first nested item).
            body = text[m.end():m.end() + 400]
            head = body.split("{")[0]
            if "contentWidth" not in head and "width: parent.width" in body:
                line = text[:m.start()].count("\n") + 1
                report(f, line, "ScrollView without contentWidth: availableWidth "
                                "(content width binds circularly and clips)")


def layout_backed_components() -> dict[str, str]:
    """Components whose default property funnels children into a *Layout*.

    Derived, not hardcoded: CPaper is a plain Rectangle, so anchors.fill is
    correct there, and an earlier hardcoded list produced ~20 false positives
    on it. Only components whose default alias targets a Layout are affected.
    """
    found: dict[str, str] = {}
    for f in (ROOT / "qml").rglob("*.qml"):
        text = f.read_text(errors="ignore")
        m = re.search(r"default property alias\s+\w+\s*:\s*(\w+)\.data", text)
        if not m:
            continue
        target = m.group(1)
        decl = re.search(rf"(\w*Layout)\s*\{{\s*\n\s*id:\s*{target}\b", text)
        if decl:
            found[f.stem] = decl.group(1)
    return found


def check_anchors_inside_card() -> None:
    """Children of a layout-backed component land inside that component's own
    Layout, so anchors.fill anchors against a layout-managed parent: undefined
    behaviour, and anchored items are excluded from the layout's implicit
    size, which collapses the container to nothing."""
    backed = layout_backed_components()
    if not backed:
        return
    names = "|".join(sorted(backed))
    open_re = re.compile(rf"^\s*({names})\s*\{{")
    for f in qml_files():
        lines = f.read_text(errors="ignore").splitlines()
        stack: list[str] = []
        for i, line in enumerate(lines, 1):
            m = open_re.match(line)
            if m:
                stack.append(m.group(1))
                continue
            if stack and re.match(r"\s*anchors\.fill:\s*parent", line):
                comp = stack[-1]
                report(f, i, f"anchors.fill inside {comp} — its children go into "
                             f"a {backed[comp]}; use Layout.fillWidth instead")
            if stack and re.match(r"\s*\}\s*$", line):
                stack.pop()


def check_split_regex() -> None:
    """A regex literal broken across a newline is a hard syntax error; the
    narrow line-wrapping style in this repo has produced one before."""
    for f in list(qml_files()) + list(js_files()):
        for i, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
            if re.search(r"match\(/[^/]*$", line):
                report(f, i, "regex literal appears to be split across lines")


def check_relative_config_paths() -> None:
    """Qt.resolvedUrl resolves against the .js file. Anything under
    qmllib/MetaBuilder sits two levels below the config directory, so a bare
    'config/...' silently misses and the caller falls through a catch."""
    target = ROOT / "qml" / "MetaBuilder"
    if not target.exists():
        return
    for f in sorted(target.rglob("*.js")):
        for i, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
            if re.search(r'loadJson\(\s*$', line):
                continue
            if re.search(r'"config/[^"]+\.json"', line):
                report(f, i, 'bare "config/..." path — needs "../../config/..." '
                             "from qmllib/MetaBuilder")


def check_quickstyle() -> None:
    """The native Controls styles discard custom background/contentItem, which
    this codebase sets on every button and field."""
    main = ROOT / "main.cpp"
    if main.exists() and "QQuickStyle::setStyle" not in main.read_text(errors="ignore"):
        report(main, 1, "QQuickStyle::setStyle is missing — native styles will "
                        "discard all custom control styling")


def main() -> int:
    for check in (check_scrollview_contentwidth, check_anchors_inside_card,
                  check_split_regex, check_relative_config_paths,
                  check_quickstyle):
        check()

    if findings:
        print(f"lint-qml: {len(findings)} finding(s)\n")
        for f in findings:
            print("  " + f)
        print("\nEach of these has caused a visible bug before; see "
              "scripts/lint-qml.py for why.")
        return 1

    print("lint-qml: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
