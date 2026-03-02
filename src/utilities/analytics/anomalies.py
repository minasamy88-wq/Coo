"""Anomaly detection for utility bills: spike, peer comparison, and trend drift."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import (
    MIN_BILLS_FOR_SPIKE,
    MIN_UNITS_FOR_PEER,
    PEER_RATIO_HIGH,
    PEER_RATIO_MEDIUM,
    SPIKE_ZSCORE_HIGH,
    SPIKE_ZSCORE_MEDIUM,
    TREND_DRIFT_HIGH,
    TREND_DRIFT_MEDIUM,
)
from ..database import (
    clear_anomalies_for_meter,
    create_anomaly,
    get_all_bills,
    get_bills_for_meter,
    get_meters_for_property,
)
from ..models import AnomalyModel, BillWithContext


def run_all_anomaly_checks(meter_id: int | None = None):
    """Run all anomaly detection. If meter_id is given, only check that meter."""
    if meter_id:
        _check_spike_for_meter(meter_id)
    else:
        bills = get_all_bills(months=24)
        if not bills:
            return
        meter_ids = {b.meter_id for b in bills}
        for mid in meter_ids:
            _check_spike_for_meter(mid)

    _check_peer_comparisons()
    _check_trend_drift()


def _check_spike_for_meter(meter_id: int):
    """Spike detection: compare latest bill to rolling average for this meter."""
    bills = get_bills_for_meter(meter_id, limit=24)
    if len(bills) < MIN_BILLS_FOR_SPIKE + 1:
        return  # Not enough history

    clear_anomalies_for_meter(meter_id)

    latest = bills[0]
    historical = bills[1:7]  # Up to 6 prior bills

    amounts = [b.total_amount for b in historical if b.total_amount is not None]
    if len(amounts) < MIN_BILLS_FOR_SPIKE:
        return

    mean = np.mean(amounts)
    std = np.std(amounts)

    if std == 0 or latest.total_amount is None:
        return

    z_score = (latest.total_amount - mean) / std

    if z_score > SPIKE_ZSCORE_HIGH:
        create_anomaly(AnomalyModel(
            bill_id=latest.id,
            anomaly_type="spike",
            severity="high",
            description=f"Bill ${latest.total_amount:.2f} is {z_score:.1f} std devs above the 6-month average of ${mean:.2f}",
            value=latest.total_amount,
            threshold=mean + SPIKE_ZSCORE_HIGH * std,
        ))
    elif z_score > SPIKE_ZSCORE_MEDIUM:
        create_anomaly(AnomalyModel(
            bill_id=latest.id,
            anomaly_type="spike",
            severity="medium",
            description=f"Bill ${latest.total_amount:.2f} is {z_score:.1f} std devs above the 6-month average of ${mean:.2f}",
            value=latest.total_amount,
            threshold=mean + SPIKE_ZSCORE_MEDIUM * std,
        ))


def _check_peer_comparisons():
    """Peer comparison: compare units within the same property for the same utility type."""
    bills = get_all_bills(months=3)
    if not bills:
        return

    df = pd.DataFrame([b.model_dump() for b in bills])
    if df.empty or "total_amount" not in df.columns:
        return

    # Group by property + utility type, compare individual meters
    for (prop_name, util_type), group in df.groupby(["property_name", "utility_type"]):
        # Only compare if there are enough distinct meters
        meter_ids = group["meter_id"].unique()
        if len(meter_ids) < MIN_UNITS_FOR_PEER:
            continue

        # Get average cost per meter over the period
        meter_avg = group.groupby("meter_id")["total_amount"].mean()
        median_cost = meter_avg.median()

        if median_cost == 0:
            continue

        for mid, avg_cost in meter_avg.items():
            ratio = avg_cost / median_cost
            if ratio > PEER_RATIO_HIGH:
                # Find the latest bill for this meter in this group
                latest = group[group["meter_id"] == mid].sort_values("period_start", ascending=False).iloc[0]
                unit_info = latest.get("unit_number", "Unknown unit")
                create_anomaly(AnomalyModel(
                    bill_id=int(latest["id"]),
                    anomaly_type="peer_outlier",
                    severity="high",
                    description=f"{unit_info} at {prop_name} ({util_type}): avg ${avg_cost:.2f} is {ratio:.1f}x the property median of ${median_cost:.2f}",
                    value=avg_cost,
                    threshold=median_cost * PEER_RATIO_HIGH,
                ))
            elif ratio > PEER_RATIO_MEDIUM:
                latest = group[group["meter_id"] == mid].sort_values("period_start", ascending=False).iloc[0]
                unit_info = latest.get("unit_number", "Unknown unit")
                create_anomaly(AnomalyModel(
                    bill_id=int(latest["id"]),
                    anomaly_type="peer_outlier",
                    severity="medium",
                    description=f"{unit_info} at {prop_name} ({util_type}): avg ${avg_cost:.2f} is {ratio:.1f}x the property median of ${median_cost:.2f}",
                    value=avg_cost,
                    threshold=median_cost * PEER_RATIO_MEDIUM,
                ))


def _check_trend_drift():
    """Trend drift: flag meters where 3-month rolling average is increasing >15%."""
    bills = get_all_bills(months=12)
    if not bills:
        return

    df = pd.DataFrame([b.model_dump() for b in bills])
    if df.empty:
        return

    df["period_start"] = pd.to_datetime(df["period_start"])
    df["month"] = df["period_start"].dt.to_period("M")

    for meter_id, meter_bills in df.groupby("meter_id"):
        if len(meter_bills) < 6:
            continue

        monthly = meter_bills.groupby("month")["total_amount"].sum().sort_index()
        if len(monthly) < 6:
            continue

        # 3-month rolling average
        rolling = monthly.rolling(window=3, min_periods=3).mean()
        rolling = rolling.dropna()

        if len(rolling) < 2:
            continue

        # Compare latest 3-month avg to the one from 3 months ago
        current_avg = rolling.iloc[-1]
        if len(rolling) >= 4:
            prior_avg = rolling.iloc[-4]
        else:
            prior_avg = rolling.iloc[0]

        if prior_avg == 0:
            continue

        drift = (current_avg - prior_avg) / prior_avg

        if drift > TREND_DRIFT_HIGH:
            latest_bill = meter_bills.sort_values("period_start", ascending=False).iloc[0]
            prop = latest_bill.get("property_name", "Unknown")
            util = latest_bill.get("utility_type", "Unknown")
            create_anomaly(AnomalyModel(
                bill_id=int(latest_bill["id"]),
                anomaly_type="trend_drift",
                severity="high",
                description=f"{prop} ({util}): 3-month avg up {drift:.0%} (${prior_avg:.2f} → ${current_avg:.2f})",
                value=current_avg,
                threshold=prior_avg * (1 + TREND_DRIFT_HIGH),
            ))
        elif drift > TREND_DRIFT_MEDIUM:
            latest_bill = meter_bills.sort_values("period_start", ascending=False).iloc[0]
            prop = latest_bill.get("property_name", "Unknown")
            util = latest_bill.get("utility_type", "Unknown")
            create_anomaly(AnomalyModel(
                bill_id=int(latest_bill["id"]),
                anomaly_type="trend_drift",
                severity="medium",
                description=f"{prop} ({util}): 3-month avg up {drift:.0%} (${prior_avg:.2f} → ${current_avg:.2f})",
                value=current_avg,
                threshold=prior_avg * (1 + TREND_DRIFT_MEDIUM),
            ))
