#!/usr/bin/env python3
"""Create a repo-mirror release zip with a canonical in-tree TUI binary."""

# FILE: scripts/package_release.py
# PURPOSE: Assemble repo-mirror release zips that uv can install as editable source trees.
# OWNS: Release staging, junk exclusion, canonical TUI placement, and zip creation under dist/.
# EXPORTS: main - CLI entry point for release zip packaging.
# DOCS: agent_chat/plan_zip_distribution_2026-04-10.md, docs/arch_tui.md, .github/workflows/build-tui.yml

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = ROOT / "dist"
INCLUDE_PATHS = [
    "pyproject.toml",
    "README.md",
    "scripts",
    "silc",
    "static",
    "manager_web_ui",
    "tui_client",
]
EXCLUDED_NAMES = {".git", ".venv", "node_modules", "__pycache__", "target", "dist"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-name", required=True)
    parser.add_argument("--tui-asset-name", required=True)
    return parser.parse_args()


def stage_copy(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, ignore=_ignore_names)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _ignore_names(directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    current = Path(directory)
    rel_parts = current.resolve().relative_to(ROOT).parts
    for name in names:
        if name in EXCLUDED_NAMES:
            ignored.add(name)
            continue
        if rel_parts == ("tui_client",) and name == "dist":
            ignored.add(name)
    return ignored


def canonical_tui_name(asset_name: str) -> str:
    return "silc-tui.exe" if asset_name.endswith(".exe") else "silc-tui"


def main() -> int:
    args = parse_args()
    DIST_ROOT.mkdir(exist_ok=True)

    output_name = Path(args.output_name).name
    stage_root = DIST_ROOT / Path(output_name).stem
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True)

    for relative in INCLUDE_PATHS:
        source = ROOT / relative
        if not source.exists():
            raise FileNotFoundError(f"Required path is missing: {source}")
        stage_copy(source, stage_root / relative)

    source_tui = ROOT / "tui_client" / "dist" / args.tui_asset_name
    if not source_tui.is_file():
        raise FileNotFoundError(f"Built TUI asset is missing: {source_tui}")

    staged_tui_dir = stage_root / "tui_client" / "dist"
    staged_tui_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_tui, staged_tui_dir / canonical_tui_name(args.tui_asset_name))

    archive_base = DIST_ROOT / output_name.removesuffix(".zip")
    archive_path = shutil.make_archive(
        str(archive_base), "zip", root_dir=DIST_ROOT, base_dir=stage_root.name
    )
    print(archive_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
