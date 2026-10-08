#!/usr/bin/env bash
# Grabber Launcher for macOS and Linux

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "⚡ Avvio di Grabber (macOS / Linux)..."
echo "============================================================"

# Check if .venv exists
if [ -d ".venv" ]; then
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    fi
fi

# Ensure python is available
if command -v python3 &>/dev/null; then
    PYTHON_CMD=python3
elif command -v python &>/dev/null; then
    PYTHON_CMD=python
else
    echo "Errore: Python non trovato nel sistema. Installa Python 3.10+."
    exit 1
fi

# Run launcher
$PYTHON_CMD run.py
