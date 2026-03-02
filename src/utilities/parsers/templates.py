"""Pre-built regex templates for Ontario utility bill providers.

Each template defines patterns to extract key fields from PDF text.
These are initial best-effort patterns; the system learns and refines
them from user confirmations via the provider_templates DB table.
"""

import json
import re
from dataclasses import dataclass, field

# Common date patterns found on Ontario utility bills
DATE_PATTERNS = [
    r"(\w{3,9}\s+\d{1,2},?\s+\d{4})",      # January 15, 2025
    r"(\d{4}-\d{2}-\d{2})",                   # 2025-01-15
    r"(\d{1,2}/\d{1,2}/\d{4})",               # 01/15/2025
    r"(\d{1,2}-\d{1,2}-\d{4})",               # 15-01-2025
]

AMOUNT_PATTERN = r"\$?\s*([\d,]+\.\d{2})"


@dataclass
class ProviderTemplate:
    """Regex patterns for extracting bill fields from a specific provider."""
    provider_name: str
    utility_types: list[str]  # What utility types this provider bills for
    # Detection: how to identify this provider from bill text
    detection_keywords: list[str]
    # Extraction patterns (regex with capture groups)
    account_number: list[str]
    meter_number: list[str]
    billing_period: list[str]  # Should have 2 capture groups: start, end
    service_address: list[str]
    usage_amount: list[str]  # Capture group 1: amount, optional group 2: unit
    total_amount: list[str]
    cost_pretax: list[str] = field(default_factory=list)
    taxes: list[str] = field(default_factory=list)
    # For multi-utility bills (hydro+water+sewer on one bill)
    section_markers: dict[str, list[str]] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "account_number": self.account_number,
            "meter_number": self.meter_number,
            "billing_period": self.billing_period,
            "service_address": self.service_address,
            "usage_amount": self.usage_amount,
            "total_amount": self.total_amount,
            "cost_pretax": self.cost_pretax,
            "taxes": self.taxes,
            "section_markers": self.section_markers,
        })


# --- Provider Templates ---

ENBRIDGE = ProviderTemplate(
    provider_name="Enbridge",
    utility_types=["gas"],
    detection_keywords=["enbridge", "enbridge gas", "enbridgegas.com"],
    account_number=[
        r"Account\s*(?:Number|No\.?|#)?\s*[:.]?\s*(\d[\d\s-]{5,})",
        r"Acct\.?\s*(?:No\.?|#)?\s*[:.]?\s*(\d[\d\s-]{5,})",
    ],
    meter_number=[
        r"Meter\s*(?:Number|No\.?)?\s*[:.]?\s*(\d{4,})",
        r"Meter\s*#?\s*[:.]?\s*(\d{4,})",
    ],
    billing_period=[
        r"(?:Billing\s+Period|Service\s+Period|Period)\s*[:.]?\s*" + DATE_PATTERNS[0] + r"\s*(?:to|-)\s*" + DATE_PATTERNS[0],
        r"(?:From|for)\s+" + DATE_PATTERNS[0] + r"\s*(?:to|-)\s*" + DATE_PATTERNS[0],
    ],
    service_address=[
        r"Service\s+Address\s*[:.]?\s*(.+?)(?:\n|$)",
        r"Premises\s*[:.]?\s*(.+?)(?:\n|$)",
    ],
    usage_amount=[
        r"(?:Total\s+)?(?:Gas\s+)?(?:Usage|Consumption)\s*[:.]?\s*([\d,.]+)\s*(m[³3]|cubic\s*m)",
        r"([\d,.]+)\s*m[³3]\s*(?:used|consumed)",
    ],
    total_amount=[
        r"(?:Total\s+)?(?:Amount\s+)?(?:Due|Owing|New\s+Charges)\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
        r"(?:Current\s+)?(?:Charges?|Balance)\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
        r"Please\s+Pay\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
    ],
    cost_pretax=[
        r"(?:Delivery|Distribution)\s+(?:Charge|Cost)\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
    ],
    taxes=[
        r"HST\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
        r"(?:Total\s+)?Tax(?:es)?\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
    ],
)

BLUEWATER_POWER = ProviderTemplate(
    provider_name="Bluewater Power",
    utility_types=["hydro", "water", "sewer"],
    detection_keywords=["bluewater power", "bluewater", "bluewaterpower"],
    account_number=[
        r"Account\s*(?:Number|No\.?|#)?\s*[:.]?\s*(\d[\d\s-]{5,})",
        r"Customer\s*(?:Number|No\.?|#)?\s*[:.]?\s*(\d[\d\s-]{5,})",
    ],
    meter_number=[
        r"Meter\s*(?:Number|No\.?)?\s*[:.]?\s*(\d{4,})",
    ],
    billing_period=[
        r"(?:Billing\s+Period|Service\s+Period)\s*[:.]?\s*" + DATE_PATTERNS[0] + r"\s*(?:to|-)\s*" + DATE_PATTERNS[0],
        r"(?:From|for)\s+" + DATE_PATTERNS[0] + r"\s*(?:to|-)\s*" + DATE_PATTERNS[0],
    ],
    service_address=[
        r"Service\s+Address\s*[:.]?\s*(.+?)(?:\n|$)",
    ],
    usage_amount=[
        r"(?:Total\s+)?(?:Electricity\s+)?(?:Usage|Consumption|Energy)\s*[:.]?\s*([\d,.]+)\s*(kWh)",
        r"([\d,.]+)\s*kWh",
        r"Water\s+(?:Usage|Consumption)\s*[:.]?\s*([\d,.]+)\s*(m[³3])",
    ],
    total_amount=[
        r"(?:Total\s+)?(?:Amount\s+)?(?:Due|Owing)\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
        r"(?:Please\s+)?Pay\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
    ],
    taxes=[
        r"HST\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
    ],
    section_markers={
        "hydro": [r"(?:Electricity|Electric)\s+(?:Charges?|Services?)", r"Distribution\s+Charges"],
        "water": [r"Water\s+(?:Charges?|Services?)", r"Water\s+(?:Supply|Distribution)"],
        "sewer": [r"(?:Sewer|Wastewater|Waste\s*water)\s+(?:Charges?|Services?)"],
    },
)

ENTEGRUS = ProviderTemplate(
    provider_name="Entegrus",
    utility_types=["hydro", "water", "sewer"],
    detection_keywords=["entegrus", "entegrus powerlines", "entegrus.com"],
    account_number=[
        r"Account\s*(?:Number|No\.?|#)?\s*[:.]?\s*(\d[\d\s-]{5,})",
        r"Customer\s*#?\s*[:.]?\s*(\d[\d\s-]{5,})",
    ],
    meter_number=[
        r"Meter\s*(?:Number|No\.?)?\s*#?\s*[:.]?\s*(\d{4,})",
    ],
    billing_period=[
        r"(?:Billing\s+Period|Service\s+Period)\s*[:.]?\s*" + DATE_PATTERNS[0] + r"\s*(?:to|-)\s*" + DATE_PATTERNS[0],
    ],
    service_address=[
        r"Service\s+Address\s*[:.]?\s*(.+?)(?:\n|$)",
    ],
    usage_amount=[
        r"([\d,.]+)\s*kWh",
        r"Water\s+(?:Usage|Consumption)\s*[:.]?\s*([\d,.]+)\s*(m[³3])",
    ],
    total_amount=[
        r"(?:Total\s+)?(?:Amount\s+)?(?:Due|Owing)\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
    ],
    taxes=[
        r"HST\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
    ],
    section_markers={
        "hydro": [r"(?:Electricity|Electric)\s+(?:Charges?|Services?)"],
        "water": [r"Water\s+(?:Charges?|Services?)"],
        "sewer": [r"(?:Sewer|Wastewater)\s+(?:Charges?|Services?)"],
    },
)

ENWIN = ProviderTemplate(
    provider_name="Enwin",
    utility_types=["hydro", "water", "sewer"],
    detection_keywords=["enwin", "enwin utilities", "enwin.com"],
    account_number=[
        r"Account\s*(?:Number|No\.?|#)?\s*[:.]?\s*(\d[\d\s-]{5,})",
    ],
    meter_number=[
        r"Meter\s*(?:Number|No\.?)?\s*[:.]?\s*(\d{4,})",
    ],
    billing_period=[
        r"(?:Billing\s+Period|Service\s+Period)\s*[:.]?\s*" + DATE_PATTERNS[0] + r"\s*(?:to|-)\s*" + DATE_PATTERNS[0],
    ],
    service_address=[
        r"Service\s+Address\s*[:.]?\s*(.+?)(?:\n|$)",
        r"(?:Location|Premise)\s*[:.]?\s*(.+?)(?:\n|$)",
    ],
    usage_amount=[
        r"([\d,.]+)\s*kWh",
        r"Water\s+(?:Usage|Consumption)\s*[:.]?\s*([\d,.]+)\s*(m[³3])",
    ],
    total_amount=[
        r"(?:Total\s+)?(?:Amount\s+)?(?:Due|Owing|Current)\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
    ],
    taxes=[
        r"HST\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
    ],
    section_markers={
        "hydro": [r"(?:Electricity|Electric)\s+(?:Charges?|Services?)"],
        "water": [r"Water\s+(?:Charges?|Services?)"],
        "sewer": [r"(?:Sewer|Wastewater)\s+(?:Charges?|Services?)"],
    },
)

LONDON_HYDRO = ProviderTemplate(
    provider_name="London Hydro",
    utility_types=["hydro", "water", "sewer"],
    detection_keywords=["london hydro", "londonhydro", "londonhydro.com"],
    account_number=[
        r"Account\s*(?:Number|No\.?|#)?\s*[:.]?\s*(\d[\d\s-]{5,})",
    ],
    meter_number=[
        r"Meter\s*(?:Number|No\.?)?\s*[:.]?\s*(\d{4,})",
    ],
    billing_period=[
        r"(?:Billing\s+Period|Service\s+Period)\s*[:.]?\s*" + DATE_PATTERNS[0] + r"\s*(?:to|-)\s*" + DATE_PATTERNS[0],
    ],
    service_address=[
        r"Service\s+Address\s*[:.]?\s*(.+?)(?:\n|$)",
    ],
    usage_amount=[
        r"(?:Total\s+)?(?:Electricity\s+)?(?:kWh\s+)?(?:Used|Usage|Consumption)\s*[:.]?\s*([\d,.]+)",
        r"([\d,.]+)\s*kWh",
    ],
    total_amount=[
        r"(?:Total\s+)?(?:Amount\s+)?(?:Due|Owing)\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
        r"(?:Please\s+)?Pay\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
    ],
    taxes=[
        r"HST\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
    ],
    section_markers={
        "hydro": [r"(?:Electricity|Electric)\s+(?:Charges?|Services?)"],
        "water": [r"Water\s+(?:Charges?|Services?)"],
        "sewer": [r"(?:Sewer|Wastewater)\s+(?:Charges?|Services?)"],
    },
)

GUELPH_HYDRO = ProviderTemplate(
    provider_name="Guelph Hydro",
    utility_types=["hydro", "water", "sewer"],
    detection_keywords=["guelph hydro", "alectra guelph", "guelphhydro"],
    account_number=[
        r"Account\s*(?:Number|No\.?|#)?\s*[:.]?\s*(\d[\d\s-]{5,})",
    ],
    meter_number=[
        r"Meter\s*(?:Number|No\.?)?\s*[:.]?\s*(\d{4,})",
    ],
    billing_period=[
        r"(?:Billing\s+Period|Service\s+Period)\s*[:.]?\s*" + DATE_PATTERNS[0] + r"\s*(?:to|-)\s*" + DATE_PATTERNS[0],
    ],
    service_address=[
        r"Service\s+Address\s*[:.]?\s*(.+?)(?:\n|$)",
    ],
    usage_amount=[
        r"([\d,.]+)\s*kWh",
        r"Water\s+(?:Usage|Consumption)\s*[:.]?\s*([\d,.]+)\s*(m[³3])",
    ],
    total_amount=[
        r"(?:Total\s+)?(?:Amount\s+)?(?:Due|Owing)\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
    ],
    taxes=[
        r"HST\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
    ],
    section_markers={
        "hydro": [r"(?:Electricity|Electric)\s+(?:Charges?|Services?)"],
        "water": [r"Water\s+(?:Charges?|Services?)"],
        "sewer": [r"(?:Sewer|Wastewater)\s+(?:Charges?|Services?)"],
    },
)

HYDRO_ONE = ProviderTemplate(
    provider_name="Hydro One",
    utility_types=["hydro"],
    detection_keywords=["hydro one", "hydroone", "hydroone.com"],
    account_number=[
        r"Account\s*(?:Number|No\.?|#)?\s*[:.]?\s*(\d[\d\s-]{5,})",
    ],
    meter_number=[
        r"Meter\s*(?:Number|No\.?)?\s*[:.]?\s*(\d{4,})",
    ],
    billing_period=[
        r"(?:Billing\s+Period|Service\s+Period)\s*[:.]?\s*" + DATE_PATTERNS[0] + r"\s*(?:to|-)\s*" + DATE_PATTERNS[0],
    ],
    service_address=[
        r"Service\s+Address\s*[:.]?\s*(.+?)(?:\n|$)",
        r"(?:Location|Premise)\s*[:.]?\s*(.+?)(?:\n|$)",
    ],
    usage_amount=[
        r"(?:Total\s+)?kWh\s+(?:Used|Usage)\s*[:.]?\s*([\d,.]+)",
        r"([\d,.]+)\s*kWh",
    ],
    total_amount=[
        r"(?:Total\s+)?(?:Amount\s+)?(?:Due|Owing)\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
        r"(?:Please\s+)?Pay\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
    ],
    taxes=[
        r"HST\s*[:.]?\s*\$?\s*([\d,]+\.\d{2})",
    ],
)

# Registry of all templates
ALL_TEMPLATES: list[ProviderTemplate] = [
    ENBRIDGE,
    BLUEWATER_POWER,
    ENTEGRUS,
    ENWIN,
    LONDON_HYDRO,
    GUELPH_HYDRO,
    HYDRO_ONE,
]

TEMPLATE_BY_NAME: dict[str, ProviderTemplate] = {t.provider_name: t for t in ALL_TEMPLATES}


def detect_provider(text: str) -> ProviderTemplate | None:
    """Detect which provider a bill belongs to based on text content."""
    text_lower = text.lower()
    for template in ALL_TEMPLATES:
        for keyword in template.detection_keywords:
            if keyword.lower() in text_lower:
                return template
    return None


def extract_field(text: str, patterns: list[str], flags: int = re.IGNORECASE) -> str | None:
    """Try multiple regex patterns and return the first match."""
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1).strip()
    return None


def extract_field_groups(text: str, patterns: list[str], flags: int = re.IGNORECASE) -> tuple | None:
    """Try multiple regex patterns and return all capture groups from first match."""
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.groups()
    return None
