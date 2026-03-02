"""Top-level launcher for the Utility Bills Dashboard.

Run with: streamlit run dashboard.py
"""

import sys
from pathlib import Path

# Ensure the project root is on the Python path so package imports work
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.utilities.app import main

main()
