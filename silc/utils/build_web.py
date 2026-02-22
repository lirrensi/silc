#!/usr/bin/env python3
"""Build the manager web UI from source.

This script compiles the Vue.js manager UI and outputs it to static/manager/.
Run this before building the Python package if you've made changes to the web UI.

Automatically detects and uses whichever package manager is available:
pnpm → npm → yarn

Usage:
    python -m silc.utils.build_web
    # or
    silc-build-web
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Optional


# Package managers to try, in order of preference
PACKAGE_MANAGERS = [
    (["pnpm"], "pnpm"),
    (["npm"], "npm"),
    (["yarn"], "yarn"),
]


def find_package_manager() -> Optional[List[str]]:
    """Find an available package manager.

    Returns:
        Command list for the first available package manager, or None if none found.
    """
    import platform

    # On Windows, we may need shell=True for .cmd/.bat files
    use_shell = platform.system() == "Windows"

    for cmd, name in PACKAGE_MANAGERS:
        try:
            result = subprocess.run(
                cmd + ["--version"],
                check=True,
                capture_output=True,
                text=True,
                shell=use_shell,
            )
            version = result.stdout.strip()
            print(f"[INFO] Found {name} v{version}")
            return cmd
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return None


def build_web_ui() -> int:
    """Build the manager web UI.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    root = Path(__file__).parent.parent.parent
    manager_ui_dir = root / "manager_web_ui"
    static_dir = root / "static" / "manager"

    if not manager_ui_dir.exists():
        print(f"[ERROR] manager_web_ui/ not found at {manager_ui_dir}")
        return 1

    if not (manager_ui_dir / "package.json").exists():
        print(f"[ERROR] package.json not found in {manager_ui_dir}")
        return 1

    # Find available package manager
    pkg_mgr = find_package_manager()
    if pkg_mgr is None:
        print("[ERROR] No package manager found. Please install one of:")
        print("   pnpm: npm install -g pnpm")
        print("   npm:  https://nodejs.org/")
        print("   yarn: npm install -g yarn")
        return 1

    pkg_mgr_name = pkg_mgr[0]
    print(f"[BUILD] Building manager web UI using {pkg_mgr_name}...")

    # Build command
    build_cmd = pkg_mgr + ["build"]

    try:
        # On Windows, use shell=True for .cmd/.bat files
        use_shell = sys.platform == "win32"
        subprocess.run(
            build_cmd,
            cwd=manager_ui_dir,
            check=True,
            capture_output=False,
            shell=use_shell,
        )

        # Verify build output
        if not static_dir.exists():
            print(f"[ERROR] Build succeeded but {static_dir} was not created")
            return 1

        index_html = static_dir / "index.html"
        if not index_html.exists():
            print(f"[ERROR] Build succeeded but {index_html} was not found")
            return 1

        print(f"[SUCCESS] Web UI built successfully!")
        print(f"   Output: {static_dir.relative_to(root)}")
        print(f"   Files: {sum(1 for _ in static_dir.rglob('*') if _.is_file())} files")
        return 0

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Build failed with exit code {e.returncode}")
        return 1
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        return 1


def main() -> None:
    """Entry point for silc-build-web command."""
    sys.exit(build_web_ui())


if __name__ == "__main__":
    main()
