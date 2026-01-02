# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

# Get the project root directory
project_root = Path(SPECPATH)

# Entry point - use the launcher script
entry_point = project_root / "main.py"

# Collect data files (static HTML)
static_dir = project_root / "static"
datas = [(str(static_dir), "static")]

# Analysis
a = Analysis(
    [str(entry_point)],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "fastapi",
        "uvicorn",
        "uvicorn.protocols.http",
        "uvicorn.protocols.websockets",
        "uvicorn.lifespan.on",
        "uvicorn.loops.auto",
        "uvicorn.loops.uvloop",
        "uvicorn.loops.asyncio",
        "pydantic",
        "click",
        "textual",
        "psutil",
        "pyte",
        "requests",
        "pywinpty" if sys.platform == "win32" else "pty",
        "silc",
        "silc.__main__",
        "silc.api",
        "silc.api.models",
        "silc.api.server",
        "silc.core",
        "silc.core.session",
        "silc.core.pty_manager",
        "silc.core.raw_buffer",
        "silc.core.cleaner",
        "silc.daemon",
        "silc.daemon.manager",
        "silc.daemon.registry",
        "silc.daemon.pidfile",
        "silc.tui",
        "silc.tui.app",
        "silc.utils",
        "silc.utils.shell_detect",
        "silc.utils.ports",
        "silc.utils.persistence",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Remove tests and development dependencies
excluded_packages = [
    "pytest",
    "pytest_asyncio",
]
for pkg in excluded_packages:
    a.excludes.append(pkg)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="silc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
