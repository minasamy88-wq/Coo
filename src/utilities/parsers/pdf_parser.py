"""PDF bill parser using pdfplumber and provider-specific templates."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from ..database import (
    create_bill,
    create_meter,
    get_all_properties,
    get_meter_by_account,
    get_provider_template,
    save_provider_template,
)
from ..models import BillModel, MeterModel, ParsedBillData, ProviderTemplateModel
from .templates import (
    TEMPLATE_BY_NAME,
    detect_provider,
    extract_field,
    extract_field_groups,
)


class PDFParseResult:
    """Result of parsing a PDF bill."""

    def __init__(self):
        self.parsed_bills: list[ParsedBillData] = []
        self.raw_text: str = ""
        self.provider_name: str | None = None
        self.needs_confirmation: bool = False
        self.errors: list[str] = []
        self.warnings: list[str] = []


def extract_text_from_pdf(file_path: str | Path) -> str:
    """Extract all text from a PDF file using pdfplumber."""
    if pdfplumber is None:
        raise ImportError("pdfplumber is required for PDF parsing. Install with: pip install pdfplumber")

    text_parts = []
    with pdfplumber.open(str(file_path)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def parse_pdf_bill(file_path: str | Path) -> PDFParseResult:
    """Parse a utility bill PDF and extract structured data."""
    result = PDFParseResult()

    try:
        result.raw_text = extract_text_from_pdf(file_path)
    except Exception as e:
        result.errors.append(f"Failed to extract text from PDF: {e}")
        return result

    if not result.raw_text.strip():
        result.errors.append("PDF appears to be empty or image-only (no extractable text)")
        return result

    # Detect provider
    template = detect_provider(result.raw_text)
    if template is None:
        result.errors.append("Could not identify utility provider from bill text")
        result.needs_confirmation = True
        # Still try to extract what we can with generic patterns
        bill = _extract_generic(result.raw_text, file_path)
        if bill:
            result.parsed_bills.append(bill)
        return result

    result.provider_name = template.provider_name

    # Check if we have a confirmed DB template (user-refined patterns)
    for util_type in template.utility_types:
        db_template = get_provider_template(template.provider_name, util_type, "pdf")
        if db_template and db_template.confirmed:
            # Use the user-confirmed patterns from DB
            pass  # For now, fall through to built-in templates

    # Extract data using template
    if len(template.utility_types) > 1 and template.section_markers:
        # Multi-utility bill (e.g., hydro + water + sewer)
        bills = _extract_multi_utility(result.raw_text, template, file_path)
        result.parsed_bills.extend(bills)
    else:
        # Single utility bill (e.g., Enbridge gas)
        bill = _extract_single_utility(result.raw_text, template, template.utility_types[0], file_path)
        if bill:
            result.parsed_bills.append(bill)

    # Check if this is a first-time template or if confidence is low
    if not result.parsed_bills:
        result.errors.append(f"Could not extract bill data from {template.provider_name} PDF")
        result.needs_confirmation = True
    elif any(b.confidence < 0.6 for b in result.parsed_bills):
        result.needs_confirmation = True
        result.warnings.append("Low confidence extraction - please confirm the data")

    return result


def _extract_single_utility(text: str, template, utility_type: str, file_path: str | Path) -> ParsedBillData | None:
    """Extract bill data for a single-utility bill."""
    account = extract_field(text, template.account_number)
    meter = extract_field(text, template.meter_number)
    address = extract_field(text, template.service_address)

    # Billing period
    period_start, period_end = None, None
    period_groups = extract_field_groups(text, template.billing_period)
    if period_groups and len(period_groups) >= 2:
        period_start = _parse_date(period_groups[0])
        period_end = _parse_date(period_groups[1])

    # Usage
    usage_amount, usage_unit = None, None
    usage_groups = extract_field_groups(text, template.usage_amount)
    if usage_groups:
        usage_amount = _parse_number(usage_groups[0])
        if len(usage_groups) > 1:
            usage_unit = usage_groups[1]

    # Amounts
    total = _parse_number(extract_field(text, template.total_amount))
    cost = _parse_number(extract_field(text, template.cost_pretax)) if template.cost_pretax else None
    taxes = _parse_number(extract_field(text, template.taxes)) if template.taxes else None

    # Calculate confidence
    confidence = _calculate_confidence(account, period_start, period_end, total)

    return ParsedBillData(
        provider_name=template.provider_name,
        account_number=account,
        meter_number=meter,
        service_address=address,
        utility_type=utility_type,
        period_start=period_start,
        period_end=period_end,
        usage_amount=usage_amount,
        usage_unit=usage_unit or _default_usage_unit(utility_type),
        cost=cost,
        taxes=taxes,
        total_amount=total,
        raw_text=text[:2000],  # Store first 2000 chars for reference
        source_file=str(Path(file_path).name),
        confidence=confidence,
    )


def _extract_multi_utility(text: str, template, file_path: str | Path) -> list[ParsedBillData]:
    """Extract multiple utility charges from a combined bill (e.g., hydro+water+sewer)."""
    bills = []

    # Common fields shared across all charges on the bill
    account = extract_field(text, template.account_number)
    meter = extract_field(text, template.meter_number)
    address = extract_field(text, template.service_address)

    period_start, period_end = None, None
    period_groups = extract_field_groups(text, template.billing_period)
    if period_groups and len(period_groups) >= 2:
        period_start = _parse_date(period_groups[0])
        period_end = _parse_date(period_groups[1])

    # Try to get total amount for the whole bill
    total = _parse_number(extract_field(text, template.total_amount))
    taxes = _parse_number(extract_field(text, template.taxes)) if template.taxes else None

    # Try to extract per-section charges
    sections_found = {}
    for util_type, markers in template.section_markers.items():
        for marker in markers:
            match = re.search(marker, text, re.IGNORECASE)
            if match:
                sections_found[util_type] = match.start()
                break

    if sections_found:
        # Extract charge amounts from each section
        sorted_sections = sorted(sections_found.items(), key=lambda x: x[1])
        for i, (util_type, start_pos) in enumerate(sorted_sections):
            end_pos = sorted_sections[i + 1][1] if i + 1 < len(sorted_sections) else len(text)
            section_text = text[start_pos:end_pos]

            # Look for a charge amount in this section
            amount_match = re.search(r"\$?\s*([\d,]+\.\d{2})", section_text)
            section_total = _parse_number(amount_match.group(1)) if amount_match else None

            # Look for usage in this section
            usage_amount = None
            usage_unit = _default_usage_unit(util_type)
            if util_type == "hydro":
                kwh_match = re.search(r"([\d,.]+)\s*kWh", section_text, re.IGNORECASE)
                if kwh_match:
                    usage_amount = _parse_number(kwh_match.group(1))
                    usage_unit = "kWh"
            elif util_type in ("water", "sewer"):
                m3_match = re.search(r"([\d,.]+)\s*m[³3]", section_text, re.IGNORECASE)
                if m3_match:
                    usage_amount = _parse_number(m3_match.group(1))
                    usage_unit = "m³"

            confidence = _calculate_confidence(account, period_start, period_end, section_total)

            bills.append(ParsedBillData(
                provider_name=template.provider_name,
                account_number=account,
                meter_number=meter,
                service_address=address,
                utility_type=util_type,
                period_start=period_start,
                period_end=period_end,
                usage_amount=usage_amount,
                usage_unit=usage_unit,
                cost=section_total,
                taxes=None,  # Taxes usually only on total
                total_amount=section_total,
                raw_text=section_text[:1000],
                source_file=str(Path(file_path).name),
                confidence=confidence,
            ))
    else:
        # Couldn't split sections - create one bill with total
        confidence = _calculate_confidence(account, period_start, period_end, total)
        bills.append(ParsedBillData(
            provider_name=template.provider_name,
            account_number=account,
            meter_number=meter,
            service_address=address,
            utility_type="hydro",  # Default to hydro for unsplit bills
            period_start=period_start,
            period_end=period_end,
            usage_amount=None,
            usage_unit=None,
            cost=None,
            taxes=taxes,
            total_amount=total,
            raw_text=text[:2000],
            source_file=str(Path(file_path).name),
            confidence=confidence * 0.7,  # Lower confidence since we couldn't split
        ))

    return bills


def _extract_generic(text: str, file_path: str | Path) -> ParsedBillData | None:
    """Fallback: try to extract data without a provider template."""
    # Try common patterns
    account_patterns = [
        r"Account\s*(?:Number|No\.?|#)?\s*[:.]?\s*(\d[\d\s-]{5,})",
    ]
    total_patterns = [
        r"(?:Total\s+)?(?:Amount\s+)?(?:Due|Owing)\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
        r"(?:Please\s+)?Pay\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
    ]
    period_patterns = [
        r"(\w{3,9}\s+\d{1,2},?\s+\d{4})\s*(?:to|-)\s*(\w{3,9}\s+\d{1,2},?\s+\d{4})",
    ]

    account = extract_field(text, account_patterns)
    total = _parse_number(extract_field(text, total_patterns))

    period_start, period_end = None, None
    period_groups = extract_field_groups(text, period_patterns)
    if period_groups and len(period_groups) >= 2:
        period_start = _parse_date(period_groups[0])
        period_end = _parse_date(period_groups[1])

    if total is None:
        return None

    return ParsedBillData(
        account_number=account,
        total_amount=total,
        period_start=period_start,
        period_end=period_end,
        raw_text=text[:2000],
        source_file=str(Path(file_path).name),
        confidence=0.3,  # Low confidence for generic extraction
    )


def save_parsed_bill(parsed: ParsedBillData, meter_id: int) -> int | None:
    """Save a parsed bill to the database, linked to a specific meter."""
    if parsed.total_amount is None or parsed.period_start is None or parsed.period_end is None:
        return None

    bill = BillModel(
        meter_id=meter_id,
        period_start=parsed.period_start,
        period_end=parsed.period_end,
        usage_amount=parsed.usage_amount,
        usage_unit=parsed.usage_unit,
        cost=parsed.cost,
        taxes=parsed.taxes,
        total_amount=parsed.total_amount,
        source_file=parsed.source_file,
        confirmed=parsed.confidence >= 0.6,
    )
    return create_bill(bill)


def match_bill_to_property(parsed: ParsedBillData) -> tuple[int | None, str | None]:
    """Try to match a parsed bill to an existing property/meter.

    Returns (meter_id, match_method) or (None, None) if no match found.
    """
    # Method 1: Match by account number
    if parsed.account_number:
        meter = get_meter_by_account(parsed.account_number)
        if meter:
            return meter.id, "account_number"

    # Method 2: Match by service address to property
    if parsed.service_address:
        properties = get_all_properties()
        addr_lower = parsed.service_address.lower()
        for prop in properties:
            if prop.name and prop.name.lower() in addr_lower:
                return None, f"address_match:{prop.id}"
            if prop.address and prop.address.lower() in addr_lower:
                return None, f"address_match:{prop.id}"

    return None, None


# --- Utility functions ---


def _parse_date(date_str: str | None) -> date | None:
    """Parse a date string into a date object."""
    if not date_str:
        return None

    date_str = date_str.strip().rstrip(",")
    formats = [
        "%B %d, %Y",     # January 15, 2025
        "%B %d %Y",      # January 15 2025
        "%b %d, %Y",     # Jan 15, 2025
        "%b %d %Y",      # Jan 15 2025
        "%Y-%m-%d",      # 2025-01-15
        "%m/%d/%Y",      # 01/15/2025
        "%d-%m-%Y",      # 15-01-2025
        "%d/%m/%Y",      # 15/01/2025
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _parse_number(value: str | None) -> float | None:
    """Parse a number string, removing commas and currency symbols."""
    if not value:
        return None
    cleaned = value.replace(",", "").replace("$", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _calculate_confidence(account, period_start, period_end, total) -> float:
    """Calculate extraction confidence based on which fields were found."""
    score = 0.0
    if account:
        score += 0.2
    if period_start:
        score += 0.25
    if period_end:
        score += 0.25
    if total is not None:
        score += 0.3
    return min(score, 1.0)


def _default_usage_unit(utility_type: str) -> str:
    """Return the default usage unit for a utility type."""
    return {
        "hydro": "kWh",
        "gas": "m³",
        "water": "m³",
        "sewer": "m³",
    }.get(utility_type, "")
