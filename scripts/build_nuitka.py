#!/usr/bin/env python3
"""Build the SILC onefile executable with Nuitka."""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"


def _ensure_root_on_path() -> None:
    root_str = str(ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def _read_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _host_target() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        return "x86_64-pc-windows-msvc"
    if system == "darwin":
        return (
            "aarch64-apple-darwin"
            if "arm" in machine or "aarch64" in machine
            else "x86_64-apple-darwin"
        )
    if system == "linux":
        return "x86_64-unknown-linux-gnu"
    raise SystemExit(f"Unsupported host platform for SILC build: {platform.system()}")


def _rust_binary_name() -> str:
    return "silc-tui.exe" if platform.system().lower() == "windows" else "silc-tui"


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def _build_web_ui() -> None:
    from silc.utils.build_web import build_web_ui

    if build_web_ui() != 0:
        raise SystemExit("Web UI build failed")


def _existing_rust_binary(target: str) -> Path | None:
    dist_dir = ROOT / "tui_client" / "dist"
    target_dir = ROOT / "tui_client" / "target" / target / "release"

    if platform.system().lower() == "windows":
        candidates = (
            dist_dir / "silc-tui.exe",
            dist_dir / "silc-tui-windows.exe",
            target_dir / "silc-tui.exe",
        )
    elif platform.system().lower() == "darwin":
        candidates = (
            dist_dir / "silc-tui",
            dist_dir / "silc-tui-macos",
            target_dir / "silc-tui",
        )
    else:
        candidates = (
            dist_dir / "silc-tui",
            dist_dir / "silc-tui-linux",
            target_dir / "silc-tui",
        )

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _build_rust_tui(target: str) -> Path:
    existing = _existing_rust_binary(target)
    if existing is not None:
        return existing

    cargo_manifest = ROOT / "tui_client" / "Cargo.toml"
    if not cargo_manifest.is_file():
        raise SystemExit(f"Missing Rust manifest: {cargo_manifest}")

    _run(["rustup", "target", "add", target], cwd=ROOT / "tui_client")
    _run(
        [
            "cargo",
            "build",
            "--release",
            "--target",
            target,
            "--manifest-path",
            str(cargo_manifest),
        ],
        cwd=ROOT,
    )

    artifact = ROOT / "tui_client" / "target" / target / "release" / _rust_binary_name()
    if not artifact.is_file():
        raise SystemExit(f"Expected Rust binary not found: {artifact}")
    return artifact


def _nuitka_command(rust_binary: Path, output_name: str, version: str) -> list[str]:
    main_dir = ROOT / "silc"
    tempdir_spec = "{CACHE_DIR}/silc/{PRODUCT}/{VERSION}"
    if platform.system().lower() == "windows":
        compiler = ["--mingw64"]
    else:
        compiler = []
    return [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--assume-yes-for-downloads",
        "--python-flag=-m",
        f"--onefile-tempdir-spec={tempdir_spec}",
        *compiler,
        "--nofollow-import-to=tests,manual_tests,agent_chat,pytest,pytest_asyncio",
        "--include-package=silc",
        f"--include-data-dir={ROOT / 'static'}=static",
        f"--include-data-files={rust_binary}=bin/{rust_binary.name}",
        "--company-name=SILC",
        "--product-name=silc",
        f"--product-version={version}",
        f"--output-filename={output_name}",
        f"--output-dir={DIST_DIR}",
        str(main_dir),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=_host_target(), help="Rust target triple")
    parser.add_argument(
        "--output-name", default=None, help="Final executable file name"
    )
    args = parser.parse_args()

    _ensure_root_on_path()
    _build_web_ui()
    rust_binary = _build_rust_tui(args.target)

    version = _read_version()
    output_name = args.output_name
    if output_name is None:
        output_name = "silc.exe" if platform.system().lower() == "windows" else "silc"

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    _run(_nuitka_command(rust_binary, output_name, version), cwd=ROOT)


if __name__ == "__main__":
    main()
