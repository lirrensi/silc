#!/usr/bin/env sh

# FILE: scripts/install-source.sh
# PURPOSE: Build a repo-like source tree, populate tui_client/dist, and install SILC from an editable checkout.
# OWNS: POSIX source-bootstrap install flow for local checkout and downloaded source tarball modes.
# EXPORTS: none - executable bootstrap script.
# DOCS: agent_chat/plan_zip_distribution_2026-04-10.md, docs/arch_tui.md, README.md

set -eu

REPO="${SILC_REPO:-lirrensi/silc}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LOCAL_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
INSTALL_ROOT="${SILC_INSTALL_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/silc/source-installs}"

resolve_tui_asset_name() {
    os=$(uname -s | tr '[:upper:]' '[:lower:]')
    arch=$(uname -m | tr '[:upper:]' '[:lower:]')

    case "$os" in
        linux)
            case "$arch" in
                x86_64|amd64) printf '%s\n' 'silc-tui-linux-x86_64' ;;
                *) printf 'Unsupported Linux architecture: %s\n' "$arch" >&2; exit 1 ;;
            esac
            ;;
        darwin)
            case "$arch" in
                x86_64|amd64) printf '%s\n' 'silc-tui-darwin-x86_64' ;;
                arm64|aarch64) printf '%s\n' 'silc-tui-darwin-aarch64' ;;
                *) printf 'Unsupported macOS architecture: %s\n' "$arch" >&2; exit 1 ;;
            esac
            ;;
        *)
            printf 'Unsupported platform: %s\n' "$os" >&2
            exit 1
            ;;
    esac
}

if [ -f "$LOCAL_ROOT/pyproject.toml" ] && [ -d "$LOCAL_ROOT/silc" ] && [ -d "$LOCAL_ROOT/manager_web_ui" ]; then
    SOURCE_TREE="$LOCAL_ROOT"
else
    STAMP=$(python -c 'import datetime; print(datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S"))')
    TARGET_ROOT="$INSTALL_ROOT/$STAMP"
    ARCHIVE_PATH="$TARGET_ROOT/source.tar.gz"
    EXTRACT_ROOT="$TARGET_ROOT/unpacked"
    mkdir -p "$EXTRACT_ROOT"
    curl -fsSL "https://api.github.com/repos/$REPO/tarball" -o "$ARCHIVE_PATH"
    SOURCE_TREE="$(python - "$ARCHIVE_PATH" "$EXTRACT_ROOT" <<'PY'
import sys
import tarfile
from pathlib import Path

archive_path = Path(sys.argv[1])
extract_root = Path(sys.argv[2])

with tarfile.open(archive_path, 'r:gz') as archive:
    archive.extractall(extract_root)

entries = [path.resolve() for path in extract_root.iterdir() if path.is_dir()]
if len(entries) != 1:
    raise SystemExit(f'Expected one extracted source directory, found {len(entries)}')

print(entries[0])
PY
)"
fi

(
    cd "$SOURCE_TREE"
    python -m silc.utils.build_web
)

TUI_ASSET_NAME=$(resolve_tui_asset_name)
TUI_DIST_DIR="$SOURCE_TREE/tui_client/dist"
mkdir -p "$TUI_DIST_DIR"
curl -fsSL "https://github.com/$REPO/releases/latest/download/$TUI_ASSET_NAME" -o "$TUI_DIST_DIR/silc-tui"
chmod +x "$TUI_DIST_DIR/silc-tui"

uv tool install --force --editable "$SOURCE_TREE"

printf 'Source tree: %s\n' "$SOURCE_TREE"
printf 'Native TUI path: %s\n' "$TUI_DIST_DIR/silc-tui"
