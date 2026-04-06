#!/usr/bin/env sh

set -eu

REPO="${SILC_REPO:-lirrensi/silc}"
INSTALL_DIR="${SILC_INSTALL_DIR:-$HOME/.local/bin}"
mkdir -p "$INSTALL_DIR"

OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

case "$OS" in
  linux)
    case "$ARCH" in
      x86_64|amd64) ASSET="silc-linux-x86_64" ;;
      *) echo "Unsupported Linux architecture: $ARCH" >&2; exit 1 ;;
    esac
    ;;
  darwin)
    case "$ARCH" in
      x86_64|amd64) ASSET="silc-darwin-x86_64" ;;
      arm64|aarch64) ASSET="silc-darwin-aarch64" ;;
      *) echo "Unsupported macOS architecture: $ARCH" >&2; exit 1 ;;
    esac
    ;;
  *)
    echo "Unsupported platform: $OS" >&2
    exit 1
    ;;
esac

URL="https://github.com/$REPO/releases/latest/download/$ASSET"
TARGET="$INSTALL_DIR/silc"
TMP_FILE="${TARGET}.tmp"

curl -fsSL "$URL" -o "$TMP_FILE"
chmod +x "$TMP_FILE"
mv "$TMP_FILE" "$TARGET"

echo "Installed SILC to $TARGET"
