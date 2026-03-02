"""CSV bill parser with flexible column detection."""

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from ..database import create_bill, get_meter_by_account
from ..models import BillModel, ParsedBillData

# Flexible column name mapping: maps various possible header names to our standard fields
COLUMN_ALIASES = {
    "account_number": [
        "account", "account_number", "account_no", "account #", "acct", "acct_no",
        "customer_number", "customer_no", "customer #",
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
        "usage_unit", "unit", "uom", "unit_of_measure",
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
}


class CSVParseResult:
    """Result of parsing a CSV file."""

    def __init__(self):
        self.parsed_bills: list[ParsedBillData] = []
        self.column_mapping: dict[str, str] = {}
        self.unmapped_columns: list[str] = []
        self.row_count: int = 0
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
            # Try different encodings
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

    # Map columns
    column_map = _detect_columns(df.columns.tolist())
    result.column_mapping = column_map
    result.unmapped_columns = [
        col for col in df.columns
        if col not in column_map.values()
    ]

    if "total_amount" not in column_map:
        result.errors.append("Could not find a 'total amount' column. Available columns: " + ", ".join(df.columns.tolist()))
        return result

    # Parse each row
    for idx, row in df.iterrows():
        try:
            bill = _row_to_parsed_bill(row, column_map, str(path.name))
            if bill:
                result.parsed_bills.append(bill)
            else:
                result.warnings.append(f"Row {idx + 2}: Could not parse (missing required fields)")
        except Exception as e:
            result.errors.append(f"Row {idx + 2}: {e}")

    return result


def _detect_columns(headers: list[str]) -> dict[str, str]:
    """Map CSV headers to our standard field names using fuzzy matching."""
    mapping = {}
    headers_lower = {h: h.lower().strip().replace(" ", "_").replace("-", "_") for h in headers}

    for field_name, aliases in COLUMN_ALIASES.items():
        for header, normalized in headers_lower.items():
            if normalized in aliases or header.lower().strip() in aliases:
                mapping[field_name] = header
                break

    return mapping


def _row_to_parsed_bill(row: pd.Series, column_map: dict[str, str], source_file: str) -> ParsedBillData | None:
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

    # If we only have one date, assume monthly billing
    if period_start and not period_end:
        # Assume end of month
        import calendar
        last_day = calendar.monthrange(period_start.year, period_start.month)[1]
        period_end = period_start.replace(day=last_day)
    elif period_end and not period_start:
        period_start = period_end.replace(day=1)

    usage = _parse_amount(get_val("usage_amount"))
    usage_unit = str(get_val("usage_unit")) if get_val("usage_unit") else None

    confidence = 0.7  # CSV data is generally more reliable than PDF extraction
    if period_start and period_end:
        confidence += 0.2
    if get_val("account_number"):
        confidence += 0.1

    return ParsedBillData(
        provider_name=str(get_val("provider_name")) if get_val("provider_name") else None,
        account_number=str(get_val("account_number")) if get_val("account_number") else None,
        meter_number=str(get_val("meter_number")) if get_val("meter_number") else None,
        service_address=str(get_val("property_name")) if get_val("property_name") else None,
        utility_type=_normalize_utility_type(get_val("utility_type")),
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

    # Try pandas parsing as last resort
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
    if not val_str:
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
