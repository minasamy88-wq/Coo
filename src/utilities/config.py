"""Application configuration constants."""

import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "utilities.db"
UPLOAD_DIR = DATA_DIR / "uploads"
INBOX_DIR = DATA_DIR / "inbox"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
INBOX_DIR.mkdir(exist_ok=True)

# Anomaly detection thresholds
SPIKE_ZSCORE_MEDIUM = 2.0
SPIKE_ZSCORE_HIGH = 3.0
PEER_RATIO_MEDIUM = 1.5
PEER_RATIO_HIGH = 2.0
TREND_DRIFT_MEDIUM = 0.15  # 15%
TREND_DRIFT_HIGH = 0.25    # 25%
MIN_BILLS_FOR_SPIKE = 3     # Need at least 3 historical bills for spike detection
MIN_UNITS_FOR_PEER = 3      # Need at least 3 units for peer comparison

# Utility types
UTILITY_TYPES = ["hydro", "gas", "water", "sewer"]

# Ontario providers
PROVIDERS = [
    "Enbridge",
    "Bluewater Power",
    "Entegrus",
    "Enwin",
    "London Hydro",
    "Guelph Hydro",
    "Hydro One",
]
