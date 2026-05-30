#!/usr/bin/env bash
# Convenience launcher for Ubuntu/macOS.
# First run: ./run.sh --setup   (creates venv + installs deps)
# Then:      ./run.sh https://youtu.be/... -f md,docx,pdf
set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"

if [[ "${1:-}" == "--setup" ]]; then
    python3 -m venv "$VENV"
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "Setup complete. Copy .env.example to .env and add your ANTHROPIC_API_KEY."
    exit 0
fi

if [[ ! -d "$VENV" ]]; then
    echo "No virtualenv found. Run: ./run.sh --setup" >&2
    exit 1
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m usum "$@"
