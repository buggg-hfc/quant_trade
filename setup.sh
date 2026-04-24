#!/usr/bin/env bash
set -e

echo "=== quant_trade setup ==="

# 1. Check Python >= 3.11
PY=$(python3 --version 2>&1 | awk '{print $2}')
MAJOR=$(echo "$PY" | cut -d. -f1)
MINOR=$(echo "$PY" | cut -d. -f2)
if [ "$MAJOR" -lt 3 ] || [ "$MAJOR" -eq 3 -a "$MINOR" -lt 11 ]; then
    echo "ERROR: Python 3.11+ required (found $PY)"
    exit 1
fi
echo "Python $PY OK"

# 2. Check / install Rust
if ! command -v rustup &>/dev/null; then
    echo "Rust not found. Installing rustup..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
    source "$HOME/.cargo/env"
fi
echo "Rust $(rustc --version) OK"

# 3. Create virtualenv
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "Created .venv"
fi
source .venv/bin/activate

# 4. Install Python dependencies
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "Python dependencies installed"

# 5. Compile Rust extension
maturin develop --release
echo "Rust extension compiled"

# 6. Copy .env template if missing
if [ ! -f "config/.env" ]; then
    cp config/.env.example config/.env
    echo "Created config/.env from template — update KEYSTORE_SALT before use"
fi

echo ""
echo "=== Setup complete! ==="
echo "Activate venv: source .venv/bin/activate"
echo "Start GUI:     python launcher.py"
