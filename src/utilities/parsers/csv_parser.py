"""CSV bill parser with flexible column detection.

Handles two formats:
1. "Long" format: one row per bill (account, date, amount)
2. "Wide" format: one row per account, months as columns (e.g., ENWIN export)
   Columns like: Building, Unit, Account#, Status, Mar 2025, Apr 2025, ..., 12-Month Total
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from ..database import create_bill, get_meter_by_account
from ..models import BillModel, ParsedBillData

# Flexible column name mapping for "long" format CSVs
COLUMN_ALIASES = {
    "account_number": [
        "account", "account_number", "account_no", "account #", "account#",
        "acct", "acct_no", "customer_number", "customer_no", "customer #",
    ],
    "meter_number": [
        "meter", "meter_number", "meter_no", "meter #", "meter_id",
    ],
    "period_start": [
        "period_start", "billing_start", "start_date", "from", "from_date",
        "bill_start", "service_from", "read_date_from",
    ],
    "period_end": [
        "period_end", "billing_end", "end_date", "to", "to_date",
        "bill_end", "service_to", "read_date_to",
    ],
    "usage_amount": [
        "usage", "usage_amount", "consumption", "kwh", "volume", "quantity",
        "total_usage", "total_kwh", "units_used",
    ],
    "usage_unit": [
        "usage_unit", "uom", "unit_of_measure",
    ],
    "total_amount": [
        "total", "total_amount", "amount", "amount_due", "total_due",
        "total_charges", "bill_amount", "total_bill", "cost",
    ],
    "cost": [
        "cost_pretax", "subtotal", "charges", "pre_tax",
    ],
    "taxes": [
        "tax", "taxes", "hst", "gst", "tax_amount",
    ],
    "utility_type": [
        "utility_type", "utility", "service_type", "service", "type",
    ],
    "provider_name": [
        "provider", "provider_name", "company", "utility_company", "supplier",
    ],
    "property_name": [
        "property", "property_name", "location", "building", "address",
        "service_address",
    ],
    "unit_number": [
        "unit", "unit_number", "unit_no", "suite", "apt",
    ],
    "status": [
        "status", "account_status",
    ],
}

# Pattern to detect month columns like "Mar 2025", "April 2025", "Jan 2026"
MONTH_COLUMN_PATTERN = re.compile(
    r"^(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+(\d{4})$",
    re.IGNORECASE,
)

# Known provider keywords to detect from filename
PROVIDER_KEYWORDS = {
    "enwin": "Enwin",
    "enbridge": "Enbridge",
    "bluewater": "Bluewater Power",
    "entegrus": "Entegrus",
    "london hydro": "London Hydro",
    "londonhydro": "London Hydro",
    "guelph": "Guelph Hydro",
    "hydro one": "Hydro One",
    "hydroone": "Hydro One",
}


class CSVParseResult:
    """Result of parsing a CSV file."""

    def __init__(self):
        self.parsed_bills: list[ParsedBillData] = []
        self.column_mapping: dict[str, str] = {}
        self.unmapped_columns: list[str] = []
        self.row_count: int = 0
        self.format_detected: str = ""  # "wide" or "long"
        self.errors: list[str] = []
        self.warnings: list[str] = []


def parse_csv_file(file_path: str | Path) -> CSVParseResult:
    """Parse a CSV or Excel file and extract bill records."""
    result = CSVParseResult()
    path = Path(file_path)

    try:
        if path.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(str(path))
        else:
            for encoding in ["utf-8", "latin-1", "cp1252"]:
                try:
                    df = pd.read_csv(str(path), encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                result.errors.append("Could not read CSV file with any supported encoding")
                return result
    except Exception as e:
        result.errors.append(f"Failed to read file: {e}")
        return result

    if df.empty:
        result.errors.append("File is empty")
        return result

    result.row_count = len(df)

    # Detect provider from filename
    provider_from_file = _detect_provider_from_filename(path.name)

    # Detect format: wide (months as columns) vs long (one row per bill)
    month_columns = _detect_month_columns(df.columns.tolist())

    if month_columns:
        result.format_detected = "wide"
        _parse_wide_format(df, month_columns, provider_from_file, path.name, result)
    else:
        result.format_detected = "long"
        _parse_long_format(df, provider_from_file, path.name, result)

    return result


def _parse_wide_format(
    df: pd.DataFrame,
    month_columns: dict[str, tuple[int, int]],
    provider_name: str | None,
    source_file: str,
    result: CSVParseResult,
):
    """Parse wide-format CSV where months are columns.

    Expected columns: Building, Unit, Account#, Status, Jan 2025, Feb 2025, ..., 12-Month Total
    """
    # Detect metadata columns
    col_map = _detect_columns(df.columns.tolist())

    for idx, row in df.iterrows():
        # Get account metadata
        account = None
        for field in ["account_number"]:
            if field in col_map:
                val = row.get(col_map[field])
                if pd.notna(val):
                    account = str(val).strip()

        building = None
        if "property_name" in col_map:
            val = row.get(col_map["property_name"])
            if pd.notna(val):
                building = str(val).strip()

        unit_number = None
        if "unit_number" in col_map:
            val = row.get(col_map["unit_number"])
            if pd.notna(val):
                unit_number = str(val).strip()

        # Skip rows with no account number and no building
        if not account and not building:
            continue

        # Create a bill for each month column that has a value
        for col_name, (year, month) in month_columns.items():
            val = row.get(col_name)
            amount = _parse_amount(val)
            if amount is None or amount == 0:
                continue

            last_day = calendar.monthrange(year, month)[1]
            period_start = date(year, month, 1)
            period_end = date(year, month, last_day)

            # Build service address from building + unit
            service_addr = building or ""
            if unit_number:
                service_addr = f"{service_addr} Unit {unit_number}".strip()

            result.parsed_bills.append(ParsedBillData(
                provider_name=provider_name,
                account_number=account,
                service_address=service_addr if service_addr else None,
                utility_type=_guess_utility_type_from_provider(provider_name),
                period_start=period_start,
                period_end=period_end,
                total_amount=amount,
                source_file=source_file,
                confidence=0.85,
            ))


def _parse_long_format(
    df: pd.DataFrame,
    provider_name: str | None,
    source_file: str,
    result: CSVParseResult,
):
    """Parse long-format CSV: one row per bill."""
    column_map = _detect_columns(df.columns.tolist())
    result.column_mapping = column_map
    result.unmapped_columns = [
        col for col in df.columns
        if col not in column_map.values()
    ]

    if "total_amount" not in column_map:
        result.errors.append(
            "Could not find a 'total amount' column. "
            "Available columns: " + ", ".join(df.columns.tolist())
        )
        return

    for idx, row in df.iterrows():
        try:
            bill = _row_to_parsed_bill(row, column_map, source_file, provider_name)
            if bill:
                result.parsed_bills.append(bill)
            else:
                result.warnings.append(f"Row {idx + 2}: Could not parse (missing required fields)")
        except Exception as e:
            result.errors.append(f"Row {idx + 2}: {e}")


# --- Format detection ---


def _detect_month_columns(headers: list[str]) -> dict[str, tuple[int, int]]:
    """Detect columns that represent months (e.g., 'Mar 2025', 'April 2025').

    Returns dict of {column_name: (year, month_number)}.
    """
    month_cols = {}
    month_names = {
        "jan": 1, "january": 1, "feb": 2, "february": 2,
        "mar": 3, "march": 3, "apr": 4, "april": 4,
        "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "september": 9,
        "oct": 10, "october": 10, "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }

    for header in headers:
        match = MONTH_COLUMN_PATTERN.match(header.strip())
        if match:
            month_str = match.group(1).lower()
            year = int(match.group(2))
            month_num = month_names.get(month_str)
            if month_num:
                month_cols[header] = (year, month_num)

    return month_cols


def _detect_provider_from_filename(filename: str) -> str | None:
    """Try to detect the utility provider from the filename."""
    name_lower = filename.lower()
    for keyword, provider in PROVIDER_KEYWORDS.items():
        if keyword in name_lower:
            return provider
    return None


def _guess_utility_type_from_provider(provider_name: str | None) -> str | None:
    """Guess the utility type based on provider name."""
    if not provider_name:
        return None
    name_lower = provider_name.lower()
    if "enbridge" in name_lower:
        return "gas"
    # Most Ontario municipal utilities provide hydro + water
    # Default to hydro since that's the primary service
    return "hydro"


# --- Column detection ---


def _detect_columns(headers: list[str]) -> dict[str, str]:
    """Map CSV headers to our standard field names using flexible matching."""
    mapping = {}
    headers_lower = {h: h.lower().strip().replace(" ", "_").replace("-", "_") for h in headers}

    for field_name, aliases in COLUMN_ALIASES.items():
        for header, normalized in headers_lower.items():
            if normalized in aliases or header.lower().strip() in aliases:
                mapping[field_name] = header
                break

    return mapping


# --- Row parsing (long format) ---


def _row_to_parsed_bill(
    row: pd.Series,
    column_map: dict[str, str],
    source_file: str,
    provider_override: str | None = None,
) -> ParsedBillData | None:
    """Convert a DataFrame row to a ParsedBillData using the column mapping."""

    def get_val(field: str):
        col = column_map.get(field)
        if col is None:
            return None
        val = row.get(col)
        if pd.isna(val):
            return None
        return val

    total = _parse_amount(get_val("total_amount"))
    if total is None:
        return None

    period_start = _parse_csv_date(get_val("period_start"))
    period_end = _parse_csv_date(get_val("period_end"))

    if period_start and not period_end:
        last_day = calendar.monthrange(period_start.year, period_start.month)[1]
        period_end = period_start.replace(day=last_day)
    elif period_end and not period_start:
        period_start = period_end.replace(day=1)

    usage = _parse_amount(get_val("usage_amount"))
    usage_unit = str(get_val("usage_unit")) if get_val("usage_unit") else None

    provider = provider_override
    if not provider:
        provider = str(get_val("provider_name")) if get_val("provider_name") else None

    confidence = 0.7
    if period_start and period_end:
        confidence += 0.2
    if get_val("account_number"):
        confidence += 0.1

    return ParsedBillData(
        provider_name=provider,
        account_number=str(get_val("account_number")) if get_val("account_number") else None,
        meter_number=str(get_val("meter_number")) if get_val("meter_number") else None,
        service_address=str(get_val("property_name")) if get_val("property_name") else None,
        utility_type=_normalize_utility_type(get_val("utility_type")) or _guess_utility_type_from_provider(provider),
        period_start=period_start,
        period_end=period_end,
        usage_amount=usage,
        usage_unit=usage_unit,
        cost=_parse_amount(get_val("cost")),
        taxes=_parse_amount(get_val("taxes")),
        total_amount=total,
        source_file=source_file,
        confidence=min(confidence, 1.0),
    )


# --- Value parsers ---


def _parse_csv_date(val) -> date | None:
    """Parse a date from various CSV formats."""
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val if isinstance(val, date) else val.date()
    if isinstance(val, pd.Timestamp):
        return val.date()

    val_str = str(val).strip()
    formats = [
        "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d",
        "%B %d, %Y", "%b %d, %Y", "%d-%b-%Y", "%d-%m-%Y",
        "%m-%d-%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            continue

    try:
        return pd.to_datetime(val_str).date()
    except Exception:
        return None


def _parse_amount(val) -> float | None:
    """Parse a monetary amount from various formats."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if not pd.isna(val) else None
    val_str = str(val).replace(",", "").replace("$", "").strip()
    if not val_str or val_str == "-" or val_str.lower() == "n/a":
        return None
    try:
        return float(val_str)
    except ValueError:
        return None


def _normalize_utility_type(val) -> str | None:
    """Normalize utility type strings to our standard values."""
    if val is None:
        return None
    val_lower = str(val).lower().strip()
    mapping = {
        "electric": "hydro", "electricity": "hydro", "hydro": "hydro",
        "power": "hydro", "electrical": "hydro",
        "gas": "gas", "natural gas": "gas", "natural_gas": "gas",
        "water": "water",
        "sewer": "sewer", "wastewater": "sewer", "waste water": "sewer",
    }
    return mapping.get(val_lower, val_lower)
