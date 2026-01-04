#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
TUI_DIR="$ROOT_DIR/tui_client"
DIST_DIR="$TUI_DIR/dist"

mkdir -p "$DIST_DIR"

declare -a TARGETS=(
    "x86_64-unknown-linux-gnu"
    "x86_64-pc-windows-gnu"
)

cd "$TUI_DIR"

for target in "${TARGETS[@]}"; do
    rustup target add "$target" >/dev/null
done

for target in "${TARGETS[@]}"; do
    echo "Building silc-tui for target: $target"
    cargo build --release --target "$target"

    if [ "$target" = "x86_64-unknown-linux-gnu" ]; then
        src="$TUI_DIR/target/$target/release/silc-tui"
        dst="$DIST_DIR/silc-tui-linux"
    else
        src="$TUI_DIR/target/$target/release/silc-tui.exe"
        dst="$DIST_DIR/silc-tui-windows.exe"
    fi

    if [ ! -f "$src" ]; then
        echo >&2 "expected binary at $src, build failed?"
        exit 1
    fi

    cp -f "$src" "$dst"
    echo "Copied $src -> $dst"
done
