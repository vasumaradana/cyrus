#!/usr/bin/env bash
# Cyrus Brain — Install Script (macOS / Linux)
# Run: bash install-brain.sh
#
# Installs Cyrus Brain + Hook + VS Code Companion Extension.
# Brain runs on the machine with VS Code + Claude Code.

set -e

INSTALL_DIR="${HOME}/.cyrus/brain"

while [[ $# -gt 0 ]]; do
    case $1 in
        --install-dir) INSTALL_DIR="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo ""
echo "=== Cyrus Brain Installer ==="

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 1. Create install directory
echo ""
echo "[1/5] Creating install directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# 2. Copy brain files
echo "[2/5] Copying brain files..."
cp "$SCRIPT_DIR/cyrus_brain.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/cyrus_hook.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/requirements-brain.txt" "$INSTALL_DIR/"

# Copy pre-built companion extension
VSIX_FILE=$(ls "$SCRIPT_DIR"/cyrus-companion/*.vsix 2>/dev/null | head -1)
if [ -n "$VSIX_FILE" ]; then
    cp "$VSIX_FILE" "$INSTALL_DIR/"
    echo "       Companion extension: $(basename "$VSIX_FILE")"
else
    echo "       WARNING: No .vsix found. Build it first: cd cyrus-companion && npm run compile && npx @vscode/vsce package --no-dependencies"
fi

# 3. Create virtual environment and install dependencies
echo "[3/5] Setting up Python virtual environment..."
VENV_DIR="$INSTALL_DIR/venv"
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements-brain.txt" -q

# 4. Install VS Code companion extension
echo "[4/5] Installing VS Code companion extension..."
VSIX_DEST=$(ls "$INSTALL_DIR"/*.vsix 2>/dev/null | head -1)
if [ -n "$VSIX_DEST" ]; then
    code --install-extension "$VSIX_DEST" --force 2>/dev/null || true
    echo "       Extension installed. Restart VS Code to activate."
else
    echo "       Skipped (no .vsix file found)."
fi

# 5. Configure Claude Code hooks
echo "[5/5] Configuring Claude Code hooks..."
CLAUDE_DIR="$HOME/.claude"
mkdir -p "$CLAUDE_DIR"
HOOK_PYTHON="$VENV_DIR/bin/python"
HOOK_SCRIPT="$INSTALL_DIR/cyrus_hook.py"

SETTINGS_FILE="$CLAUDE_DIR/settings.json"
if [ -f "$SETTINGS_FILE" ]; then
    cp "$SETTINGS_FILE" "${SETTINGS_FILE}.bak"
    echo "       Backed up existing settings to: ${SETTINGS_FILE}.bak"
fi

cat > "$SETTINGS_FILE" << SETTINGS
{
  "hooks": {
    "Stop": [{"hooks": [{"type": "command", "command": "$HOOK_PYTHON $HOOK_SCRIPT", "timeout": 5}]}],
    "PreToolUse": [{"hooks": [{"type": "command", "command": "$HOOK_PYTHON $HOOK_SCRIPT", "timeout": 5}]}],
    "PostToolUse": [{"hooks": [{"type": "command", "command": "$HOOK_PYTHON $HOOK_SCRIPT", "timeout": 5}]}],
    "Notification": [{"hooks": [{"type": "command", "command": "$HOOK_PYTHON $HOOK_SCRIPT", "timeout": 5}]}],
    "PreCompact": [{"hooks": [{"type": "command", "command": "$HOOK_PYTHON $HOOK_SCRIPT", "timeout": 5}]}]
  }
}
SETTINGS

# Create launch script
cat > "$INSTALL_DIR/start-brain.sh" << LAUNCH
#!/usr/bin/env bash
echo "Starting Cyrus Brain"
cd "$INSTALL_DIR"
"$VENV_DIR/bin/python" cyrus_brain.py "\$@"
LAUNCH
chmod +x "$INSTALL_DIR/start-brain.sh"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Brain installed to: $INSTALL_DIR"
echo ""
echo "Next steps:"
echo "  1. Restart VS Code (to activate companion extension)"
echo "  2. Run: $INSTALL_DIR/start-brain.sh"
echo "  3. On the voice machine, run install-voice and point it at this machine's IP"
echo ""
