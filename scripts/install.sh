#!/usr/bin/env sh

# FILE: scripts/install.sh
# PURPOSE: Download the latest repo-mirror release zip and install SILC from an editable unpacked tree.
# OWNS: POSIX zip-bootstrap install flow for GitHub-hosted release assets.
# EXPORTS: none - executable bootstrap script.
# DOCS: agent_chat/plan_zip_distribution_2026-04-10.md, docs/arch_tui.md, README.md

set -eu

REPO="${SILC_REPO:-lirrensi/silc}"
INSTALL_ROOT="${SILC_INSTALL_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/silc/releases}"

resolve_asset_name() {
    os=$(uname -s | tr '[:upper:]' '[:lower:]')
    arch=$(uname -m | tr '[:upper:]' '[:lower:]')

    case "$os" in
        linux)
            case "$arch" in
                x86_64|amd64) printf '%s\n' 'silc-linux-x86_64.zip' ;;
                *) printf 'Unsupported Linux architecture: %s\n' "$arch" >&2; exit 1 ;;
            esac
            ;;
        darwin)
            case "$arch" in
                x86_64|amd64) printf '%s\n' 'silc-darwin-x86_64.zip' ;;
                arm64|aarch64) printf '%s\n' 'silc-darwin-aarch64.zip' ;;
                *) printf 'Unsupported macOS architecture: %s\n' "$arch" >&2; exit 1 ;;
            esac
            ;;
        *)
            printf 'Unsupported platform: %s\n' "$os" >&2
            exit 1
            ;;
    esac
}

ASSET_NAME=$(resolve_asset_name)
STAMP=$(python -c 'import datetime; print(datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S"))')
TARGET_ROOT="$INSTALL_ROOT/$STAMP"
ARCHIVE_PATH="$TARGET_ROOT/$ASSET_NAME"
EXTRACT_ROOT="$TARGET_ROOT/unpacked"

mkdir -p "$EXTRACT_ROOT"
curl -fsSL "https://github.com/$REPO/releases/latest/download/$ASSET_NAME" -o "$ARCHIVE_PATH"

REPO_TREE="$(python - "$ARCHIVE_PATH" "$EXTRACT_ROOT" <<'PY'
import sys
import zipfile
from pathlib import Path

archive_path = Path(sys.argv[1])
extract_root = Path(sys.argv[2])

with zipfile.ZipFile(archive_path) as archive:
    archive.extractall(extract_root)

candidates = []
for pyproject in extract_root.rglob('pyproject.toml'):
    parent = pyproject.parent
    if (parent / 'silc').is_dir() and (parent / 'manager_web_ui').is_dir():
        candidates.append(parent.resolve())

if len(candidates) != 1:
    raise SystemExit(f'Expected one unpacked repo tree, found {len(candidates)}')

print(candidates[0])
PY
)"

uv tool install --force --editable "$REPO_TREE"

printf 'Unpacked SILC tree: %s\n' "$REPO_TREE"
printf 'Native TUI path: %s\n' "$REPO_TREE/tui_client/dist/silc-tui"
