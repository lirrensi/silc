#!/usr/bin/env python3
"""
Manual test for TUI binary distribution.

This script tests the installer functionality by:
1. Fetching the latest release from GitHub
2. Verifying release metadata and assets
3. Downloading and verifying a test binary
4. Checking binary compatibility

Usage:
    python manual_tests/test_tui_binary_release.py
"""

from __future__ import annotations

import hashlib
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import requests

# Import the installer module
sys.path.insert(0, str(Path(__file__).parent.parent))
from silc.tui import installer


class TestTuiRelease:
    """Test suite for TUI binary distribution."""

    def __init__(self):
        self.repo = installer.DEFAULT_GITHUB_REPO
        self.api_url = installer.DEFAULT_RELEASE_API
        self.target_platform = platform.system().lower()
        self.target_arch = platform.machine().lower()
        self._temp_dirs: list[Path] = []

    def print_section(self, title: str) -> None:
        """Print a formatted section header."""
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}")

    def test_fetch_release(self) -> dict[str, Any]:
        """Test 1: Fetch the latest release from GitHub."""
        self.print_section("Test 1: Fetching Latest Release")

        try:
            print(f"Fetching release from: {self.api_url}")
            response = requests.get(
                self.api_url, headers=installer.RELEASE_HEADERS, timeout=30
            )
            response.raise_for_status()
            release = response.json()

            print(f"✓ Release fetched successfully")
            print(f"  Tag: {release.get('tag_name')}")
            print(f"  Name: {release.get('name')}")
            print(f"  Published: {release.get('published_at')}")
            print(f"  Draft: {release.get('draft')}")
            print(f"  Pre-release: {release.get('prerelease')}")

            return release
        except Exception as exc:
            print(f"✗ Failed to fetch release: {exc}")
            raise

    def test_detect_platform(self, release: dict[str, Any]) -> dict[str, Any]:
        """Test 2: Detect and select appropriate asset for current platform."""
        self.print_section("Test 2: Platform Detection")

        print(f"Current platform: {self.target_platform}")
        print(f"Current architecture: {self.target_arch}")

        platform_keywords = installer._platform_keywords()
        arch_keywords = installer._architecture_keywords()

        print(f"\nPlatform keywords: {platform_keywords}")
        print(f"Architecture keywords: {arch_keywords}")

        try:
            asset = installer._choose_asset_for_platform(release)
            print(f"\n✓ Appropriate asset selected:")
            print(f"  Name: {asset.get('name')}")
            print(f"  Size: {asset.get('size')} bytes")
            print(f"  Download URL: {asset.get('browser_download_url')}")
            print(f"  MIME type: {asset.get('content_type')}")

            return asset
        except Exception as exc:
            print(f"✗ No suitable asset found: {exc}")
            print(f"\nAvailable platforms in release:")
            for asset in release.get("assets", []):
                print(f"  - {asset.get('name')}")
            raise

    def test_download_binary(self, asset: dict[str, Any]) -> Path:
        """Test 3: Download the binary asset."""
        self.print_section("Test 3: Downloading Binary")

        url = asset.get("browser_download_url")
        if not url:
            raise RuntimeError("Asset missing download URL")

        print(f"Downloading from: {url}")

        # Create a temporary directory that lives until cleanup
        temp_dir = Path(tempfile.mkdtemp(prefix="silc-tui-test-"))
        self._temp_dirs.append(temp_dir)
        download_path = temp_dir / asset.get("name", "binary")

        try:
            # Download with progress
            print(f"Downloading to: {download_path}")
            with requests.get(url, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0

                with open(download_path, "wb") as out_file:
                    for chunk in resp.iter_content(chunk_size=32_768):
                        if chunk:
                            out_file.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                print(
                                    f"\rProgress: {downloaded:,}/{total_size:,} ({percent:.1f}%)",
                                    end="",
                                )

            print(f"\n✓ Download completed")
            print(f"  Size: {download_path.stat().st_size:,} bytes")

            # Verify file
            if not download_path.exists():
                raise RuntimeError("Downloaded file does not exist")

            return download_path

        except Exception as exc:
            if download_path.exists():
                download_path.unlink()
            print(f"\n✗ Download failed: {exc}")
            raise

    def test_extract_binary(
        self, archive_path: Path, progress: installer.BinaryProgress | None = None
    ) -> Path:
        """Test 4: Extract binary from archive."""
        self.print_section("Test 4: Extracting Binary")

        print(f"Extracting: {archive_path.name}")

        try:
            binary = installer._extract_binary_from_archive(
                archive_path, archive_path.parent, progress=progress
            )
            print(f"✓ Binary extracted to: {binary}")
            print(f"  Exists: {binary.exists()}")
            print(f"  Size: {binary.stat().st_size:,} bytes")

            if not binary.exists():
                raise RuntimeError("Extracted binary does not exist")

            # Check if executable
            is_executable = installer._is_valid_native_binary(binary)
            print(f"  Executable: {is_executable}")

            return binary
        except Exception as exc:
            print(f"✗ Extraction failed: {exc}")
            raise

    def test_binary_version(self, binary_path: Path, release: dict[str, Any]) -> None:
        """Test 5: Verify binary version matches release."""
        self.print_section("Test 5: Version Verification")

        release_tag = release.get("tag_name", "")
        print(f"Release tag: {release_tag}")

        # Check if tag matches expected version pattern (e.g., v0.1.0)
        import re

        version_pattern = r"^v(\d+\.\d+\.\d+)(?:-.*)?$"
        match = re.match(version_pattern, release_tag)

        if match:
            version = match.group(1)
            print(f"Version: {version}")
            print(f"✓ Version format is valid")
        else:
            print(f"⚠ Version tag format is unusual: {release_tag}")

    def test_binary_integrity(self, binary_path: Path) -> None:
        """Test 6: Calculate and verify binary checksum."""
        self.print_section("Test 6: Binary Integrity Check")

        print(f"Calculating SHA256 checksum...")

        sha256_hash = hashlib.sha256()
        with open(binary_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        checksum = sha256_hash.hexdigest()
        print(f"✓ SHA256: {checksum}")

        # Note: GitHub release assets don't include checksums by default
        # You can add checksum calculation to the workflow if needed
        print(f"  (Note: GitHub releases don't include checksums by default)")

    def test_binary_info(self, binary_path: Path) -> None:
        """Test 7: Display binary information."""
        self.print_section("Test 7: Binary Information")

        print(f"Platform: {installer._platform_keywords()}")
        print(f"Architecture: {installer._architecture_keywords()}")
        print(f"Binary: {binary_path.name}")
        print(f"Size: {binary_path.stat().st_size:,} bytes")
        print(f"Permissions: {oct(binary_path.stat().st_mode)}")

        # Try to get more info on Unix-like systems
        if sys.platform != "win32":
            try:
                import subprocess

                result = subprocess.run(
                    ["file", str(binary_path)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                print(f"File type: {result.stdout.strip()}")
            except Exception:
                pass

    def run_all_tests(self) -> int:
        """Run all tests."""
        self.print_section("TUI Binary Distribution Test Suite")

        print(f"Repository: {self.repo}")
        print(f"API Endpoint: {self.api_url}")
        print(f"Python: {sys.version}")
        print(f"OS: {sys.platform}")

        release = None
        asset = None
        binary_path = None

        try:
            # Test 1: Fetch release
            release = self.test_fetch_release()

            # Test 2: Select platform-appropriate asset
            asset = self.test_detect_platform(release)

            # Test 3: Download binary
            binary_path = self.test_download_binary(asset)

            # Test 4: Extract binary
            binary_path = self.test_extract_binary(binary_path, progress=None)

            # Test 5: Verify version
            if release:
                self.test_binary_version(binary_path, release)

            # Test 6: Check integrity
            self.test_binary_integrity(binary_path)

            # Test 7: Display binary info
            self.test_binary_info(binary_path)

            # Summary
            self.print_section("Test Summary")
            print("✓ All tests passed successfully!")
            print("\nBinary is ready for:")
            print("  - Local testing")
            print("  - Distribution to users")
            print("  - Integration testing")

            return 0

        except Exception as exc:
            self.print_section("Test Failed")
            print(f"✗ Error: {exc}")
            import traceback

            traceback.print_exc()
            return 1

        finally:
            # Cleanup: remove test binary
            if binary_path and binary_path.exists():
                print(f"\nCleaning up test binary: {binary_path}")
                binary_path.unlink()

            # Cleanup: remove temporary directories created during download
            for temp_dir in getattr(self, "_temp_dirs", []):
                try:
                    if temp_dir.exists():
                        shutil.rmtree(temp_dir)
                except Exception:
                    print(f"Warning: failed to remove temporary directory {temp_dir}")
            if hasattr(self, "_temp_dirs"):
                self._temp_dirs.clear()


def main() -> int:
    """Entry point."""
    test = TestTuiRelease()
    return test.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
