#!/usr/bin/env bash
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
TUI_DIR="$ROOT_DIR/tui_client"
DIST_DIR="$TUI_DIR/dist"

mkdir -p "$DIST_DIR"

TARGET=""
OUTPUT_NAME=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --target)
            TARGET="${2:-}"
            shift 2
            ;;
        --output-name)
            OUTPUT_NAME="${2:-}"
            shift 2
            ;;
        *)
            echo >&2 "unknown argument: $1"
            exit 1
            ;;
    esac
done

if [ -z "$TARGET" ]; then
    case "$(uname -s | tr '[:upper:]' '[:lower:]')" in
        linux)
            TARGET="x86_64-unknown-linux-gnu"
            OUTPUT_NAME="${OUTPUT_NAME:-silc-tui-linux-x86_64}"
            ;;
        darwin)
            case "$(uname -m | tr '[:upper:]' '[:lower:]')" in
                arm64|aarch64)
                    TARGET="aarch64-apple-darwin"
                    OUTPUT_NAME="${OUTPUT_NAME:-silc-tui-darwin-aarch64}"
                    ;;
                x86_64|amd64)
                    TARGET="x86_64-apple-darwin"
                    OUTPUT_NAME="${OUTPUT_NAME:-silc-tui-darwin-x86_64}"
                    ;;
                *)
                    echo >&2 "unsupported macOS architecture"
                    exit 1
                    ;;
            esac
            ;;
        mingw*|msys*|cygwin*|windows_nt)
            TARGET="x86_64-pc-windows-msvc"
            OUTPUT_NAME="${OUTPUT_NAME:-silc-tui-windows-x86_64.exe}"
            ;;
        *)
            echo >&2 "unsupported platform"
            exit 1
            ;;
    esac
fi

if [ -z "$OUTPUT_NAME" ]; then
    case "$TARGET" in
        *windows*) OUTPUT_NAME="silc-tui-windows-x86_64.exe" ;;
        *apple-darwin)
            case "$TARGET" in
                aarch64-apple-darwin) OUTPUT_NAME="silc-tui-darwin-aarch64" ;;
                *) OUTPUT_NAME="silc-tui-darwin-x86_64" ;;
            esac
            ;;
        *) OUTPUT_NAME="silc-tui-linux-x86_64" ;;
    esac
fi

if ! command -v cargo >/dev/null 2>&1; then
    echo >&2 "cargo not found; install the Rust toolchain first"
    exit 1
fi

echo "Building native TUI for target: $TARGET"

if command -v rustup >/dev/null 2>&1; then
    rustup target add "$TARGET" >/dev/null
else
    echo >&2 "rustup not found; assuming target $TARGET is already installed"
fi
cargo build --release --target "$TARGET" --manifest-path "$TUI_DIR/Cargo.toml"

case "$TARGET" in
    *windows*) src="$TUI_DIR/target/$TARGET/release/silc-tui.exe" ;;
    *) src="$TUI_DIR/target/$TARGET/release/silc-tui" ;;
esac

if [ ! -f "$src" ]; then
    echo >&2 "expected binary at $src, build failed?"
    exit 1
fi

dst="$DIST_DIR/$OUTPUT_NAME"
cp -f "$src" "$dst"
echo "Copied $src -> $dst"
