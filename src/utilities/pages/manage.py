"""Manage page: add/edit properties, units, meters, and provider templates."""

import pandas as pd
import streamlit as st

from ..database import (
    create_meter,
    create_property,
    create_unit,
    get_all_properties,
    get_all_provider_templates,
    get_meters_for_property,
    get_units_for_property,
    update_meter,
    update_property,
)
from ..models import MeterModel, PropertyModel, UnitModel


def render_manage():
    st.title("Manage Properties")

    tab1, tab2, tab3, tab4 = st.tabs(["Properties", "Units & Meters", "Add Property", "Provider Templates"])

    with tab1:
        _render_properties_list()

    with tab2:
        _render_units_and_meters()

    with tab3:
        _render_add_property()

    with tab4:
        _render_provider_templates()


def _render_properties_list():
    """Display and edit existing properties."""
    properties = get_all_properties()

    if not properties:
        st.info("No properties yet. Use the **Add Property** tab to create your first property.")
        return

    st.markdown(f"### {len(properties)} Properties")

    data = []
    for p in properties:
        meters = get_meters_for_property(p.id)
        units = get_units_for_property(p.id)
        data.append({
            "ID": p.id,
            "Property": p.name,
            "City": p.city or "—",
            "Units": len(units),
            "Meters": len(meters),
            "Notes": p.notes or "—",
        })

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Edit property
    st.markdown("#### Edit Property")
    prop_names = [p.name for p in properties]
    selected = st.selectbox("Select property to edit:", prop_names, key="edit_prop_select")
    prop = next((p for p in properties if p.name == selected), None)

    if prop:
        with st.form(f"edit_prop_{prop.id}"):
            name = st.text_input("Name", value=prop.name)
            address = st.text_input("Address", value=prop.address or "")
            city = st.text_input("City", value=prop.city or "")
            notes = st.text_area("Notes", value=prop.notes or "")

            if st.form_submit_button("Update Property"):
                prop.name = name
                prop.address = address or None
                prop.city = city or None
                prop.notes = notes or None
                update_property(prop)
                st.success(f"Updated {name}")
                st.rerun()


def _render_units_and_meters():
    """View and manage units and meters for a property."""
    properties = get_all_properties()
    if not properties:
        st.info("Add a property first.")
        return

    prop_names = [p.name for p in properties]
    selected = st.selectbox("Select property:", prop_names, key="um_prop_select")
    prop = next((p for p in properties if p.name == selected), None)

    if not prop:
        return

    # Units
    units = get_units_for_property(prop.id)
    meters = get_meters_for_property(prop.id)

    st.markdown(f"### Units ({len(units)})")
    if units:
        unit_data = [
            {"Unit": u.unit_number, "Common Area": "Yes" if u.is_common_area else "No", "Notes": u.notes or "—"}
            for u in units
        ]
        st.dataframe(pd.DataFrame(unit_data), use_container_width=True, hide_index=True)

    # Add unit
    with st.expander("Add Unit"):
        with st.form(f"add_unit_{prop.id}"):
            unit_number = st.text_input("Unit Number (e.g., '1', '2', 'basement', 'common')")
            is_common = st.checkbox("Common area (shared meter)")

            if st.form_submit_button("Add Unit"):
                if unit_number:
                    unit_id = create_unit(UnitModel(
                        property_id=prop.id,
                        unit_number=unit_number,
                        is_common_area=is_common,
                    ))
                    st.success(f"Added unit: {unit_number}")
                    st.rerun()

    # Meters
    st.markdown(f"### Meters ({len(meters)})")
    if meters:
        unit_map = {u.id: u.unit_number for u in units}
        meter_data = []
        for m in meters:
            meter_data.append({
                "ID": m.id,
                "Utility": m.utility_type.title(),
                "Provider": m.provider_name,
                "Account #": m.account_number or "—",
                "Meter #": m.meter_number or "—",
                "Unit": unit_map.get(m.unit_id, "Building-level"),
                "Bulk": "Yes" if m.is_bulk else "No",
                "Active": "Yes" if m.active else "No",
            })
        st.dataframe(pd.DataFrame(meter_data), use_container_width=True, hide_index=True)

    # Edit meter
    if meters:
        st.markdown("#### Edit Meter")
        meter_labels = [
            f"{m.utility_type.title()} - {m.provider_name} (#{m.account_number or m.id})"
            for m in meters
        ]
        selected_idx = st.selectbox("Select meter:", range(len(meters)),
                                     format_func=lambda i: meter_labels[i], key="edit_meter_select")
        meter = meters[selected_idx]

        with st.form(f"edit_meter_{meter.id}"):
            col1, col2 = st.columns(2)
            with col1:
                account = st.text_input("Account Number", value=meter.account_number or "")
                meter_num = st.text_input("Meter Number", value=meter.meter_number or "")
                utility = st.selectbox(
                    "Utility Type",
                    ["hydro", "gas", "water", "sewer"],
                    index=["hydro", "gas", "water", "sewer"].index(meter.utility_type),
                )
            with col2:
                provider = st.text_input("Provider", value=meter.provider_name)
                unit_options = ["Building-level (bulk)"] + [u.unit_number for u in units]
                current_unit = "Building-level (bulk)"
                if meter.unit_id:
                    unit_map = {u.id: u.unit_number for u in units}
                    current_unit = unit_map.get(meter.unit_id, "Building-level (bulk)")
                selected_unit = st.selectbox("Assigned Unit", unit_options,
                                              index=unit_options.index(current_unit) if current_unit in unit_options else 0)
                is_bulk = st.checkbox("Bulk meter (whole building)", value=meter.is_bulk)
                active = st.checkbox("Active", value=meter.active)

            if st.form_submit_button("Update Meter"):
                meter.account_number = account or None
                meter.meter_number = meter_num or None
                meter.utility_type = utility
                meter.provider_name = provider
                meter.is_bulk = is_bulk
                meter.active = active

                if selected_unit == "Building-level (bulk)":
                    meter.unit_id = None
                else:
                    unit = next((u for u in units if u.unit_number == selected_unit), None)
                    meter.unit_id = unit.id if unit else None

                update_meter(meter)
                st.success("Meter updated")
                st.rerun()

    # Add meter
    with st.expander("Add Meter"):
        with st.form(f"add_meter_{prop.id}"):
            col1, col2 = st.columns(2)
            with col1:
                new_account = st.text_input("Account Number", key="new_meter_acct")
                new_meter_num = st.text_input("Meter Number", key="new_meter_num")
                new_utility = st.selectbox("Utility Type", ["hydro", "gas", "water", "sewer"], key="new_meter_util")
            with col2:
                new_provider = st.text_input("Provider Name", key="new_meter_prov")
                new_bulk = st.checkbox("Bulk meter", key="new_meter_bulk")
                unit_opts = ["Building-level"] + [u.unit_number for u in units]
                new_unit_sel = st.selectbox("Unit", unit_opts, key="new_meter_unit")

            if st.form_submit_button("Add Meter"):
                if new_utility and new_provider:
                    unit_id = None
                    if new_unit_sel != "Building-level":
                        unit = next((u for u in units if u.unit_number == new_unit_sel), None)
                        unit_id = unit.id if unit else None

                    create_meter(MeterModel(
                        property_id=prop.id,
                        unit_id=unit_id,
                        account_number=new_account or None,
                        meter_number=new_meter_num or None,
                        utility_type=new_utility,
                        provider_name=new_provider,
                        is_bulk=new_bulk,
                    ))
                    st.success("Meter added")
                    st.rerun()


def _render_add_property():
    """Form to add a new property."""
    st.markdown("### Add New Property")

    with st.form("add_property"):
        name = st.text_input("Property Name (e.g., '892 Wellington')", placeholder="892 Wellington")
        address = st.text_input("Full Address (optional)", placeholder="892 Wellington St, Sarnia, ON")
        city = st.text_input("City", placeholder="Sarnia")
        notes = st.text_area("Notes (optional)", placeholder="Gas: Enbridge | Hydro+Water: Bluewater Power")

        if st.form_submit_button("Add Property"):
            if name:
                prop_id = create_property(PropertyModel(
                    name=name,
                    address=address or None,
                    city=city or None,
                    notes=notes or None,
                ))
                st.success(f"Created property: {name} (ID: {prop_id})")
                st.rerun()
            else:
                st.error("Property name is required")


def _render_provider_templates():
    """View and manage provider parsing templates."""
    st.markdown("### Provider Templates")
    st.caption(
        "These templates control how PDF bills are parsed for each provider. "
        "Templates are created automatically when you first upload a bill from a provider."
    )

    templates = get_all_provider_templates()

    if not templates:
        st.info(
            "No templates yet. Upload a bill to auto-create a template for that provider. "
            "Built-in templates for Ontario providers (Enbridge, Enwin, etc.) are used by default."
        )
        return

    for t in templates:
        with st.expander(f"{t.provider_name} - {t.utility_type} ({t.file_type})"):
            st.text(f"Confirmed: {'Yes' if t.confirmed else 'No'}")
            if t.field_patterns:
                st.json(t.field_patterns)
            if t.sample_text:
                st.text_area("Sample text", value=t.sample_text, height=100, disabled=True)
