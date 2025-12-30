import pathlib, zipapp, importlib.metadata, shutil, tempfile, sys


def main() -> None:
    root = pathlib.Path(__file__).parent
    out_dir = root / "dist"
    out_dir.mkdir(exist_ok=True)
    target = out_dir / "silc.pyz"
    # create temporary build dir
    with tempfile.TemporaryDirectory() as tmpdir:
        build_dir = pathlib.Path(tmpdir)
        # copy the silc package
        shutil.copytree(root / "silc", build_dir / "silc")
        # ensure entry point
        shutil.copy2(root / "silc" / "__main__.py", build_dir / "__main__.py")
        # include site-packages from current Python environment
        import sysconfig

        site_pkg = pathlib.Path(sysconfig.get_paths()["purelib"])
        for item in site_pkg.iterdir():
            dest = build_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        zipapp.create_archive(
            build_dir,
            target=target,
            interpreter=None,
        )
    print(f"Created {target}")


if __name__ == "__main__":
    main()
