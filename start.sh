#!/usr/bin/env bash
set -euo pipefail

echo "====================================================================="
echo "  ZILLERS Quantitative Crypto Terminal - Startup (Linux/macOS)       "
echo "====================================================================="

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 is required but not installed."
    exit 1
fi

# Ensure configuration exists
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "[WARN] .env not found. Initializing from .env.example..."
        cp .env.example .env
        echo "[ACTION REQUIRED] Please edit .env to configure ADMIN_INITIAL_PASSWORD."
        exit 1
    else
        echo "[ERROR] .env file is missing!"
        exit 1
    fi
fi

# Create runtime directories
mkdir -p work/runtime data

PORT="${1:-8900}"
echo "[INFO] Starting ZILLERS dashboard on http://127.0.0.1:${PORT}"
exec python3 -m cryptoscope.dashboard --port "${PORT}"
