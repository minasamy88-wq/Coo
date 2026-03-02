"""Property detail page: drill-down into individual properties, units, and meters."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ..database import (
    get_all_properties,
    get_bills_for_meter,
    get_bills_for_property,
    get_meters_for_property,
    get_property_monthly_totals,
    get_units_for_property,
)


def render_property_detail():
    st.title("Property Detail")

    properties = get_all_properties()
    if not properties:
        st.info("No properties configured yet. Go to **Manage Properties** to add properties.")
        return

    # Property selector in sidebar
    property_names = [p.name for p in properties]
    selected_name = st.sidebar.selectbox("Select Property", property_names)
    selected_prop = next((p for p in properties if p.name == selected_name), None)

    if not selected_prop:
        return

    # Property header
    st.markdown(f"## {selected_prop.name}")
    if selected_prop.city:
        st.caption(f"{selected_prop.city}, {selected_prop.province}")

    # Load data
    units = get_units_for_property(selected_prop.id)
    meters = get_meters_for_property(selected_prop.id)
    monthly_totals = get_property_monthly_totals(selected_prop.id, months=12)

    # Summary cards
    _render_property_summary(selected_prop, units, meters, monthly_totals)

    # Monthly cost breakdown
    if monthly_totals:
        _render_monthly_breakdown(monthly_totals)

    # Meter details
    if meters:
        _render_meter_details(meters)
        _render_peer_comparison(meters)
    else:
        st.info("No meters registered yet. Upload bills for this property to auto-create meters.")

    # Account/meter reference table
    if meters:
        _render_reference_table(meters, units)


def _render_property_summary(prop, units, meters, monthly_totals):
    """Summary cards for the property."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if monthly_totals:
            df = pd.DataFrame(monthly_totals)
            latest_month = df["month"].max()
            latest_total = df[df["month"] == latest_month]["total"].sum()
            st.metric("Latest Month Spend", f"${latest_total:,.2f}")
        else:
            st.metric("Latest Month Spend", "No data")

    with col2:
        st.metric("Units", len(units))

    with col3:
        st.metric("Active Meters", len(meters))

    with col4:
        utility_types = sorted({m.utility_type for m in meters})
        st.metric("Utility Types", ", ".join(utility_types) if utility_types else "None")


def _render_monthly_breakdown(monthly_totals):
    """Monthly cost breakdown by utility type."""
    st.markdown("### Monthly Cost Breakdown")

    df = pd.DataFrame(monthly_totals)

    fig = px.bar(
        df,
        x="month",
        y="total",
        color="utility_type",
        barmode="stack",
        title="Monthly Costs by Utility Type",
        labels={"total": "Amount ($)", "month": "Month", "utility_type": "Utility"},
        color_discrete_map={
            "hydro": "#FFA500",
            "gas": "#4169E1",
            "water": "#00CED1",
            "sewer": "#8B4513",
        },
    )
    fig.update_layout(hovermode="x unified", height=400)
    st.plotly_chart(fig, use_container_width=True)

    # Usage trends (if available)
    usage_df = df[df["total_usage"].notna() & (df["total_usage"] > 0)]
    if not usage_df.empty:
        st.markdown("### Usage Trends")
        for util in sorted(usage_df["utility_type"].unique()):
            util_data = usage_df[usage_df["utility_type"] == util]
            fig = px.line(
                util_data,
                x="month",
                y="total_usage",
                title=f"{util.title()} Usage Over Time",
                labels={"total_usage": "Usage", "month": "Month"},
                markers=True,
            )
            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)


def _render_meter_details(meters):
    """Detailed history for each meter."""
    st.markdown("### Meter History")

    # Let user select a meter
    meter_labels = []
    for m in meters:
        label = f"{m.utility_type.title()} - {m.provider_name}"
        if m.account_number:
            label += f" (Acct: {m.account_number})"
        if m.meter_number:
            label += f" [Meter: {m.meter_number}]"
        meter_labels.append(label)

    selected_idx = st.selectbox(
        "Select Meter",
        range(len(meters)),
        format_func=lambda i: meter_labels[i],
    )

    selected_meter = meters[selected_idx]
    bills = get_bills_for_meter(selected_meter.id, limit=24)

    if not bills:
        st.info("No bills recorded for this meter yet.")
        return

    df = pd.DataFrame([b.model_dump() for b in bills])
    df["period_start"] = pd.to_datetime(df["period_start"])

    # Cost history line chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["period_start"],
        y=df["total_amount"],
        mode="lines+markers",
        name="Total ($)",
        line=dict(color="#4169E1"),
    ))

    # Add usage on secondary axis if available
    if df["usage_amount"].notna().any():
        fig.add_trace(go.Scatter(
            x=df["period_start"],
            y=df["usage_amount"],
            mode="lines+markers",
            name=f"Usage ({df['usage_unit'].iloc[0] or ''})",
            yaxis="y2",
            line=dict(color="#FFA500", dash="dash"),
        ))
        fig.update_layout(
            yaxis2=dict(title="Usage", overlaying="y", side="right"),
        )

    fig.update_layout(
        title=f"Bill History - {selected_meter.utility_type.title()} ({selected_meter.provider_name})",
        xaxis_title="Billing Period",
        yaxis_title="Amount ($)",
        hovermode="x unified",
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Raw bill data table
    with st.expander("View Raw Bill Data"):
        display_df = df[["period_start", "period_end", "usage_amount", "usage_unit", "total_amount", "source_file"]].copy()
        display_df.columns = ["Start", "End", "Usage", "Unit", "Total ($)", "Source"]
        st.dataframe(display_df, use_container_width=True, hide_index=True)


def _render_peer_comparison(meters):
    """Compare costs across meters of the same utility type within this property."""
    st.markdown("### Peer Comparison")

    # Group meters by utility type
    util_groups = {}
    for m in meters:
        util_groups.setdefault(m.utility_type, []).append(m)

    for util_type, group_meters in sorted(util_groups.items()):
        if len(group_meters) < 2:
            continue

        st.markdown(f"**{util_type.title()}** - {len(group_meters)} meters")

        meter_data = []
        for m in group_meters:
            bills = get_bills_for_meter(m.id, limit=3)
            if bills:
                avg_cost = sum(b.total_amount for b in bills) / len(bills)
                label = m.account_number or m.meter_number or f"Meter #{m.id}"
                meter_data.append({"Meter": label, "Avg Cost (3mo)": avg_cost})

        if len(meter_data) >= 2:
            comp_df = pd.DataFrame(meter_data)
            fig = px.bar(
                comp_df,
                x="Meter",
                y="Avg Cost (3mo)",
                title=f"{util_type.title()} - 3-Month Average Cost per Meter",
                color="Avg Cost (3mo)",
                color_continuous_scale="RdYlGn_r",
            )
            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)


def _render_reference_table(meters, units):
    """Reference table showing all account and meter numbers."""
    st.markdown("### Account & Meter Reference")

    unit_map = {u.id: u.unit_number for u in units}

    data = []
    for m in meters:
        data.append({
            "Utility": m.utility_type.title(),
            "Provider": m.provider_name,
            "Account #": m.account_number or "—",
            "Meter #": m.meter_number or "—",
            "Unit": unit_map.get(m.unit_id, "Building-level") if m.unit_id else "Building-level",
            "Bulk": "Yes" if m.is_bulk else "No",
        })

    st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
