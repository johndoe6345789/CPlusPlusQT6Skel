#!/usr/bin/env python3
"""Auto-generate CMakeLists.txt from project structure and cmake_config.json.

Scans QML files, C++ sources, SVG/audio assets, and package metadata to produce
a complete CMakeLists.txt for the Qt6 DBAL Observatory frontend.

Supports extracted component layout where QML files live in ../../libraries/qml/
and are referenced via relative paths with QT_RESOURCE_ALIAS for correct QRC URIs.

Usage:
    python3 generate_cmake.py                     # Write CMakeLists.txt
    python3 generate_cmake.py --dry-run            # Print without writing
    python3 generate_cmake.py --output build.cmake # Custom output path
    python3 generate_cmake.py --config my.json     # Custom config file
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional


def load_config(config_path: str) -> dict:
    """Load and validate cmake_config.json."""
    path = Path(config_path)
    if not path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def _scan_dir(directory: str, extensions: tuple[str, ...]) -> list[str]:
    """Walk a directory (following symlinks) and return matching files."""
    result = []
    for dirpath, _dirnames, filenames in os.walk(directory, followlinks=True):
        for fn in filenames:
            if fn.endswith(extensions):
                result.append(os.path.join(dirpath, fn))
    return sorted(result)


# Project layout. Defaults mirror the values that used to be hardcoded
# throughout this file; cmake_config.json's "paths" overrides any of them.
# Keeping the layout in config is the point -- a hardcoded module list here
# went stale across a refactor and quietly dropped the component library out
# of the build.
# Order of the generated file when cmake_config.json does not override it
# with "cmake_pipeline". A bare string names a Python emitter; {"block":
# "..."} renders a template from "cmake_blocks".
DEFAULT_PIPELINE: list = [
    "header",
    "project",
    "msvc_cplusplus",
    "conan_toolchain",
    "find_qt",
    "executable",
    "compile_definitions",
    "resource_aliases",
    "qml_module",
    "svg_resources",
    "link_libraries",
    "features",
    {
        "block": "update_channel"
    },
    {
        "block": "icon_runtime"
    },
    {
        "block": "icon_windows"
    },
    {
        "block": "icon_linux"
    },
    "macos_bundle",
    "msvc_include_path",
    "finalize",
    "ninja_warning",
    "install"
]


PATHS: dict = {
    "shared_qml_roots": ["../../libraries/qml", "qml"],
    "qmllib": "qmllib",
    "packages": "packages",
    "config": "config",
    "src": "src",
    "svg_assets": "assets/svg",
    "audio_assets": "assets/audio",
    "entry_point": "main.cpp",
}


def apply_paths(config: dict) -> None:
    """Merge the JSON "paths" block over the defaults."""
    PATHS.update(config.get("paths", {}) or {})


def find_shared_qml_root(root_dir: Path) -> Optional[Path]:
    """Locate the shared QML component tree.

    Two layouts are supported: the monorepo one, where this project sits at
    <repo>/frontends/qt6/ and the components live in <repo>/libraries/qml/, and
    the standalone one, where the same tree is vendored in as ./qml/.
    """
    candidates = [
        (root_dir / rel).resolve() if rel.startswith("..") else root_dir / rel
        for rel in PATHS["shared_qml_roots"]
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def find_root_qml_files(root_dir: Path) -> list[tuple[str, Optional[str]]]:
    """Find root QML/JS files. Returns (rel_path, alias_or_None) tuples.

    Checks both the local directory and ../../qml/qt6/ for extracted files.
    Extracted files get a QT_RESOURCE_ALIAS so their QRC path matches the original.
    """
    result = []
    # Local files
    for fn in sorted(os.listdir(str(root_dir))):
        if fn.endswith((".qml", ".js")) and os.path.isfile(root_dir / fn):
            result.append((fn, None))

    # Shared tree: qt6/ holds the files that belong at the QRC root
    local_names = {t[0] for t in result}
    shared_qml = find_shared_qml_root(root_dir)
    extracted_dir = shared_qml / "qt6" if shared_qml else None
    if extracted_dir and extracted_dir.exists():
        for fn in sorted(os.listdir(str(extracted_dir))):
            if fn.endswith((".qml", ".js")) and fn not in local_names:
                rel = os.path.relpath(extracted_dir / fn, root_dir)
                result.append((rel, fn))
    return result


def find_qmllib_files(root_dir: Path,
                      shared_modules: Optional[list[str]] = None,
                      ) -> dict[str, list[tuple[str, Optional[str]]]]:
    """Find qmllib QML/JS and qmldir files. Returns dict with 'qml' and 'resources'.

    Searches local qmllib/ (following symlinks) and extracted ../../qml/{module}/
    directories. Extracted files get QT_RESOURCE_ALIAS for correct QRC URIs.
    """
    if shared_modules is None:
        shared_modules = ["MetaBuilder", "Material", "dbal"]
    result: dict[str, list[tuple[str, Optional[str]]]] = {"qml": [], "resources": []}

    # Mapping of (real_directory, qrc_prefix)
    dirs_to_scan: list[tuple[Path, str]] = []

    # Local qmllib/ with symlinks
    qmllib_dir = root_dir / PATHS["qmllib"]
    if qmllib_dir.exists():
        dirs_to_scan.append((qmllib_dir, "qmllib"))

    # Shared tree: {MetaBuilder,Material,dbal}
    extracted_qml = find_shared_qml_root(root_dir)
    if extracted_qml:
        # Which shared modules get compiled into the QRC. Config-driven
        # rather than hardcoded: this list silently went stale across a
        # refactor, which is how qml/components (the entire component
        # library), qml/hybrid and qml/widgets ended up as no build input at
        # all -- they are only copied into the bundle POST_BUILD, so editing
        # one does not trigger a rebuild.
        #
        # NB adding a directory here is not sufficient on its own: these are
        # aliased under qmllib/<module>, whereas the component library is
        # consumed as `import QmlComponents 1.0` resolved from the on-disk
        # import path. Compiling it in without also moving that import would
        # produce two copies that drift.
        for module in shared_modules:
            candidate = extracted_qml / module
            if candidate.exists() and not (qmllib_dir / module).exists():
                dirs_to_scan.append((candidate, f"qmllib/{module}"))

    for scan_dir, prefix in dirs_to_scan:
        for dirpath, _dirnames, filenames in os.walk(str(scan_dir), followlinks=True):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel_to_root = os.path.relpath(full, str(root_dir))
                # Compute the alias: prefix + path relative to scan_dir
                rel_to_scan = os.path.relpath(full, str(scan_dir))
                alias_path = f"{prefix}/{rel_to_scan}"

                # Only need alias if real path differs from desired QRC path
                needs_alias = rel_to_root != alias_path

                if fn.endswith((".qml", ".js")):
                    result["qml"].append((rel_to_root, alias_path if needs_alias else None))
                elif fn == "qmldir":
                    result["resources"].append((rel_to_root, alias_path if needs_alias else None))

    # Sort by alias (or real path)
    result["qml"].sort(key=lambda t: t[1] or t[0])
    result["resources"].sort(key=lambda t: t[1] or t[0])
    return result


def find_component_tree_files(root_dir: Path, rel: str) -> list[str]:
    """Every file of the shared component tree, for embedding in the QRC.

    These are currently copied into the bundle after linking and loaded from
    disk, which means they are not build inputs: editing one does not trigger
    a rebuild and the bundle silently keeps the previous version.
    """
    base = root_dir / rel
    if not base.exists():
        return []
    out = []
    for p in sorted(base.rglob("*")):
        if p.is_dir() or p.name.startswith("."):
            continue
        if p.suffix in (".qml", ".js") or p.name == "qmldir":
            out.append(str(p.relative_to(root_dir)))
    return out


def find_package_qml_files(root_dir: Path) -> list[str]:
    """Find all *.qml and *.js files in packages/ subdirectories."""
    packages_dir = root_dir / PATHS["packages"]
    if not packages_dir.exists():
        return []
    files = sorted(
        list(packages_dir.rglob("*.qml")) + list(packages_dir.rglob("*.js"))
    )
    return [str(f.relative_to(root_dir)) for f in files]


def find_config_files(root_dir: Path) -> dict[str, list[str]]:
    """Find config/ files: JS goes into QML_FILES, JSON into RESOURCES."""
    config_dir = root_dir / PATHS["config"]
    result = {"qml": [], "resources": []}
    if not config_dir.exists():
        return result
    for f in sorted(config_dir.rglob("*.js")):
        result["qml"].append(str(f.relative_to(root_dir)))
    for f in sorted(config_dir.rglob("*.json")):
        result["resources"].append(str(f.relative_to(root_dir)))
    return result


def load_package_metadata(root_dir: Path) -> list[dict]:
    """Read metadata.json from each packages/ subdirectory."""
    packages_dir = root_dir / PATHS["packages"]
    if not packages_dir.exists():
        return []
    metadata = []
    for meta_file in sorted(packages_dir.rglob("metadata.json")):
        with open(meta_file) as f:
            data = json.load(f)
            data["_dir"] = str(meta_file.parent.relative_to(root_dir))
            metadata.append(data)
    return metadata


def find_svg_assets(root_dir: Path) -> list[str]:
    """Glob SVG assets from assets/svg/."""
    svg_dir = root_dir / PATHS["svg_assets"]
    if not svg_dir.exists():
        return []
    files = sorted(svg_dir.glob("*.svg"))
    return [str(f.relative_to(root_dir)) for f in files]


def find_audio_assets(root_dir: Path) -> list[str]:
    """Glob audio assets from assets/audio/."""
    audio_dir = root_dir / PATHS["audio_assets"]
    if not audio_dir.exists():
        return []
    files = sorted(audio_dir.rglob("*"))
    return [str(f.relative_to(root_dir)) for f in files if f.is_file()]


def find_cpp_sources(root_dir: Path) -> dict[str, list[str]]:
    """Find all *.cpp, *.h, and *.hpp files in src/."""
    src_dir = root_dir / PATHS["src"]
    result = {"cpp": [], "h": []}
    if not src_dir.exists():
        return result
    result["cpp"] = sorted(
        str(f.relative_to(root_dir)) for f in src_dir.rglob("*.cpp")
    )
    headers = list(src_dir.rglob("*.h")) + list(src_dir.rglob("*.hpp"))
    result["h"] = sorted(
        str(f.relative_to(root_dir)) for f in headers
    )
    return result


def render_block(name: str, config: dict, values: dict) -> list[str]:
    """Render a CMake block declared in cmake_config.json's "cmake_blocks".

    A block is a list of strings (one per output line) plus an optional
    "when" naming a dotted config path that must be truthy for it to emit.

    Substitution uses @name@ rather than ${name} deliberately: CMake's own
    variable syntax is ${...} and appears throughout these templates, so a
    ${...} placeholder would collide with the very text being emitted. This
    mirrors configure_file(... @ONLY), which exists for the same reason.

    A placeholder must be closed by a second @. That is what keeps macOS
    loader syntax intact -- INSTALL_RPATH "@executable_path/../Frameworks"
    survives precisely because @executable_path is not @executable@. Do not
    relax this into a bare @name match, and avoid naming a value after a
    loader prefix (executable_path, loader_path, rpath).
    """
    block = (config.get("cmake_blocks", {}) or {}).get(name)
    if not block:
        return []

    when = block.get("when")
    if when:
        node = config
        for part in when.split("."):
            if not isinstance(node, dict):
                node = None
                break
            node = node.get(part)
        if not node:
            return []

    out = []
    for line in block.get("lines", []):
        for key, val in values.items():
            line = line.replace(f"@{key}@", str(val))
        out.append(line)
    return out


def generate_cmake(config: dict, root_dir: Path) -> str:
    """Generate the full CMakeLists.txt content from config and discovered files."""
    proj = config["project"]
    qt = config["qt"]
    cpp = config["cpp"]
    qml = config["qml"]
    features = config.get("features", {})
    compile_defs = config.get("compile_definitions", {})

    # Discover files
    root_qml = find_root_qml_files(root_dir)
    qmllib = find_qmllib_files(root_dir, qml.get("shared_modules"))
    package_qml = find_package_qml_files(root_dir)
    config_files = find_config_files(root_dir)
    cpp_sources = find_cpp_sources(root_dir)
    svg_assets = find_svg_assets(root_dir)
    audio_assets = find_audio_assets(root_dir)
    packages_meta = load_package_metadata(root_dir)

    # Build Qt components string
    extra_components = [
        component
        for feature, component in qt.get("feature_components", {}).items()
        if features.get(feature)
    ]
    all_components = qt["components"] + extra_components
    qt_components_str = " ".join(all_components)

    # Build source files list
    # .hpp files with Q_OBJECT must be listed so AUTOMOC scans them
    hpp_headers = [h for h in cpp_sources["h"] if h.endswith(".hpp")]
    source_files = [PATHS["entry_point"]] + cpp_sources["cpp"] + hpp_headers

    # Collect all QML files: (path, alias_or_None)
    all_qml: list[tuple[str, Optional[str]]] = []
    all_qml.extend(root_qml)
    all_qml.extend(qmllib["qml"])
    all_qml.extend((p, None) for p in package_qml)
    all_qml.extend((p, None) for p in config_files["qml"])

    # Collect all resource files: (path, alias_or_None)
    all_res: list[tuple[str, Optional[str]]] = []
    all_res.extend((p, None) for p in audio_assets)
    all_res.extend((p, None) for p in config_files["resources"])
    all_res.extend(qmllib["resources"])

    # Separate files needing aliases
    aliased_files = [(path, alias) for path, alias in all_qml + all_res if alias]

    # Total counts for header
    total_qml = len(all_qml)

    # Compile definitions
    defs_lines = [
        f'target_compile_definitions({proj["executable"]} PRIVATE {k}="{v}")'
        for k, v in compile_defs.items()
    ]

    # Link libraries
    link_libs = " ".join(f"Qt6::{c}" for c in all_components)

    # Feature blocks
    feature_blocks = []
    if features.get("libopenmpt"):
        feature_blocks.append(f"""
# libopenmpt support
find_package(PkgConfig REQUIRED)
pkg_check_modules(OPENMPT REQUIRED libopenmpt)
target_include_directories({proj["executable"]} PRIVATE ${{OPENMPT_INCLUDE_DIRS}})
target_link_libraries({proj["executable"]} PRIVATE ${{OPENMPT_LIBRARIES}})""")

    # Package metadata comment block
    pkg_comment_lines = []
    if packages_meta:
        pkg_comment_lines.append("# Discovered packages:")
        for meta in packages_meta:
            pkg_comment_lines.append(
                f'#   {meta.get("packageId", "unknown"):20s} '
                f'v{meta.get("version", "?")} - {meta.get("name", "")}'
            )

    # ── Emitters ──────────────────────────────────────────────────────
    # Each returns the lines for one section. The order they run in is not
    # written here: it comes from "cmake_pipeline" in cmake_config.json, so
    # the shape of the generated file is data rather than control flow.
    def header():
        out = ["# AUTO-GENERATED by generate_cmake.py — do not edit manually",
               f"# Generated from cmake_config.json | {total_qml} QML files, "
               f"{len(source_files)} C++ sources, {len(svg_assets)} SVGs, "
               f"{len(audio_assets)} audio assets"]
        if pkg_comment_lines:
            out.append("#")
            out.extend(pkg_comment_lines)
        out.append("")
        return out

    def project():
        return ["cmake_minimum_required(VERSION 3.27)",
                f'project({proj["name"]} VERSION {proj["version"]} LANGUAGES CXX)',
                "",
                f"set(CMAKE_CXX_STANDARD {cpp['standard']})",
                "set(CMAKE_CXX_STANDARD_REQUIRED ON)",
                "set(CMAKE_EXPORT_COMPILE_COMMANDS ON)",
                "set(CMAKE_AUTOMOC ON)",
                ""]

    def msvc_cplusplus():
        return ["# MSVC: Qt requires correct __cplusplus macro value",
                "if(MSVC)", "    add_compile_options(/Zc:__cplusplus)", "endif()", ""]

    def conan_toolchain():
        return ["include(${CMAKE_BINARY_DIR}/conan_toolchain.cmake OPTIONAL)", ""]

    def find_qt():
        return [f"find_package(Qt6 COMPONENTS {qt_components_str} REQUIRED)",
                "qt_policy(SET QTP0001 NEW)", ""]

    def executable():
        out = [f"qt_add_executable({proj['executable']}"]
        out += [f"    {s}" for s in source_files]
        out += [")", ""]
        return out

    def compile_definitions():
        return list(defs_lines) + ([""] if defs_lines else [])

    def resource_aliases():
        if not aliased_files:
            return []
        out = ["# Map extracted files to their original QRC paths"]
        out += [f'set_source_files_properties({p} PROPERTIES QT_RESOURCE_ALIAS {a})'
                for p, a in aliased_files]
        out.append("")
        return out

    def qml_module():
        out = [f"qt_add_qml_module({proj['executable']}",
               f"    URI {qml['uri']}",
               f"    VERSION {qml['version']}",
               "    QML_FILES"]
        out += [f"        {p}" for p, _ in all_qml]
        if all_res:
            out.append("    RESOURCES")
            out += [f"        {p}" for p, _ in all_res]
        out += [")", ""]
        return out

    def component_tree():
        rel = PATHS.get("component_tree", "qml")
        files = find_component_tree_files(root_dir, rel)
        if not files:
            return []
        out = ["# Shared component tree, embedded so `import QmlComponents 1.0`",
               "# resolves from the binary. Placed under /qt/qml, which the engine",
               "# already has on its import path, so the module is found without a",
               "# disk copy -- that copy was not a build input, so editing a",
               "# component did not trigger a rebuild.",
               f'qt_add_resources({proj["executable"]} "component_tree"',
               '    PREFIX "/qt/qml/QmlComponents"',
               f'    BASE "{rel}"',
               "    FILES"]
        out += [f"        {f}" for f in files]
        out += [")", ""]
        return out

    def svg_resources():
        if not svg_assets:
            return []
        return ["# SVG assets",
                "file(GLOB SVG_ASSETS RELATIVE ${CMAKE_CURRENT_SOURCE_DIR} assets/svg/*.svg)",
                f'qt_add_resources({proj["executable"]} "svg_assets"',
                '    PREFIX "/"',
                "    FILES ${SVG_ASSETS}",
                ")", ""]

    def link_libraries():
        return [f"target_link_libraries({proj['executable']} PRIVATE",
                f"    {link_libs}", ")", ""]

    def features_block():
        out = []
        for block in feature_blocks:
            out.append(block)
            out.append("")
        return out

    def macos_bundle():
        macos = config.get("macos", {})
        if not macos.get("bundle", True):
            return []
        out = ["# macOS: build an .app bundle so macdeployqt can package a .dmg",
               "if(APPLE)",
               f'    set_target_properties({proj["executable"]} PROPERTIES',
               "        MACOSX_BUNDLE TRUE",
               f'        MACOSX_BUNDLE_BUNDLE_NAME "{macos.get("bundle_name", proj["name"])}"',
               f'        MACOSX_BUNDLE_GUI_IDENTIFIER "{macos.get("identifier", "local." + proj["name"])}"',
               f'        MACOSX_BUNDLE_BUNDLE_VERSION "{proj["version"]}"']
        icon = macos.get("icon")
        if icon:
            # CFBundleIconFile is the basename without extension; the .icns
            # itself must be copied into Contents/Resources to be found.
            icon_name = icon.rsplit("/", 1)[-1]
            out.append(f'        MACOSX_BUNDLE_ICON_FILE "{icon_name.rsplit(".", 1)[0]}"')
        out.append(f'        MACOSX_BUNDLE_SHORT_VERSION_STRING "{proj["version"]}"')
        out.append("    )")
        if icon:
            out.append(f'    set_source_files_properties("${{CMAKE_CURRENT_SOURCE_DIR}}/{icon}"')
            out.append("        PROPERTIES MACOSX_PACKAGE_LOCATION Resources)")
            out.append(f'    target_sources({proj["executable"]} PRIVATE "${{CMAKE_CURRENT_SOURCE_DIR}}/{icon}")')

        sparkle = macos.get("sparkle") or {}
        out.extend(render_block("sparkle", config, {
            "executable": proj["executable"],
            "version": sparkle.get("version", ""),
            "sha256": sparkle.get("sha256", ""),
            "feed_url": sparkle.get("feed_url", ""),
            "public_key": sparkle.get("public_key", ""),
        }))
        # packages/ stays on disk: PackageLoader watches it and hot-reloads
        # package views at runtime. The component tree no longer needs copying
        # -- it is compiled into the QRC, so there is one copy rather than two
        # that can drift.
        out += ["    # Package views are read from disk at runtime so they can be",
                "    # installed and hot-reloaded; copy them into the bundle.",
                f"    add_custom_command(TARGET {proj['executable']} POST_BUILD",
                "        COMMAND ${CMAKE_COMMAND} -E copy_directory",
                '            "${CMAKE_CURRENT_SOURCE_DIR}/packages"',
                f'            "$<TARGET_BUNDLE_CONTENT_DIR:{proj["executable"]}>/Resources/packages"',
                "        VERBATIM",
                "    )",
                "endif()", ""]
        return out

    def msvc_include_path():
        return ["# Conan Qt recipe: propagate CMAKE_INCLUDE_PATH entries for MSVC",
                "foreach(_inc ${CMAKE_INCLUDE_PATH})",
                f'    target_include_directories({proj["executable"]} PRIVATE "${{_inc}}")',
                "endforeach()", ""]

    def finalize():
        return [f"qt_finalize_executable({proj['executable']})", ""]

    def ninja_warning():
        return ['if(NOT "${CMAKE_GENERATOR}" STREQUAL "Ninja")',
                "  message(", "    STATUS",
                f'    "{proj["executable"]} is designed for Ninja; configure with `cmake -G Ninja` so the Conan Ninja toolchain is used."',
                "  )", "endif()", ""]

    def install_rules():
        return [f"install(TARGETS {proj['executable']}",
                "    BUNDLE  DESTINATION .",
                "    RUNTIME DESTINATION bin",
                ")", ""]

    emitters = {
        "header": header, "project": project,
        "msvc_cplusplus": msvc_cplusplus, "conan_toolchain": conan_toolchain,
        "find_qt": find_qt, "executable": executable,
        "compile_definitions": compile_definitions,
        "resource_aliases": resource_aliases, "qml_module": qml_module,
        "component_tree": component_tree,
        "svg_resources": svg_resources, "link_libraries": link_libraries,
        "features": features_block, "macos_bundle": macos_bundle,
        "msvc_include_path": msvc_include_path, "finalize": finalize,
        "ninja_warning": ninja_warning, "install": install_rules,
    }

    upd = config.get("update", {})
    icon_cfg = config.get("icon", {})
    block_values = {
        "update_channel": {
            "executable": proj["executable"], "version": proj["version"],
            "channel": upd.get("default_channel", "dev"),
            "repo": upd.get("repo", ""), "tag_prefix": upd.get("tag_prefix", ""),
        },
    }
    for _b in ("icon_runtime", "icon_windows", "icon_linux"):
        block_values[_b] = {
            "executable": proj["executable"],
            "runtime_png": icon_cfg.get("runtime_png", ""),
            "ico": icon_cfg.get("ico", ""),
            "linux_dir": icon_cfg.get("linux_dir", ""),
        }

    # ── Assemble, in the order the config asks for ────────────────────
    pipeline = config.get("cmake_pipeline") or DEFAULT_PIPELINE
    lines = []
    for step in pipeline:
        if isinstance(step, dict):
            name = step.get("block")
            if name:
                lines.extend(render_block(name, config,
                                          block_values.get(name, {})))
                continue
            step = step.get("step", "")
        if step not in emitters:
            raise SystemExit(
                f"cmake_pipeline: unknown step {step!r}. "
                f"Known steps: {', '.join(sorted(emitters))}")
        lines.extend(emitters[step]())

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Auto-generate CMakeLists.txt from project structure and cmake_config.json.",
        epilog="Examples:\n"
               "  python3 generate_cmake.py                     # Write CMakeLists.txt\n"
               "  python3 generate_cmake.py --dry-run            # Print without writing\n"
               "  python3 generate_cmake.py --output build.cmake # Custom output\n"
               "  python3 generate_cmake.py --config my.json     # Custom config\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default="cmake_config.json",
        help="Path to cmake_config.json (default: cmake_config.json)",
    )
    parser.add_argument(
        "--output",
        default="CMakeLists.txt",
        help="Output path for generated CMakeLists.txt (default: CMakeLists.txt)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated CMakeLists.txt to stdout without writing to disk",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Project root directory (default: directory containing this script)",
    )
    args = parser.parse_args()

    # Determine root directory
    if args.root:
        root_dir = Path(args.root).resolve()
    else:
        root_dir = Path(__file__).parent.resolve()

    # Resolve config path
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root_dir / config_path

    config = load_config(str(config_path))
    apply_paths(config)
    content = generate_cmake(config, root_dir)

    if args.dry_run:
        print(content)
        return

    # Resolve output path
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = root_dir / output_path

    with open(output_path, "w") as f:
        f.write(content)

    # Summary
    root_qml = find_root_qml_files(root_dir)
    qmllib = find_qmllib_files(root_dir, config["qml"].get("shared_modules"))
    package_qml = find_package_qml_files(root_dir)
    cpp_sources = find_cpp_sources(root_dir)
    svg_assets = find_svg_assets(root_dir)
    audio_assets = find_audio_assets(root_dir)
    packages_meta = load_package_metadata(root_dir)

    total_qml = len(root_qml) + len(qmllib["qml"]) + len(package_qml)
    total_cpp = len(cpp_sources["cpp"]) + 1

    print(f"Generated {output_path}")
    print(f"  QML files:    {total_qml} ({len(root_qml)} root, {len(qmllib['qml'])} qmllib, {len(package_qml)} packages)")
    print(f"  C++ sources:  {total_cpp} ({len(cpp_sources['cpp'])} in src/ + main.cpp)")
    print(f"  C++ headers:  {len(cpp_sources['h'])}")
    print(f"  SVG assets:   {len(svg_assets)}")
    print(f"  Audio assets: {len(audio_assets)}")
    print(f"  Packages:     {len(packages_meta)} with metadata.json")
    aliased = len(root_qml) + len(qmllib["qml"]) + len(qmllib["resources"])
    aliased_count = sum(1 for _, a in root_qml if a) + sum(1 for _, a in qmllib["qml"] if a) + sum(1 for _, a in qmllib["resources"] if a)
    if aliased_count:
        print(f"  Aliased:      {aliased_count} files with QT_RESOURCE_ALIAS (extracted layout)")


if __name__ == "__main__":
    main()
