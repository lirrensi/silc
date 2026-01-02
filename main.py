import sys
from pathlib import Path


def main():
    # Add parent directory to path for development (when not frozen)
    if getattr(sys, "frozen", False):
        # Running in PyInstaller bundle - paths are already set correctly
        pass
    else:
        # Development mode - add parent directory to import silc
        script_dir = Path(__file__).parent
        if str(script_dir) not in sys.path:
            sys.path.insert(0, str(script_dir))

    from silc.__main__ import main as silc_main

    silc_main()


if __name__ == "__main__":
    main()
