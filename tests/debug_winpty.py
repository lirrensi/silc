import time

from winpty import PtyProcess


def main():
    pty = PtyProcess.spawn("cmd.exe")
    time.sleep(0.5)
    for _ in range(5):
        try:
            chunk = pty.read(4096)
        except Exception as exc:
            print("read ERR", type(exc), exc)
            break
        print("first chunk repr", repr(chunk))
        if "Microsoft" in chunk:
            break
    pty.write("echo hi\r\n")
    time.sleep(0.5)
    for i in range(6):
        try:
            chunk = pty.read(4096)
        except Exception as exc:
            print("read2 ERR", type(exc), exc)
            break
        print("later chunk repr", repr(chunk))
        time.sleep(0.1)
    pty.close()


def hasattr(p):
    pass


if __name__ == "__main__":
    main()
