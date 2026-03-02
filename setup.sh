#!/bin/bash
# Utility Bills Dashboard - One-time Setup Script for macOS
# Run with: bash setup.sh

set -e

echo "============================================"
echo "  Utility Bills Dashboard - Setup"
echo "============================================"
echo ""

# Step 1: Check for Homebrew
if ! command -v brew &> /dev/null; then
    echo "Installing Homebrew (macOS package manager)..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Add Homebrew to PATH for Apple Silicon Macs
    if [[ -f /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
    fi
    echo "Homebrew installed."
else
    echo "Homebrew already installed."
fi

# Step 2: Install Python
if ! command -v python3 &> /dev/null || ! python3 -c "import sys; assert sys.version_info >= (3,11)" 2>/dev/null; then
    echo "Installing Python 3.11+..."
    brew install python@3.12
    echo "Python installed."
else
    echo "Python 3.11+ already installed: $(python3 --version)"
fi

# Step 3: Create virtual environment
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [[ ! -d "$VENV_DIR" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "Virtual environment created at .venv/"
else
    echo "Virtual environment already exists."
fi

# Step 4: Activate and install dependencies
echo "Installing Python packages..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install streamlit pdfplumber pandas numpy plotly scipy openpyxl pydantic

# Step 5: Initialize database and seed properties
echo ""
echo "Initializing database and seeding properties..."
cd "$SCRIPT_DIR"
python3 -c "
import sys
sys.path.insert(0, '.')
from src.utilities.database import init_db
from src.utilities.seed_data import seed
init_db()
count = seed()
print(f'Database initialized. {count} properties seeded.')
"

echo ""
echo "============================================"
echo "  Setup Complete!"
echo "============================================"
echo ""
echo "To launch the dashboard, run:"
echo ""
echo "  bash run.sh"
echo ""
echo "Or manually:"
echo ""
echo "  source .venv/bin/activate"
echo "  streamlit run src/utilities/app.py"
echo ""
