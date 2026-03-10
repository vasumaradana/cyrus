#!/usr/bin/env bash
# Cyrus Voice — Install Script (macOS / Linux)
# Run: bash install-voice.sh [--brain-host <ip>] [--brain-port <port>]
#
# Installs Cyrus Voice service on this machine.
# Voice can run locally (same machine as Brain) or remotely.

set -e

INSTALL_DIR="${HOME}/.cyrus/voice"
BRAIN_HOST="localhost"
BRAIN_PORT=8766

while [[ $# -gt 0 ]]; do
    case $1 in
        --install-dir) INSTALL_DIR="$2"; shift 2 ;;
        --brain-host)  BRAIN_HOST="$2";  shift 2 ;;
        --brain-port)  BRAIN_PORT="$2";  shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo ""
echo "=== Cyrus Voice Installer ==="

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 1. Create install directory
echo ""
echo "[1/4] Creating install directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# 2. Copy voice files
echo "[2/4] Copying voice files..."
cp "$SCRIPT_DIR/cyrus_voice.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/requirements-voice.txt" "$INSTALL_DIR/"

# Copy or download Kokoro TTS model files
HF_BASE="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
if [ -f "$SCRIPT_DIR/kokoro-v1.0.onnx" ]; then
    echo "       Copying Kokoro TTS model..."
    cp "$SCRIPT_DIR/kokoro-v1.0.onnx" "$INSTALL_DIR/"
elif [ ! -f "$INSTALL_DIR/kokoro-v1.0.onnx" ]; then
    echo "       Downloading Kokoro TTS model (~370 MB)..."
    curl -L -o "$INSTALL_DIR/kokoro-v1.0.onnx" "$HF_BASE/kokoro-v1.0.onnx"
fi
if [ -f "$SCRIPT_DIR/voices-v1.0.bin" ]; then
    cp "$SCRIPT_DIR/voices-v1.0.bin" "$INSTALL_DIR/"
elif [ ! -f "$INSTALL_DIR/voices-v1.0.bin" ]; then
    echo "       Downloading Kokoro voices (~4 MB)..."
    curl -L -o "$INSTALL_DIR/voices-v1.0.bin" "$HF_BASE/voices-v1.0.bin"
fi

# 3. Create virtual environment and install dependencies
echo "[3/4] Setting up Python virtual environment..."
VENV_DIR="$INSTALL_DIR/venv"
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements-voice.txt" -q

# 4. Create launch script
echo "[4/4] Creating launch script..."
cat > "$INSTALL_DIR/start-voice.sh" << LAUNCH
#!/usr/bin/env bash
echo "Starting Cyrus Voice (connecting to Brain at $BRAIN_HOST:$BRAIN_PORT)"
cd "$INSTALL_DIR"
"$VENV_DIR/bin/python" cyrus_voice.py --host "$BRAIN_HOST" --port "$BRAIN_PORT" "\$@"
LAUNCH
chmod +x "$INSTALL_DIR/start-voice.sh"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Voice installed to: $INSTALL_DIR"
echo ""
echo "To start Cyrus Voice:"
echo "  $INSTALL_DIR/start-voice.sh"
echo ""
echo "To connect to a remote Brain:"
echo "  $INSTALL_DIR/start-voice.sh --host <brain-ip>"
echo ""
