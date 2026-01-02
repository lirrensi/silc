import subprocess
import sys
from pathlib import Path


def build():
    project_root = Path(__file__).parent
    spec_file = project_root / "build.spec"

    if not spec_file.exists():
        print(f"Error: {spec_file} not found")
        sys.exit(1)

    # Build with PyInstaller
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        str(spec_file),
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode != 0:
        print(f"Build failed with exit code {result.returncode}")
        sys.exit(1)

    # Find the executable
    dist_dir = project_root / "dist"
    if sys.platform == "win32":
        exe_path = dist_dir / "silc.exe"
    else:
        exe_path = dist_dir / "silc"

    if exe_path.exists():
        print(f"\n✓ Build complete!")
        print(f"  Executable: {exe_path}")
    else:
        print("\n✗ Executable not found in dist/")
        sys.exit(1)


if __name__ == "__main__":
    build()
