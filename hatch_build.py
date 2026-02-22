"""Build hook to compile the manager web UI before packaging.

Automatically detects and uses whichever package manager is available:
pnpm → npm → yarn
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


# Package managers to try, in order of preference
PACKAGE_MANAGERS: List[Tuple[List[str], str]] = [
    (["pnpm"], "pnpm"),
    (["npm"], "npm"),
    (["yarn"], "yarn"),
]


def find_package_manager() -> Optional[Tuple[List[str], str]]:
    """Find an available package manager.

    Returns:
        Tuple of (command_list, name) for the first available package manager,
        or None if none found.
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
            return (cmd, f"{name} v{version}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return None


class WebUIBuildHook(BuildHookInterface):
    """Build hook that compiles the Vue.js manager UI before packaging."""

    PLUGIN_NAME = "webui-build"

    def initialize(self, version: str, build_data: dict) -> None:
        """Build the manager web UI before the wheel is packaged."""
        root = Path(self.root)
        manager_ui_dir = root / "manager_web_ui"
        static_dir = root / "static" / "manager"

        # Skip if manager_web_ui doesn't exist (e.g., in CI for pure Python builds)
        if not manager_ui_dir.exists():
            self.app.display_warning("manager_web_ui/ not found, skipping web UI build")
            return

        # Skip if already built (for editable installs)
        if static_dir.exists() and any(static_dir.glob("assets/*.js")):
            self.app.display_info(
                f"[INFO] Web UI already built in {static_dir.relative_to(root)}, skipping rebuild"
            )
            return

        # Find available package manager
        pkg_mgr = find_package_manager()
        if pkg_mgr is None:
            self.app.display_warning(
                "No package manager found (tried: pnpm, npm, yarn). "
                "Install one to build the web UI, or build manually and skip this hook."
            )
            return

        cmd, version_info = pkg_mgr
        self.app.display_info(f"[INFO] Using {version_info}")
        self.app.display_info("[BUILD] Building manager web UI...")

        try:
            # On Windows, use shell=True for .cmd/.bat files
            use_shell = sys.platform == "win32"
            subprocess.run(
                cmd + ["build"],
                cwd=manager_ui_dir,
                check=True,
                capture_output=False,
                shell=use_shell,
            )
            self.app.display_info(
                f"[SUCCESS] Web UI built successfully to {static_dir.relative_to(root)}"
            )
        except subprocess.CalledProcessError as e:
            self.app.display_error(f"Failed to build web UI: {e}")
            sys.exit(1)
