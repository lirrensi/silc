"""Helpers for bootstrapping the native SILC TUI binary."""

from __future__ import annotations

import os
import platform
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

import platformdirs
import requests

INSTALL_DIR_ENV = "SILC_TUI_BIN_DIR"
REPO_ENV = "SILC_TUI_RELEASE_REPO"
API_ENV = "SILC_TUI_RELEASE_API"
DEFAULT_GITHUB_REPO = "lirrensi/silc"
DEFAULT_RELEASE_API = (
    f"https://api.github.com/repos/{DEFAULT_GITHUB_REPO}/releases/latest"
)
RELEASE_HEADERS = {"Accept": "application/vnd.github.v3+json"}

BinaryProgress = Callable[[str], None]


class InstallerError(RuntimeError):
    """Raised when the native TUI binary cannot be installed."""


def ensure_native_tui_binary(progress: BinaryProgress | None = None) -> Path:
    """Return a ready-to-run native TUI binary, downloading it if necessary."""

    candidate = _cached_tui_binary_path()
    if _is_valid_native_binary(candidate):
        return candidate

    release = _fetch_latest_release()
    asset = _choose_asset_for_platform(release)
    if progress:
        progress(f"Downloading native TUI release asset {asset['name']}…")
    binary_source = _download_and_extract_asset(asset, progress=progress)
    _install_binary(binary_source, candidate)
    if progress:
        progress(f"Native TUI ready at {candidate}")
    return candidate


def _is_valid_native_binary(path: Path) -> bool:
    return path.exists() and os.access(path, os.X_OK)


def _cached_tui_binary_path() -> Path:
    install_dir = os.getenv(INSTALL_DIR_ENV)
    if install_dir:
        root = Path(install_dir)
    else:
        cache_root = platformdirs.user_cache_dir("silc")
        root = Path(cache_root) / "bin"
    binary_name = "silc-tui.exe" if sys.platform.startswith("win") else "silc-tui"
    return root.expanduser().resolve() / binary_name


def _fetch_latest_release() -> dict:
    api_url = os.getenv(API_ENV) or DEFAULT_RELEASE_API
    try:
        resp = requests.get(api_url, headers=RELEASE_HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise InstallerError(
            f"Failed to fetch SILC TUI release metadata from {api_url}: {exc}"
        ) from exc


def _choose_asset_for_platform(release: dict) -> dict:
    assets = release.get("assets") or []
    platform_keywords = _platform_keywords()
    arch_keywords = _architecture_keywords()

    for asset in assets:
        name = asset.get("name", "")
        if not name:
            continue
        lower = name.lower()
        if not any(keyword in lower for keyword in platform_keywords):
            continue
        if not any(keyword in lower for keyword in arch_keywords):
            continue
        return asset

    repo = os.getenv(REPO_ENV) or DEFAULT_GITHUB_REPO
    release_url = release.get("html_url") or f"https://github.com/{repo}/releases"
    raise InstallerError(
        f"No release asset for your platform was found in {release_url}."
    )


def _platform_keywords() -> set[str]:
    system = platform.system().lower()
    if "linux" in system:
        return {"linux", "unknown-linux"}
    if "darwin" in system or "mac" in system:
        return {"darwin", "macos", "apple-darwin"}
    if "windows" in system:
        return {"windows", "pc-windows-msvc"}
    raise InstallerError(
        f"SILC TUI is not supported on this platform ({platform.system()}); "
        "build it locally from the `tui_client` crate."
    )


def _architecture_keywords() -> set[str]:
    machine = platform.machine().lower()
    if "arm" in machine or "aarch64" in machine:
        return {"arm64", "aarch64"}
    if "x86_64" in machine or "amd64" in machine:
        return {"x86_64", "amd64"}
    return {machine}


def _download_and_extract_asset(
    asset: dict, *, progress: BinaryProgress | None = None
) -> Path:
    url = asset.get("browser_download_url")
    if not url:
        raise InstallerError("Release asset is missing a download URL.")

    with tempfile.TemporaryDirectory(prefix="silc-tui-") as temp_dir:
        download_path = Path(temp_dir) / asset.get("name", "asset")
        try:
            with requests.get(url, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                with open(download_path, "wb") as out_file:
                    for chunk in resp.iter_content(chunk_size=32_768):
                        if chunk:
                            out_file.write(chunk)
        except requests.RequestException as exc:
            raise InstallerError(f"Failed to download release asset: {exc}") from exc

        return _extract_binary_from_archive(
            download_path, Path(temp_dir), progress=progress
        )


def _extract_binary_from_archive(
    download_path: Path, work_dir: Path, *, progress: BinaryProgress | None
) -> Path:
    target_name = "silc-tui.exe" if sys.platform.startswith("win") else "silc-tui"

    if download_path.name.endswith(".zip"):
        with zipfile.ZipFile(download_path) as archive:
            matches = [
                name for name in archive.namelist() if Path(name).name == target_name
            ]
            if not matches:
                raise InstallerError(
                    f"{download_path.name} does not contain {target_name}."
                )
            member = matches[0]
            dest = work_dir / Path(member).name
            archive.extract(member, path=work_dir)
            result = dest
    elif download_path.name.endswith((".tar.gz", ".tgz", ".tar.xz", ".tar")):
        mode = "r:*"
        with tarfile.open(download_path, mode) as archive:
            member = next(
                (m for m in archive.getmembers() if Path(m.name).name == target_name),
                None,
            )
            if member is None:
                raise InstallerError(
                    f"{download_path.name} does not contain {target_name}."
                )
            archive.extract(member, path=work_dir)
            result = work_dir / member.name
    else:
        # Assume the asset is the binary itself.
        result = work_dir / target_name
        shutil.copy(download_path, result)

    if progress:
        progress(f"Extracted native TUI to {result}")
    return result


def _install_binary(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = destination.with_suffix(destination.suffix + ".tmp")
    if temp_dest.exists():
        temp_dest.unlink()

    shutil.copyfile(source, temp_dest)
    temp_dest.chmod(0o755)
    temp_dest.replace(destination)
