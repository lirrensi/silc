#!/bin/bash

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$PROJECT_ROOT/dist"
INSTALL_DIR="$HOME/silc"

echo "SILC Installer for Unix/Linux/macOS"
echo "====================================="

# Detect platform
if [[ "$OSTYPE" == "darwin"* ]]; then
    PLATFORM="macos"
    EXE_NAME="silc"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    PLATFORM="linux"
    EXE_NAME="silc"
else
    echo "Unknown platform: $OSTYPE"
    exit 1
fi

EXE_PATH="$DIST_DIR/$EXE_NAME"
TARGET_PATH="$INSTALL_DIR/$EXE_NAME"

# Check if executable exists
if [ ! -f "$EXE_PATH" ]; then
    echo "Executable not found in dist/, building first..."
    python3 "$PROJECT_ROOT/build.py" || python "$PROJECT_ROOT/build.py"
    if [ $? -ne 0 ]; then
        echo "Build failed!"
        exit 1
    fi
fi

# Create install directory
if [ ! -d "$INSTALL_DIR" ]; then
    echo "Creating install directory: $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
fi

# Copy executable
echo "Copying executable to $INSTALL_DIR"
cp -f "$EXE_PATH" "$TARGET_PATH"
chmod +x "$TARGET_PATH"

# Add to PATH
echo ""
echo "Adding $INSTALL_DIR to PATH..."

# Detect shell
if [ -n "$ZSH_VERSION" ] || [ -n "$ZSH_NAME" ]; then
    SHELL_CONFIG="$HOME/.zshrc"
    PROFILE_CMD="export PATH=\"$INSTALL_DIR:\$PATH\""
elif [ -n "$BASH_VERSION" ]; then
    if [ -f "$HOME/.bashrc" ]; then
        SHELL_CONFIG="$HOME/.bashrc"
    elif [ -f "$HOME/.bash_profile" ]; then
        SHELL_CONFIG="$HOME/.bash_profile"
    else
        SHELL_CONFIG="$HOME/.bashrc"
    fi
    PROFILE_CMD="export PATH=\"$INSTALL_DIR:\$PATH\""
else
    # Fallback to profile
    SHELL_CONFIG="$HOME/.profile"
    PROFILE_CMD="export PATH=\"$INSTALL_DIR:\$PATH\""
fi

# Check if already in config file
if [ -f "$SHELL_CONFIG" ] && grep -q "$INSTALL_DIR" "$SHELL_CONFIG"; then
    echo "Already in PATH in $SHELL_CONFIG, skipping."
else
    echo "" >> "$SHELL_CONFIG"
    echo "# SILC" >> "$SHELL_CONFIG"
    echo "$PROFILE_CMD" >> "$SHELL_CONFIG"
    echo "Added to $SHELL_CONFIG"
    echo ""
    echo "IMPORTANT: Please run 'source $SHELL_CONFIG' or restart your terminal."
fi

# Also add to .profile for compatibility
if [ -f "$HOME/.profile" ] && ! grep -q "$INSTALL_DIR" "$HOME/.profile"; then
    echo "" >> "$HOME/.profile"
    echo "# SILC" >> "$HOME/.profile"
    echo "$PROFILE_CMD" >> "$HOME/.profile"
fi

echo ""
echo "=========================================="
echo "Installation complete!"
echo "=========================================="
echo "Executable location: $TARGET_PATH"
echo "Installation directory: $INSTALL_DIR"
echo ""
echo "Try running: $TARGET_PATH --help"
echo ""
