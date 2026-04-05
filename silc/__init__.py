"""Top-level package for the SILC shared shell project."""


def main() -> None:
    from .__main__ import main as _main

    _main()


__all__ = ["main"]
