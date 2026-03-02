"""Streamlit entry point for the Utility Bills Analysis Dashboard.

Run with: streamlit run src/utilities/app.py
"""

import streamlit as st

from .database import init_db
from .seed_data import seed


def main():
    st.set_page_config(
        page_title="Utility Bills Dashboard",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Initialize database on first run
    if "db_initialized" not in st.session_state:
        init_db()
        count = seed()
        st.session_state.db_initialized = True
        if count > 0:
            st.toast(f"Initialized {count} properties")

    # Navigation
    st.sidebar.title("Utility Bills")
    page = st.sidebar.radio(
        "Navigate",
        ["Dashboard", "Property Detail", "Upload Bills", "Manage Properties"],
        label_visibility="collapsed",
    )

    if page == "Dashboard":
        from .pages.dashboard import render_dashboard
        render_dashboard()
    elif page == "Property Detail":
        from .pages.property_detail import render_property_detail
        render_property_detail()
    elif page == "Upload Bills":
        from .pages.upload import render_upload
        render_upload()
    elif page == "Manage Properties":
        from .pages.manage import render_manage
        render_manage()


if __name__ == "__main__":
    main()
