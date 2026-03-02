"""Pydantic models for utility bills entities."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class PropertyModel(BaseModel):
    id: Optional[int] = None
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    province: str = "ON"
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


class UnitModel(BaseModel):
    id: Optional[int] = None
    property_id: int
    unit_number: str
    is_common_area: bool = False
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


class MeterModel(BaseModel):
    id: Optional[int] = None
    property_id: int
    unit_id: Optional[int] = None
    account_number: Optional[str] = None
    meter_number: Optional[str] = None
    utility_type: str  # hydro, gas, water, sewer
    provider_name: str
    is_bulk: bool = False
    active: bool = True
    created_at: Optional[datetime] = None


class BillModel(BaseModel):
    id: Optional[int] = None
    meter_id: int
    period_start: date
    period_end: date
    usage_amount: Optional[float] = None
    usage_unit: Optional[str] = None
    cost: Optional[float] = None
    taxes: Optional[float] = None
    total_amount: float
    source_file: Optional[str] = None
    confirmed: bool = True
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


class ProviderTemplateModel(BaseModel):
    id: Optional[int] = None
    provider_name: str
    utility_type: str
    file_type: str = "pdf"
    field_patterns: Optional[str] = None  # JSON string
    column_mapping: Optional[str] = None  # JSON string
    sample_text: Optional[str] = None
    confirmed: bool = False
    created_at: Optional[datetime] = None


class AnomalyModel(BaseModel):
    id: Optional[int] = None
    bill_id: int
    anomaly_type: str  # spike, peer_outlier, trend_drift
    severity: str  # low, medium, high
    description: str
    value: Optional[float] = None
    threshold: Optional[float] = None
    acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


# Extended models for dashboard display (with joined data)


class BillWithContext(BillModel):
    """Bill with property/meter context for dashboard display."""
    property_name: Optional[str] = None
    property_city: Optional[str] = None
    unit_number: Optional[str] = None
    utility_type: Optional[str] = None
    provider_name: Optional[str] = None
    account_number: Optional[str] = None
    meter_number: Optional[str] = None


class AnomalyWithContext(AnomalyModel):
    """Anomaly with full context for dashboard display."""
    property_name: Optional[str] = None
    property_city: Optional[str] = None
    unit_number: Optional[str] = None
    utility_type: Optional[str] = None
    provider_name: Optional[str] = None
    total_amount: Optional[float] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None


class ParsedBillData(BaseModel):
    """Data extracted from a PDF or CSV bill, before matching to a meter."""
    provider_name: Optional[str] = None
    account_number: Optional[str] = None
    meter_number: Optional[str] = None
    service_address: Optional[str] = None
    utility_type: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    usage_amount: Optional[float] = None
    usage_unit: Optional[str] = None
    cost: Optional[float] = None
    taxes: Optional[float] = None
    total_amount: Optional[float] = None
    raw_text: Optional[str] = None
    source_file: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
