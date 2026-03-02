#!/bin/bash
# Launch the Utility Bills Dashboard
# Run with: bash run.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [[ ! -d "$VENV_DIR" ]]; then
    echo "Virtual environment not found. Run setup first:"
    echo "  bash setup.sh"
    exit 1
fi

source "$VENV_DIR/bin/activate"
cd "$SCRIPT_DIR"
streamlit run src/utilities/app.py
