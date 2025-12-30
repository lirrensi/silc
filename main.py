import sys


def main():
    if len(sys.argv) > 1:
        from silc.__main__ import main as silc_main

        silc_main()
    else:
        print("Usage: python main.py <silc command>")


if __name__ == "__main__":
    main()
