"""Main dashboard page: portfolio overview, anomalies, trends."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ..database import (
    get_active_anomalies,
    get_all_bills,
    get_all_properties,
    get_latest_bill_per_meter,
    get_monthly_totals,
)


def render_dashboard():
    st.title("Utility Bills Dashboard")

    properties = get_all_properties()
    anomalies = get_active_anomalies()
    monthly = get_monthly_totals(months=12)

    if not monthly:
        st.info(
            "No bill data yet. Go to **Upload Bills** to import your first utility bills, "
            "or check **Manage Properties** to see your configured properties."
        )
        _render_property_summary(properties)
        return

    df_monthly = pd.DataFrame(monthly)

    # --- Summary Cards ---
    _render_summary_cards(df_monthly)

    # --- Anomaly Panel ---
    _render_anomaly_panel(anomalies)

    # --- Trend Charts ---
    _render_trend_charts(df_monthly)

    # --- Property Heatmap ---
    _render_property_heatmap()

    # --- Property Table ---
    _render_property_table(properties)


def _render_summary_cards(df: pd.DataFrame):
    """Top-level KPI cards showing portfolio totals."""
    st.markdown("### Portfolio Overview")

    # Current month vs previous month
    if df.empty:
        return

    months_available = sorted(df["month"].unique())
    if len(months_available) < 1:
        return

    current_month = months_available[-1]
    current_total = df[df["month"] == current_month]["total"].sum()

    prev_total = None
    if len(months_available) >= 2:
        prev_month = months_available[-2]
        prev_total = df[df["month"] == prev_month]["total"].sum()

    # Year-over-year
    yoy_total = None
    yoy_month = current_month[:4]  # Get year
    target_yoy = str(int(yoy_month) - 1) + current_month[4:]
    if target_yoy in months_available:
        yoy_total = df[df["month"] == target_yoy]["total"].sum()

    # Anomaly count
    anomaly_count = len(get_active_anomalies())

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label=f"Total Spend ({current_month})",
            value=f"${current_total:,.2f}",
            delta=f"${current_total - prev_total:,.2f}" if prev_total else None,
            delta_color="inverse",
        )

    with col2:
        if prev_total and prev_total > 0:
            mom_change = (current_total - prev_total) / prev_total
            st.metric(
                label="Month-over-Month",
                value=f"{mom_change:+.1%}",
                delta=f"${current_total - prev_total:+,.2f}",
                delta_color="inverse",
            )
        else:
            st.metric(label="Month-over-Month", value="N/A")

    with col3:
        if yoy_total and yoy_total > 0:
            yoy_change = (current_total - yoy_total) / yoy_total
            st.metric(
                label="Year-over-Year",
                value=f"{yoy_change:+.1%}",
                delta=f"${current_total - yoy_total:+,.2f}",
                delta_color="inverse",
            )
        else:
            st.metric(label="Year-over-Year", value="N/A")

    with col4:
        st.metric(
            label="Active Flags",
            value=anomaly_count,
            delta="needs attention" if anomaly_count > 0 else "all clear",
            delta_color="inverse" if anomaly_count > 0 else "normal",
        )


def _render_anomaly_panel(anomalies):
    """Red/yellow flag panel for active anomalies."""
    if not anomalies:
        st.success("No active anomalies detected.")
        return

    st.markdown("### Flags Requiring Attention")

    high = [a for a in anomalies if a.severity == "high"]
    medium = [a for a in anomalies if a.severity == "medium"]

    if high:
        for a in high:
            st.error(
                f"**{a.anomaly_type.upper()}** | {a.property_name} "
                f"({a.utility_type}) | {a.description}"
            )

    if medium:
        for a in medium:
            st.warning(
                f"**{a.anomaly_type.upper()}** | {a.property_name} "
                f"({a.utility_type}) | {a.description}"
            )


def _render_trend_charts(df: pd.DataFrame):
    """Line charts showing spend over time by utility type."""
    st.markdown("### Spending Trends")

    if df.empty:
        return

    # Stacked area chart by utility type
    fig = px.area(
        df,
        x="month",
        y="total",
        color="utility_type",
        title="Monthly Spend by Utility Type",
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

    # Per-utility breakdown
    col1, col2 = st.columns(2)

    utility_types = df["utility_type"].unique()
    for i, util in enumerate(sorted(utility_types)):
        util_df = df[df["utility_type"] == util]
        fig = px.bar(
            util_df,
            x="month",
            y="total",
            title=f"{util.title()} - Monthly Cost",
            labels={"total": "Amount ($)", "month": "Month"},
        )
        fig.update_layout(height=300, showlegend=False)

        if i % 2 == 0:
            col1.plotly_chart(fig, use_container_width=True)
        else:
            col2.plotly_chart(fig, use_container_width=True)


def _render_property_heatmap():
    """Heatmap showing cost by property and utility type."""
    bills = get_all_bills(months=3)
    if not bills:
        return

    st.markdown("### Property Cost Heatmap (Last 3 Months)")

    df = pd.DataFrame([b.model_dump() for b in bills])
    if df.empty:
        return

    pivot = df.pivot_table(
        values="total_amount",
        index="property_name",
        columns="utility_type",
        aggfunc="sum",
        fill_value=0,
    )

    if pivot.empty:
        return

    fig = px.imshow(
        pivot.values,
        labels=dict(x="Utility Type", y="Property", color="Total ($)"),
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        color_continuous_scale="RdYlGn_r",
        aspect="auto",
    )
    fig.update_layout(height=max(300, len(pivot) * 30))
    st.plotly_chart(fig, use_container_width=True)


def _render_property_table(properties):
    """Sortable table with all properties and their latest costs."""
    st.markdown("### Property Summary")

    latest_bills = get_latest_bill_per_meter()

    if not latest_bills:
        _render_property_summary(properties)
        return

    df = pd.DataFrame([b.model_dump() for b in latest_bills])

    summary = df.groupby("property_name").agg(
        city=("property_city", "first"),
        total_latest=("total_amount", "sum"),
        meters=("meter_id", "nunique"),
        utilities=("utility_type", lambda x: ", ".join(sorted(x.unique()))),
    ).reset_index()

    summary = summary.rename(columns={
        "property_name": "Property",
        "city": "City",
        "total_latest": "Latest Month ($)",
        "meters": "Active Meters",
        "utilities": "Utility Types",
    })

    st.dataframe(
        summary.sort_values("Latest Month ($)", ascending=False),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Latest Month ($)": st.column_config.NumberColumn(format="$%.2f"),
        },
    )


def _render_property_summary(properties):
    """Show property list when no bill data exists yet."""
    st.markdown("### Configured Properties")
    if not properties:
        st.info("No properties configured. Go to **Manage Properties** to add your first property.")
        return

    data = [
        {"Property": p.name, "City": p.city or "TBD", "Province": p.province, "Notes": p.notes or ""}
        for p in properties
    ]
    st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
