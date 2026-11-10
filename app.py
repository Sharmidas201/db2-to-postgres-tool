"""
Azure Migration Assistant - entrypoint.
Sets up the page, shared session state, the sidebar and page navigation.
Pages live in app_pages/.
"""

import streamlit as st

st.set_page_config(
    page_title="Azure Migration Assistant - App Sizing & Data Explorer",
    page_icon=":material/cloud:",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Session state initialization
if "datasets" not in st.session_state:
    st.session_state.datasets = {}
if "active_app_num" not in st.session_state:
    st.session_state.active_app_num = ""

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.title("Migration assistant")
    st.caption("Application sizing & Excel explorer")

    st.subheader("Dataset status")
    slots_info = [
        ("ARM Service Now", "ARM SERVICE NOW FILE", "ARM Service now", ":material/apps:"),
        ("BA_AS_SERVER", "BA-AS-A-SERVER", "ba_as_server", ":material/link:"),
        ("CMDB_CI_SERVER", "CMDB-CI-SERVER", "cmdb_ci_server", ":material/dns:"),
    ]

    for label, schema_key, keyword, icon in slots_info:
        meta_entry = next(((k, v) for k, v in st.session_state.datasets.items() if v.get("detected_schema") == schema_key), None)
        if meta_entry:
            fname, meta = meta_entry
            path_tag = " *(local disk)*" if meta.get("file_path") else ""
            st.markdown(f"{icon} **{label}**")
            st.badge("Loaded", icon=":material/check_circle:", color="green")
            st.caption(f"`{fname}` | Rows: **{len(meta['df']):,}**{path_tag}")
        else:
            st.markdown(f"{icon} **{label}**")
            st.badge("Not loaded", color="gray")
            st.caption(f"Waiting for upload (includes `{keyword}`)")

# ---------------- NAVIGATION ----------------
pg = st.navigation([
    st.Page("app_pages/home.py", title="Home", icon=":material/home:", default=True),
    st.Page("app_pages/db2_assessment.py", title="Db2 assessment", icon=":material/schema:"),
    st.Page("app_pages/research.py", title="Research & guide", icon=":material/menu_book:"),
])
pg.run()
