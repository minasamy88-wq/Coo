"""Upload page: import PDF and CSV utility bills with confirmation workflow."""

import shutil
from pathlib import Path

import pandas as pd
import streamlit as st

from ..analytics.anomalies import run_all_anomaly_checks
from ..config import UPLOAD_DIR
from ..database import (
    create_bill,
    create_meter,
    create_unit,
    get_all_properties,
    get_meter_by_account,
    get_meters_for_property,
)
from ..models import BillModel, MeterModel, ParsedBillData, UnitModel
from ..parsers.csv_parser import CSVParseResult, parse_csv_file
from ..parsers.pdf_parser import PDFParseResult, match_bill_to_property, parse_pdf_bill, save_parsed_bill


def render_upload():
    st.title("Upload Bills")
    st.markdown(
        "Upload PDF or CSV utility bills. The system will auto-detect the provider "
        "and extract bill data. First-time uploads from a new provider may need your confirmation."
    )

    # File uploader
    uploaded_files = st.file_uploader(
        "Drop utility bills here",
        type=["pdf", "csv", "xlsx", "xls"],
        accept_multiple_files=True,
        help="Supported: PDF bills, CSV exports, Excel files from utility provider portals",
    )

    if not uploaded_files:
        _render_tips()
        return

    properties = get_all_properties()
    if not properties:
        st.error("No properties configured. Please go to **Manage Properties** first.")
        return

    # Process each file
    for uploaded_file in uploaded_files:
        st.markdown(f"---\n### Processing: `{uploaded_file.name}`")

        # Save to upload directory
        file_path = UPLOAD_DIR / uploaded_file.name
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        if uploaded_file.name.lower().endswith(".pdf"):
            _process_pdf(file_path, properties)
        else:
            _process_csv(file_path, properties)

    # Run anomaly checks after all uploads
    st.markdown("---")
    if st.button("Run Anomaly Detection", type="primary"):
        with st.spinner("Checking for anomalies..."):
            run_all_anomaly_checks()
        st.success("Anomaly detection complete. Check the Dashboard for any new flags.")


def _process_pdf(file_path: Path, properties):
    """Process a single PDF bill."""
    with st.spinner(f"Parsing {file_path.name}..."):
        result = parse_pdf_bill(file_path)

    if result.errors:
        for err in result.errors:
            st.error(err)

    if result.warnings:
        for warn in result.warnings:
            st.warning(warn)

    if not result.parsed_bills:
        st.error("Could not extract any bill data from this PDF.")
        if result.raw_text:
            with st.expander("View raw extracted text"):
                st.text(result.raw_text[:3000])
        return

    if result.provider_name:
        st.info(f"Detected provider: **{result.provider_name}**")

    # Process each extracted bill
    for i, parsed in enumerate(result.parsed_bills):
        _handle_parsed_bill(parsed, properties, f"pdf_{file_path.name}_{i}")


def _process_csv(file_path: Path, properties):
    """Process a CSV/Excel file."""
    with st.spinner(f"Parsing {file_path.name}..."):
        result = parse_csv_file(file_path)

    if result.errors:
        for err in result.errors:
            st.error(err)
        return

    if result.warnings:
        for warn in result.warnings:
            st.warning(warn)

    st.success(f"Found {len(result.parsed_bills)} bill records in {result.row_count} rows")

    # Show column mapping
    if result.column_mapping:
        with st.expander("Column Mapping"):
            for field, col in result.column_mapping.items():
                st.text(f"  {field} ← {col}")
            if result.unmapped_columns:
                st.caption(f"Unmapped columns: {', '.join(result.unmapped_columns)}")

    # Process each parsed bill
    saved = 0
    skipped = 0
    needs_review = []

    for i, parsed in enumerate(result.parsed_bills):
        meter_id, match_method = match_bill_to_property(parsed)

        if meter_id:
            bill_id = save_parsed_bill(parsed, meter_id)
            if bill_id:
                saved += 1
            else:
                skipped += 1  # Duplicate
        else:
            needs_review.append((i, parsed))

    if saved:
        st.success(f"Saved {saved} bills")
    if skipped:
        st.info(f"Skipped {skipped} duplicate bills")

    # Handle bills that need property assignment
    if needs_review:
        st.warning(f"{len(needs_review)} bills need property assignment")
        for idx, parsed in needs_review:
            _handle_parsed_bill(parsed, properties, f"csv_{file_path.name}_{idx}")


def _handle_parsed_bill(parsed: ParsedBillData, properties, unique_key: str):
    """Handle a single parsed bill: match to property or ask user."""
    meter_id, match_method = match_bill_to_property(parsed)

    if meter_id:
        bill_id = save_parsed_bill(parsed, meter_id)
        if bill_id:
            st.success(
                f"Saved: {parsed.utility_type or 'Unknown'} bill "
                f"${parsed.total_amount:,.2f} "
                f"({parsed.period_start} to {parsed.period_end})"
            )
        else:
            st.info("Duplicate bill - already exists for this meter and period.")
        return

    # If address matched a property but no meter exists yet
    if match_method and match_method.startswith("address_match:"):
        prop_id = int(match_method.split(":")[1])
        _create_meter_and_save(parsed, prop_id, unique_key)
        return

    # Need user to assign to a property
    amount_str = f"${parsed.total_amount:,.2f}" if parsed.total_amount else "N/A"
    st.markdown(f"**Bill needs assignment:** {parsed.utility_type or 'Unknown'} {amount_str}")

    if parsed.service_address:
        st.caption(f"Service address: {parsed.service_address}")
    if parsed.account_number:
        st.caption(f"Account: {parsed.account_number}")

    # Show extracted data
    with st.expander("Extracted Data", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.text(f"Provider: {parsed.provider_name or 'Unknown'}")
            st.text(f"Type: {parsed.utility_type or 'Unknown'}")
            st.text(f"Account: {parsed.account_number or 'N/A'}")
            st.text(f"Meter: {parsed.meter_number or 'N/A'}")
        with col2:
            st.text(f"Period: {parsed.period_start} to {parsed.period_end}")
            st.text(f"Usage: {parsed.usage_amount} {parsed.usage_unit or ''}")
            total_str = f"${parsed.total_amount:,.2f}" if parsed.total_amount else "N/A"
            st.text(f"Total: {total_str}")
            st.text(f"Confidence: {parsed.confidence:.0%}")

    # Property selector
    prop_names = [p.name for p in properties]
    selected = st.selectbox(
        "Assign to property:",
        prop_names,
        key=f"prop_select_{unique_key}",
    )

    if st.button("Save Bill", key=f"save_{unique_key}"):
        prop = next((p for p in properties if p.name == selected), None)
        if prop:
            _create_meter_and_save(parsed, prop.id, unique_key)


def _create_meter_and_save(parsed: ParsedBillData, property_id: int, unique_key: str):
    """Create a new meter (if needed) and save the bill."""
    # Check if a meter already exists for this account
    meter = None
    if parsed.account_number:
        meter = get_meter_by_account(parsed.account_number)

    if not meter:
        # Create a new meter
        meter_model = MeterModel(
            property_id=property_id,
            account_number=parsed.account_number,
            meter_number=parsed.meter_number,
            utility_type=parsed.utility_type or "hydro",
            provider_name=parsed.provider_name or "Unknown",
            is_bulk=True,  # Default to bulk; user can change in Manage
        )
        meter_id = create_meter(meter_model)
        st.info(f"Created new meter: {parsed.utility_type} ({parsed.provider_name})")
    else:
        meter_id = meter.id

    bill_id = save_parsed_bill(parsed, meter_id)
    if bill_id:
        st.success(f"Saved bill #{bill_id}")
    else:
        st.info("Duplicate bill - already exists.")


def _render_tips():
    """Show helpful tips when no files are uploaded."""
    st.markdown("""
    ### Tips for uploading bills

    **PDF bills:**
    - Download directly from your provider portal (Enbridge, Enwin, Bluewater Power, etc.)
    - The system auto-detects the provider and extracts account numbers, usage, and costs
    - First upload from each provider needs your confirmation; after that it's automatic

    **CSV / Excel files:**
    - Many providers offer CSV or Excel export from their billing portals
    - CSVs are more reliable than PDFs for data accuracy
    - The system auto-detects column names (account, period, cost, usage, etc.)

    **Supported providers:**
    - Enbridge (gas)
    - Bluewater Power (hydro + water)
    - Entegrus (hydro + water)
    - Enwin (hydro + water)
    - London Hydro (hydro + water)
    - Guelph Hydro (hydro + water)
    - Hydro One (hydro)
    """)
