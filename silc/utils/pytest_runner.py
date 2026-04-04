"""Run pytest test nodes one at a time with logging and timeouts."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from typing import Sequence

DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class TestRunResult:
    nodeid: str
    returncode: int | None
    timed_out: bool


def _collect_test_nodeids(pytest_args: Sequence[str]) -> list[str]:
    cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q", *pytest_args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    nodeids: list[str] = []
    for line in result.stdout.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith(("=", "-", "<")):
            continue
        if "::" not in candidate:
            continue
        nodeids.append(candidate)

    if result.returncode not in {0, 5} and not nodeids:
        raise RuntimeError(
            result.stderr.strip() or result.stdout.strip() or "pytest collection failed"
        )

    return list(dict.fromkeys(nodeids))


def _run_test_node(nodeid: str, timeout_seconds: float) -> TestRunResult:
    print(f"\n=== RUN {nodeid}", flush=True)
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-s",
        "--disable-warnings",
        nodeid,
    ]

    proc = subprocess.Popen(cmd)
    try:
        returncode = proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        print(f"=== SKIP {nodeid} (>{timeout_seconds:.0f}s timeout)", flush=True)
        return TestRunResult(nodeid=nodeid, returncode=None, timed_out=True)

    if returncode == 0:
        print(f"=== PASS {nodeid}", flush=True)
    else:
        print(f"=== FAIL {nodeid} (exit {returncode})", flush=True)

    return TestRunResult(nodeid=nodeid, returncode=returncode, timed_out=False)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="silc-test",
        description="Run pytest tests one-by-one with logging and timeouts.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["tests"],
        help="Pytest paths or selectors to collect.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Per-test timeout in seconds (default: 30).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        nodeids = _collect_test_nodeids(args.paths)
    except RuntimeError as exc:
        print(f"Collection failed: {exc}", file=sys.stderr, flush=True)
        return 2

    if not nodeids:
        print("No tests collected.", flush=True)
        return 0

    passed = 0
    failed = 0
    skipped = 0

    for nodeid in nodeids:
        result = _run_test_node(nodeid, args.timeout)
        if result.timed_out:
            skipped += 1
        elif result.returncode == 0:
            passed += 1
        else:
            failed += 1

    print(
        f"\nSummary: {passed} passed, {failed} failed, {skipped} skipped by timeout",
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
