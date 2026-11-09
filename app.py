"""
Azure Migration Assistant - Excel Data Explorer & Application Sizing
Single-user Streamlit UI for viewing datasets and looking up application hardware specs by Application Number.
"""

import io
import importlib
from pathlib import Path
import streamlit as st
import pandas as pd
from schemas import detect_schema, KNOWN_SCHEMAS, normalize_name, check_filename_includes
from path_manager import (
    find_local_system_path,
    scan_default_local_files,
    save_persistent_path,
    load_persistent_paths,
    clear_persistent_paths
)
from sample_data import generate_sample_datasets
import app_lookup
import azure_recommender
importlib.reload(app_lookup)
importlib.reload(azure_recommender)
from app_lookup import extract_app_numbers, lookup_application, generate_app_excel_bytes
from azure_recommender import recommend_azure_postgresql, extract_domain_from_fqdn, select_azure_sku, generate_azure_markdown_report

st.set_page_config(
    page_title="Azure Migration Assistant - App Sizing & Data Explorer",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom minimal styling - theme friendly
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding-top: 8px;
        padding-bottom: 8px;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# Session state initialization
if "datasets" not in st.session_state:
    st.session_state.datasets = {}
if "active_app_num" not in st.session_state:
    st.session_state.active_app_num = ""


def load_dataset_from_source(source, expected_schema=None, slot_key=None):
    """
    Loads dataset from a local file path (str or Path) or uploaded file object.
    If the file exists on the local filesystem, saves the path, avoids holding large
    file_bytes in memory, and persists the path across app restarts.
    """
    file_path = None
    file_name = ""
    file_bytes = None

    if isinstance(source, (str, Path)):
        resolved = Path(source).expanduser().resolve()
        if resolved.exists() and resolved.is_file():
            file_path = resolved
            file_name = resolved.name
        else:
            st.error(f"File not found on system: {source}")
            return False
    elif hasattr(source, "name"):
        file_name = source.name
        # Check if this uploaded file exists on the local system
        local_match = find_local_system_path(file_name)
        if local_match:
            file_path = local_match
        else:
            file_bytes = source.getvalue()
    else:
        return False

    try:
        schema = detect_schema(file_name)
        if schema == "Custom / Unknown" and expected_schema:
            schema = expected_schema

        if file_path:
            if file_name.endswith((".xlsx", ".xls")):
                excel_file = pd.ExcelFile(file_path)
                sheet_names = excel_file.sheet_names
                pref_sheet = sheet_names[0]
                for s in sheet_names:
                    if any(k in s.lower() for k in ["server", "sheet", "data"]):
                        pref_sheet = s
                        break
                df = pd.read_excel(excel_file, sheet_name=pref_sheet)
                is_excel = True
            else:
                df = pd.read_csv(file_path)
                sheet_names = ["default"]
                pref_sheet = "default"
                is_excel = False

            # Persist path if slot_key provided or derivable
            derived_slot = slot_key
            if not derived_slot:
                if schema == "ARM SERVICE NOW FILE":
                    derived_slot = "arm"
                elif schema == "BA-AS-A-SERVER":
                    derived_slot = "ba"
                elif schema == "CMDB-CI-SERVER":
                    derived_slot = "cmdb"
            if derived_slot:
                save_persistent_path(derived_slot, str(file_path))

            st.session_state.datasets[file_name] = {
                "file_path": str(file_path),
                "file_bytes": None,
                "df": df,
                "detected_schema": schema,
                "sheets": sheet_names,
                "active_sheet": pref_sheet,
                "is_excel": is_excel,
                "is_local": True
            }
            return True
        else:
            # In-memory uploaded bytes fallback
            if file_name.endswith((".xlsx", ".xls")):
                excel_file = pd.ExcelFile(io.BytesIO(file_bytes))
                sheet_names = excel_file.sheet_names
                pref_sheet = sheet_names[0]
                for s in sheet_names:
                    if any(k in s.lower() for k in ["server", "sheet", "data"]):
                        pref_sheet = s
                        break
                df = pd.read_excel(excel_file, sheet_name=pref_sheet)
                is_excel = True
            else:
                df = pd.read_csv(io.BytesIO(file_bytes))
                sheet_names = ["default"]
                pref_sheet = "default"
                is_excel = False

            st.session_state.datasets[file_name] = {
                "file_path": None,
                "file_bytes": file_bytes,
                "df": df,
                "detected_schema": schema,
                "sheets": sheet_names,
                "active_sheet": pref_sheet,
                "is_excel": is_excel,
                "is_local": False
            }
            return True
    except Exception as e:
        st.error(f"Error loading {file_name}: {e}")
        return False


def load_file_into_state(file_name, file_bytes, expected_schema=None):
    """Compatibility wrapper calling load_dataset_from_source."""
    class DummyUpload:
        def __init__(self, name, bytes_val):
            self.name = name
            self._bytes = bytes_val
        def getvalue(self):
            return self._bytes
    return load_dataset_from_source(DummyUpload(file_name, file_bytes), expected_schema=expected_schema)


# Automatic restoration from saved persistent paths on startup
if "initialized_from_saved_paths" not in st.session_state:
    st.session_state.initialized_from_saved_paths = True
    saved_initial_paths = load_persistent_paths()
    slot_schemas_init = {
        "arm": "ARM SERVICE NOW FILE",
        "ba": "BA-AS-A-SERVER",
        "cmdb": "CMDB-CI-SERVER"
    }
    for s_slot, s_path in saved_initial_paths.items():
        if Path(s_path).exists():
            load_dataset_from_source(s_path, expected_schema=slot_schemas_init.get(s_slot), slot_key=s_slot)


def load_sample_data():
    """Populates session state with mock datasets for testing."""
    samples = generate_sample_datasets()
    st.session_state.datasets.clear()
    for name, df in samples.items():
        schema = detect_schema(name)
        st.session_state.datasets[name] = {
            "df": df,
            "detected_schema": schema,
            "sheets": ["Sheet1"],
            "active_sheet": "Sheet1",
            "is_excel": True,
            "file_bytes": None
        }


def convert_df_to_excel_bytes(dfs_dict):
    """Converts a dict of {sheet_name: df} into an in-memory Excel workbook."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in dfs_dict.items():
            safe_name = str(sheet_name)[:31].replace(":", "_").replace("/", "_").replace("\\", "_")
            df.to_excel(writer, sheet_name=safe_name, index=False)
    output.seek(0)
    return output.getvalue()


# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.title("☁️ Migration Assistant")
    st.caption("Application Sizing & Excel Explorer")
    st.markdown("---")

    st.subheader("📋 Dataset Status")
    slots_info = [
        ("ARM Service Now", "ARM SERVICE NOW FILE", "ARM Service now"),
        ("BA_AS_SERVER", "BA-AS-A-SERVER", "ba_as_server"),
        ("CMDB_CI_SERVER", "CMDB-CI-SERVER", "cmdb_ci_server")
    ]

    for label, schema_key, keyword in slots_info:
        meta_entry = next(((k, v) for k, v in st.session_state.datasets.items() if v.get("detected_schema") == schema_key), None)
        if meta_entry:
            fname, meta = meta_entry
            path_tag = " *(local disk)*" if meta.get("file_path") else ""
            st.markdown(f"**🟢 {label}**")
            st.caption(f"`{fname}` | Rows: **{len(meta['df']):,}**{path_tag}")
        else:
            st.markdown(f"**⚪ {label}**")
            st.caption(f"Waiting for path / upload (includes `{keyword}`)")

    st.markdown("---")
    st.subheader("📥 Consolidated Export")
    if st.session_state.datasets:
        export_dict = {}
        for fname, meta in st.session_state.datasets.items():
            sheet_title = meta["detected_schema"] if meta["detected_schema"] != "Custom / Unknown" else fname.split(".")[0]
            export_dict[sheet_title] = meta["df"]

        all_excel_bytes = convert_df_to_excel_bytes(export_dict)
        st.download_button(
            label="📥 Download Datasets (.xlsx)",
            data=all_excel_bytes,
            file_name="migration_datasets_consolidated.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch"
        )
    else:
        st.caption("Export available once files are loaded.")


# ---------------- MAIN CONTENT ----------------
st.title("☁️ Azure Migration Assistant")
st.caption("Application Hardware Sizing & Target Architecture Planner")

# Dedicated Upload & System Path Section on Main Page
with st.container(border=True):
    col_u_hdr, col_u_actions = st.columns([2.5, 2.5], vertical_alignment="center")
    with col_u_hdr:
        st.subheader("📁 Dataset Management & Local File Paths")
        st.caption("Point to files on your system or upload them. Local paths are saved and persist across restarts.")
    with col_u_actions:
        c_btn_local, c_btn_sample, c_btn_clear = st.columns(3)
        with c_btn_local:
            if st.button("⚡ Load Local", width="stretch", help="Load detected files from local system and save paths"):
                scanned = scan_default_local_files()
                slot_schemas = {"arm": "ARM SERVICE NOW FILE", "ba": "BA-AS-A-SERVER", "cmdb": "CMDB-CI-SERVER"}
                for s_key, s_path in scanned.items():
                    if s_path and s_path.exists():
                        load_dataset_from_source(s_path, expected_schema=slot_schemas.get(s_key), slot_key=s_key)
                st.session_state.active_app_num = ""
                st.rerun()
        with c_btn_sample:
            if st.button("🧪 Sample Data", width="stretch", help="Load built-in mock datasets"):
                load_sample_data()
                st.session_state.active_app_num = ""
                st.rerun()
        with c_btn_clear:
            if st.button("🗑️ Clear All", width="stretch", help="Clear all loaded datasets and saved path configuration"):
                st.session_state.datasets.clear()
                clear_persistent_paths()
                st.session_state.active_app_num = ""
                for k in ["last_arm_upload", "last_ba_upload", "last_cmdb_upload"]:
                    st.session_state.pop(k, None)
                st.rerun()

    col_arm, col_ba, col_cmdb = st.columns(3)

    saved_paths = load_persistent_paths()
    scanned_defaults = scan_default_local_files()

    # 1. ARM Service Now Slot
    with col_arm:
        with st.container(border=True):
            st.markdown("##### 1. ARM Service Now")
            st.caption("Catalog & metadata (includes `ARM Service now`)")

            default_arm_path = saved_paths.get("arm") or (str(scanned_defaults["arm"]) if scanned_defaults.get("arm") else "")
            c_inp_arm, c_btn_arm = st.columns([3, 1], vertical_alignment="bottom")
            with c_inp_arm:
                arm_path_input = st.text_input(
                    "Local File Path:",
                    value=default_arm_path,
                    key="input_arm_path",
                    placeholder="e.g. samples/ARM ServiceNow Data.xlsx",
                    help="System path to ARM ServiceNow Excel or CSV file"
                )
            with c_btn_arm:
                if st.button("Load", key="btn_load_arm", width="stretch", help="Load dataset directly from path"):
                    if arm_path_input.strip():
                        resolved_arm = find_local_system_path(arm_path_input.strip())
                        if resolved_arm:
                            to_del = [k for k, v in st.session_state.datasets.items() if v.get("detected_schema") == "ARM SERVICE NOW FILE"]
                            for k in to_del:
                                del st.session_state.datasets[k]
                            load_dataset_from_source(resolved_arm, expected_schema="ARM SERVICE NOW FILE", slot_key="arm")
                            st.session_state.active_app_num = ""
                            st.rerun()
                        else:
                            st.error(f"Path not found on disk: {arm_path_input}")

            arm_file = st.file_uploader(
                "Or drop/upload file",
                type=["xlsx", "xls", "csv"],
                key="uploader_arm_file",
                help="Drop or upload file. If located on this system, path will be saved."
            )
            if arm_file is not None:
                if st.session_state.get("last_arm_upload") != arm_file.name:
                    to_del = [k for k, v in st.session_state.datasets.items() if v.get("detected_schema") == "ARM SERVICE NOW FILE"]
                    for k in to_del:
                        del st.session_state.datasets[k]
                    st.session_state["last_arm_upload"] = arm_file.name
                    load_dataset_from_source(arm_file, expected_schema="ARM SERVICE NOW FILE", slot_key="arm")
                    st.session_state.active_app_num = ""
                    st.rerun()
            elif st.session_state.get("last_arm_upload"):
                prev = st.session_state.pop("last_arm_upload", None)
                if prev and prev in st.session_state.datasets:
                    del st.session_state.datasets[prev]
                    st.session_state.active_app_num = ""
                    st.rerun()

            arm_meta = next(((k, v) for k, v in st.session_state.datasets.items() if v.get("detected_schema") == "ARM SERVICE NOW FILE"), None)
            if arm_meta:
                fname, meta = arm_meta
                matched = check_filename_includes(fname, "ARM Service now") or ("arm" in normalize_name(fname) and "service" in normalize_name(fname))
                match_tag = "✅ Keyword verified" if matched else "⚠️ Keyword not in filename"
                path_info = f"📍 `{meta['file_path']}`" if meta.get("file_path") else "Uploaded via browser"
                st.success(f"🟢 **{fname}**\n\nRows: **{len(meta['df']):,}** | Cols: **{len(meta['df'].columns)}**\n\n{path_info}\n\n*{match_tag}*")
            else:
                st.info("⚪ *Not loaded yet*")

    # 2. BA_AS_SERVER Slot
    with col_ba:
        with st.container(border=True):
            st.markdown("##### 2. BA_AS_SERVER")
            st.caption("App-to-server mapping (includes `ba_as_server`)")

            default_ba_path = saved_paths.get("ba") or (str(scanned_defaults["ba"]) if scanned_defaults.get("ba") else "")
            c_inp_ba, c_btn_ba = st.columns([3, 1], vertical_alignment="bottom")
            with c_inp_ba:
                ba_path_input = st.text_input(
                    "Local File Path:",
                    value=default_ba_path,
                    key="input_ba_path",
                    placeholder="e.g. samples/BA_AS_Server_No_Filter.xlsx",
                    help="System path to BA_AS_SERVER Excel or CSV file"
                )
            with c_btn_ba:
                if st.button("Load", key="btn_load_ba", width="stretch", help="Load dataset directly from path"):
                    if ba_path_input.strip():
                        resolved_ba = find_local_system_path(ba_path_input.strip())
                        if resolved_ba:
                            to_del = [k for k, v in st.session_state.datasets.items() if v.get("detected_schema") == "BA-AS-A-SERVER"]
                            for k in to_del:
                                del st.session_state.datasets[k]
                            load_dataset_from_source(resolved_ba, expected_schema="BA-AS-A-SERVER", slot_key="ba")
                            st.session_state.active_app_num = ""
                            st.rerun()
                        else:
                            st.error(f"Path not found on disk: {ba_path_input}")

            ba_file = st.file_uploader(
                "Or drop/upload file",
                type=["xlsx", "xls", "csv"],
                key="uploader_ba_file",
                help="Drop or upload file. If located on this system, path will be saved."
            )
            if ba_file is not None:
                if st.session_state.get("last_ba_upload") != ba_file.name:
                    to_del = [k for k, v in st.session_state.datasets.items() if v.get("detected_schema") == "BA-AS-A-SERVER"]
                    for k in to_del:
                        del st.session_state.datasets[k]
                    st.session_state["last_ba_upload"] = ba_file.name
                    load_dataset_from_source(ba_file, expected_schema="BA-AS-A-SERVER", slot_key="ba")
                    st.session_state.active_app_num = ""
                    st.rerun()
            elif st.session_state.get("last_ba_upload"):
                prev = st.session_state.pop("last_ba_upload", None)
                if prev and prev in st.session_state.datasets:
                    del st.session_state.datasets[prev]
                    st.session_state.active_app_num = ""
                    st.rerun()

            ba_meta = next(((k, v) for k, v in st.session_state.datasets.items() if v.get("detected_schema") == "BA-AS-A-SERVER"), None)
            if ba_meta:
                fname, meta = ba_meta
                matched = check_filename_includes(fname, "ba_as_server") or check_filename_includes(fname, "ba_as_a_server")
                match_tag = "✅ Keyword verified" if matched else "⚠️ Keyword not in filename"
                path_info = f"📍 `{meta['file_path']}`" if meta.get("file_path") else "Uploaded via browser"
                st.success(f"🟢 **{fname}**\n\nRows: **{len(meta['df']):,}** | Cols: **{len(meta['df'].columns)}**\n\n{path_info}\n\n*{match_tag}*")
            else:
                st.info("⚪ *Not loaded yet*")

    # 3. CMDB_CI_SERVER Slot
    with col_cmdb:
        with st.container(border=True):
            st.markdown("##### 3. CMDB_CI_SERVER")
            st.caption("Server hardware specs & OS (includes `cmdb_ci_server`)")

            default_cmdb_path = saved_paths.get("cmdb") or (str(scanned_defaults["cmdb"]) if scanned_defaults.get("cmdb") else "")
            c_inp_cmdb, c_btn_cmdb = st.columns([3, 1], vertical_alignment="bottom")
            with c_inp_cmdb:
                cmdb_path_input = st.text_input(
                    "Local File Path:",
                    value=default_cmdb_path,
                    key="input_cmdb_path",
                    placeholder="e.g. samples/cmdb_ci_server.xlsx",
                    help="System path to CMDB_CI_SERVER Excel or CSV file"
                )
            with c_btn_cmdb:
                if st.button("Load", key="btn_load_cmdb", width="stretch", help="Load dataset directly from path"):
                    if cmdb_path_input.strip():
                        resolved_cmdb = find_local_system_path(cmdb_path_input.strip())
                        if resolved_cmdb:
                            to_del = [k for k, v in st.session_state.datasets.items() if v.get("detected_schema") == "CMDB-CI-SERVER"]
                            for k in to_del:
                                del st.session_state.datasets[k]
                            load_dataset_from_source(resolved_cmdb, expected_schema="CMDB-CI-SERVER", slot_key="cmdb")
                            st.session_state.active_app_num = ""
                            st.rerun()
                        else:
                            st.error(f"Path not found on disk: {cmdb_path_input}")

            cmdb_file = st.file_uploader(
                "Or drop/upload file",
                type=["xlsx", "xls", "csv"],
                key="uploader_cmdb_file",
                help="Drop or upload file. If located on this system, path will be saved."
            )
            if cmdb_file is not None:
                if st.session_state.get("last_cmdb_upload") != cmdb_file.name:
                    to_del = [k for k, v in st.session_state.datasets.items() if v.get("detected_schema") == "CMDB-CI-SERVER"]
                    for k in to_del:
                        del st.session_state.datasets[k]
                    st.session_state["last_cmdb_upload"] = cmdb_file.name
                    load_dataset_from_source(cmdb_file, expected_schema="CMDB-CI-SERVER", slot_key="cmdb")
                    st.session_state.active_app_num = ""
                    st.rerun()
            elif st.session_state.get("last_cmdb_upload"):
                prev = st.session_state.pop("last_cmdb_upload", None)
                if prev and prev in st.session_state.datasets:
                    del st.session_state.datasets[prev]
                    st.session_state.active_app_num = ""
                    st.rerun()

            cmdb_meta = next(((k, v) for k, v in st.session_state.datasets.items() if v.get("detected_schema") == "CMDB-CI-SERVER"), None)
            if cmdb_meta:
                fname, meta = cmdb_meta
                matched = check_filename_includes(fname, "cmdb_ci_server")
                match_tag = "✅ Keyword verified" if matched else "⚠️ Keyword not in filename"
                path_info = f"📍 `{meta['file_path']}`" if meta.get("file_path") else "Uploaded via browser"
                st.success(f"🟢 **{fname}**\n\nRows: **{len(meta['df']):,}** | Cols: **{len(meta['df'].columns)}**\n\n{path_info}\n\n*{match_tag}*")
            else:
                st.info("⚪ *Not loaded yet*")

if not st.session_state.datasets:
    # Empty State Guidance
    st.info("💡 **Getting Started:** Upload the Excel or CSV files above for **ARM Service Now**, **BA_AS_SERVER**, and **CMDB_CI_SERVER**, or click **🧪 Sample Data** to preview application sizing immediately.")
else:
    # Top-level Tabs
    main_tab_lookup, main_tab_explorer = st.tabs(["🎯 Application Sizing Lookup", "📁 Raw Datasets Explorer"])

    # ================= TAB 1: APPLICATION LOOKUP =================
    with main_tab_lookup:
        st.subheader("🎯 Application Sizing & Hardware Lookup")

        available_apps = extract_app_numbers(st.session_state.datasets)

        col_search1, col_search2, col_btn = st.columns([3, 2, 1])
        with col_search1:
            entered_app = st.text_input(
                "Enter Application Number:",
                value="",
                placeholder="Type application number (e.g. APP0001)...",
                help="Type the application number and press Enter or click Look Up"
            )
        with col_search2:
            if available_apps:
                picked_app = st.selectbox(
                    "Or pick from detected applications:",
                    options=[""] + available_apps,
                    index=0,
                    format_func=lambda x: "Select from detected list..." if x == "" else x,
                    help="Application numbers detected in your loaded datasets"
                )
            else:
                picked_app = ""
        with col_btn:
            st.write("")
            st.write("")
            lookup_clicked = st.button("🔍 Look Up", width="stretch")

        # Resolve selected application:
        # Priority: explicit typed text, then dropdown selection
        selected_app_num = None
        if entered_app.strip():
            selected_app_num = entered_app.strip()
        elif picked_app:
            selected_app_num = picked_app

        if selected_app_num:
            app_info, servers_df, rollup = lookup_application(selected_app_num, st.session_state.datasets)

            app_name = app_info.get("Name", "Name Not Specified in Catalog")
            env = app_info.get("Environment", "Unknown")
            crit = app_info.get("Business criticality", "Unknown")
            owner = app_info.get("IT Application owner", app_info.get("Business owner", "Not Listed"))
            status = app_info.get("Install Status", "Unknown")
            arch = app_info.get("Architecture type", "N/A")

            # App Title & Metadata Card (Theme-adaptive container)
            with st.container(border=True):
                st.subheader(f"🏷️ {selected_app_num}: {app_name}")
                col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
                col_m1.markdown(f"**Environment**\n\n`{env}`")
                col_m2.markdown(f"**Criticality**\n\n`{crit}`")
                col_m3.markdown(f"**Owner**\n\n{owner}")
                col_m4.markdown(f"**Status**\n\n`{status}`")
                col_m5.markdown(f"**Architecture**\n\n`{arch}`")

            # Hardware Rollup KPIs
            st.markdown("#### Hardware Resource Rollup")
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Total Servers", f"{rollup['Total Servers']}", f"{rollup['Virtual Servers']} VMs / {rollup['Physical Servers']} Phys")
            k2.metric("Total vCPUs / Cores", f"{rollup['Total vCPUs']}")
            k3.metric("Total RAM", f"{rollup['Total RAM (GB)']:.1f} GB")
            k4.metric("Allocated Storage", f"{rollup['Total Allocated Disk (GB)']:.1f} GB")
            k5.metric("In-Use / Consumed", f"{rollup['Total In-Use Disk (GB)']:.1f} GB")

            st.markdown("---")

            # Mapped Servers Table & Filters
            st.markdown("#### Mapped Host Servers")

            if not servers_df.empty:
                # 1. Filter by Domain or FQDN
                filter_c1, filter_c2 = st.columns([1, 2])
                all_fqdns = servers_df["Server FQDN"].dropna().tolist()
                domain_list = sorted(list(set(servers_df["Server FQDN"].apply(extract_domain_from_fqdn))))

                with filter_c1:
                    chosen_domain = st.selectbox(
                        "Filter by Domain:",
                        options=["All Domains"] + domain_list,
                        index=0,
                        key=f"dom_filter_{selected_app_num}",
                        help="Filter servers belonging to a specific network domain"
                    )

                if chosen_domain != "All Domains":
                    eligible_fqdns = [f for f in all_fqdns if extract_domain_from_fqdn(f) == chosen_domain]
                else:
                    eligible_fqdns = all_fqdns

                with filter_c2:
                    chosen_fqdns = st.multiselect(
                        "Filter by Server FQDN(s) to compute target sizing:",
                        options=eligible_fqdns,
                        default=eligible_fqdns,
                        key=f"fqdn_filter_{selected_app_num}",
                        help="Select one or more server FQDNs to include in Azure Flexible Server sizing"
                    )

                filtered_servers_df = servers_df[servers_df["Server FQDN"].isin(chosen_fqdns)] if chosen_fqdns else pd.DataFrame(columns=servers_df.columns)

                st.caption(f"Showing **{len(filtered_servers_df)}** of **{len(servers_df)}** mapped host servers")
                st.dataframe(filtered_servers_df, height=220)

                if not filtered_servers_df.empty:
                    # 2. Azure Target Recommendation Section
                    st.markdown("---")
                    
                    # Workload & Configuration controls
                    is_prod_workload = (env.lower() == "production") or (crit.lower() in ["critical", "high"])
                    
                    with st.container(border=True):
                        cfg_c1, cfg_c2 = st.columns([1.5, 2.0])
                        with cfg_c1:
                            source_engine = st.selectbox(
                                "Source Database Engine:",
                                options=["IBM Db2", "Generic / Other"],
                                index=0,
                                key=f"engine_{selected_app_num}",
                                help="Db2 workloads map to Memory Optimized E-Series to preserve bufferpool caching."
                            )
                        with cfg_c2:
                            ha_option = st.radio(
                                "High Availability Architecture:",
                                options=["Zone-Redundant HA (Dual-Zone Standby)", "Standalone (Single Zone)"],
                                index=0 if is_prod_workload else 1,
                                horizontal=True,
                                key=f"ha_{selected_app_num}",
                                help="Zone-redundant HA automatically provisions a synchronous standby in another AZ."
                            )
                            ha_enabled = "Zone-Redundant" in ha_option

                    # Sizing Rollup for filtered servers
                    filt_vcpus = float(filtered_servers_df["vCPUs"].sum())
                    filt_ram = float(filtered_servers_df["RAM (GB)"].sum())
                    filt_disk = float(filtered_servers_df["Allocated Disk (GB)"].sum())
                    if filt_disk <= 0:
                        filt_disk = float(filtered_servers_df["In-Use Disk (GB)"].sum())

                    # Run recommendation engine
                    azure_rec = recommend_azure_postgresql(
                        vcpus=filt_vcpus,
                        ram_gb=filt_ram,
                        disk_gb=filt_disk,
                        source_engine=source_engine,
                        is_production=is_prod_workload,
                        ha_override=ha_enabled
                    )

                    sku_meta = azure_rec["recommended_sku"]

                    # Precompute reports for download
                    try:
                        app_excel_bytes = generate_app_excel_bytes(app_info, filtered_servers_df, rollup, azure_rec=azure_rec)
                    except TypeError:
                        app_excel_bytes = generate_app_excel_bytes(app_info, filtered_servers_df, rollup)
                    
                    md_report_str = generate_azure_markdown_report(app_info, filtered_servers_df, azure_rec)

                    # Recommendation Header with Top Quick Download
                    col_rec_hdr, col_rec_dl = st.columns([2.6, 1.4])
                    with col_rec_hdr:
                        st.markdown("### ☁️ Azure Database for PostgreSQL – Sizing Recommendation & Reasoning")
                        st.caption("Automated architectural sizing and technical reasoning based on Azure Flexible Server best practices.")
                    with col_rec_dl:
                        st.download_button(
                            label="📥 Download Sizing Report (.xlsx)",
                            data=app_excel_bytes,
                            file_name=f"{selected_app_num}_azure_sizing_report.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            width="stretch",
                            key=f"dl_top_{selected_app_num}"
                        )

                    # Recommendation Card
                    with st.container(border=True):
                        st.markdown(f"#### 🎯 Recommended Target SKU: `{sku_meta['sku']}`")
                        badge_color = "🟣" if "Memory" in sku_meta["tier"] else "🔵"
                        st.markdown(f"**Tier:** {badge_color} **{sku_meta['tier']}** (`{sku_meta['family']}`) | **vCPUs:** `{sku_meta['vcpus']}` | **Memory:** `{sku_meta['memory_gib']} GiB` | **Target Storage:** `{azure_rec['target_storage_gib']:,} GiB`")

                        rec_m1, rec_m2, rec_m3, rec_m4 = st.columns(4)
                        rec_m1.metric("Compute SKU", sku_meta["sku"], f"{sku_meta['vcpus']} vCPUs")
                        rec_m2.metric("Target Memory", f"{sku_meta['memory_gib']} GiB", f"+25% Headroom ({filt_ram:.1f} GB src)")
                        rec_m3.metric("Provisioned Storage", f"{azure_rec['target_storage_gib']:,} GiB", f"+30% MVCC/WAL ({filt_disk:.1f} GB src)")
                        rec_m4.metric("High Availability", "Zone-Redundant" if ha_enabled else "Standalone", "Sync Replication" if ha_enabled else "Single Zone")

                    # Detailed Architectural Reasoning
                    st.markdown("##### 🧠 Sizing & Architectural Reasoning")
                    
                    r_col1, r_col2 = st.columns(2)
                    with r_col1:
                        with st.container(border=True):
                            st.markdown(f"**1. Compute Tier Selection: `{sku_meta['tier']}`**")
                            st.write(azure_rec["reasoning"]["tier_selection"]["justification"])
                            st.caption(f"Source vCPUs: {azure_rec['source_vcpus']:.0f} | Source RAM: {azure_rec['source_ram_gb']:.1f} GB")

                        with st.container(border=True):
                            st.markdown(f"**2. High Availability: `{azure_rec['reasoning']['high_availability']['mode']}`**")
                            st.write(azure_rec["reasoning"]["high_availability"]["justification"])
                            st.caption(f"App Environment: `{env}` | Business Criticality: `{crit}`.")

                    with r_col2:
                        with st.container(border=True):
                            st.markdown(f"**3. Compute & Memory Headroom: `{azure_rec['target_ram_gib']} GiB` Target**")
                            st.write(azure_rec["reasoning"]["compute_sizing"]["justification"])
                            st.caption(f"Target vCPUs: {azure_rec['target_vcpus']} cores | Target RAM: {azure_rec['target_ram_gib']} GiB (1.25× factor).")

                        with st.container(border=True):
                            st.markdown(f"**4. Storage & MVCC Headroom: `{azure_rec['target_storage_gib']:,} GiB` Target**")
                            st.write(azure_rec["reasoning"]["storage_sizing"]["justification"])
                            st.caption(f"Source Disk: {azure_rec['source_disk_gb']:.1f} GB | 1.30× MVCC safety margin.")

                    # If multiple servers filtered, provide individual server mapping
                    if len(filtered_servers_df) > 1:
                        with st.expander(f"🔍 Per-Server Individual Azure Target Breakdown ({len(filtered_servers_df)} servers)"):
                            indiv_rows = []
                            for _, srow in filtered_servers_df.iterrows():
                                s_fqdn = srow["Server FQDN"]
                                s_cpu = float(srow["vCPUs"])
                                s_ram = float(srow["RAM (GB)"])
                                s_disk = float(srow["Allocated Disk (GB)"]) if float(srow["Allocated Disk (GB)"]) > 0 else float(srow["In-Use Disk (GB)"])
                                s_rec = recommend_azure_postgresql(
                                    vcpus=s_cpu,
                                    ram_gb=s_ram,
                                    disk_gb=s_disk,
                                    source_engine=source_engine,
                                    is_production=is_prod_workload,
                                    ha_override=ha_enabled
                                )
                                s_sku = s_rec["recommended_sku"]
                                indiv_rows.append({
                                    "Server FQDN": s_fqdn,
                                    "Source Cores": int(s_cpu),
                                    "Source RAM (GB)": s_ram,
                                    "Source Disk (GB)": s_disk,
                                    "Azure SKU": s_sku["sku"],
                                    "Azure Tier": s_sku["tier"],
                                    "SKU Specs": f"{s_sku['vcpus']} vCPU / {s_sku['memory_gib']} GiB RAM",
                                    "Target Storage (GiB)": f"{s_rec['target_storage_gib']:,}",
                                    "HA Mode": "Zone-Redundant" if ha_enabled else "Standalone"
                                })
                            st.dataframe(pd.DataFrame(indiv_rows), height=200)

                    # Export Center
                    st.markdown("---")
                    st.markdown("##### 📥 Downloadable Sizing Reports")
                    dl_col_left, dl_col_btn1, dl_col_btn2 = st.columns([2.5, 1.25, 1.25])
                    with dl_col_left:
                        st.markdown(f"**Export Package for {selected_app_num} ({app_name}):**")
                        st.caption(f"Target SKU: `{sku_meta['sku']}` | Sized Storage: `{azure_rec['target_storage_gib']:,} GiB` | Mode: `{azure_rec['reasoning']['high_availability']['mode']}`")
                    with dl_col_btn1:
                        st.download_button(
                            label="📗 Excel Report (.xlsx)",
                            data=app_excel_bytes,
                            file_name=f"{selected_app_num}_azure_sizing_report.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            width="stretch",
                            key=f"dl_bottom_xlsx_{selected_app_num}"
                        )
                    with dl_col_btn2:
                        st.download_button(
                            label="📄 Markdown Brief (.md)",
                            data=md_report_str.encode("utf-8"),
                            file_name=f"{selected_app_num}_azure_sizing_brief.md",
                            mime="text/markdown",
                            width="stretch",
                            key=f"dl_bottom_md_{selected_app_num}"
                        )
                else:
                    st.warning("⚠️ No servers match the chosen domain or FQDN filter. Please select at least one FQDN to compute sizing.")
            else:
                st.warning(f"No servers found mapped to {selected_app_num} in BA-AS-A-SERVER. Ensure BA-AS-A-SERVER dataset is loaded.")

            # Full Application Metadata (Expandable)
            with st.expander("📋 View Complete Application Attributes from ARM Catalog"):
                attr_df = pd.DataFrame([{"Attribute": k, "Value": v} for k, v in app_info.items()])
                st.dataframe(attr_df, height=250)
        else:
            st.info("💡 **Enter an Application Number** above to compute hardware sizing, server mappings, and generate downloadable reports.")

    # ================= TAB 2: RAW DATASETS EXPLORER =================
    with main_tab_explorer:
        st.subheader("📁 Raw Datasets Explorer")

        total_files = len(st.session_state.datasets)
        total_rows = sum(len(m["df"]) for m in st.session_state.datasets.values())
        schema_types = [m["detected_schema"] for m in st.session_state.datasets.values()]
        known_matched = sum(1 for s in schema_types if s != "Custom / Unknown")

        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Loaded Files", f"{total_files}")
        kpi2.metric("Total Records Across Files", f"{total_rows:,}")
        kpi3.metric("Recognized Schemas", f"{known_matched} / {total_files}")

        st.markdown("---")

        file_list = list(st.session_state.datasets.keys())
        subtabs = st.tabs([f"📄 {f}" for f in file_list])

        for i, file_name in enumerate(file_list):
            with subtabs[i]:
                meta = st.session_state.datasets[file_name]
                df = meta["df"]
                detected = meta["detected_schema"]

                # Sheet selector if Excel has multiple sheets
                if meta.get("is_excel") and len(meta.get("sheets", [])) > 1:
                    col_sheet, col_empty = st.columns([2, 4])
                    with col_sheet:
                        new_sheet = st.selectbox(
                            f"Select Sheet for {file_name}:",
                            options=meta["sheets"],
                            index=meta["sheets"].index(meta["active_sheet"]),
                            key=f"sheet_select_{file_name}"
                        )
                        if new_sheet != meta["active_sheet"]:
                            meta["active_sheet"] = new_sheet
                            if meta.get("file_path") and Path(meta["file_path"]).exists():
                                new_df = pd.read_excel(meta["file_path"], sheet_name=new_sheet)
                            else:
                                new_df = pd.read_excel(io.BytesIO(meta["file_bytes"]), sheet_name=new_sheet)
                            meta["df"] = new_df
                            meta["detected_schema"] = detect_schema(file_name)
                            st.rerun()

                schema_info = KNOWN_SCHEMAS.get(detected, {})
                desc = schema_info.get("description", "Uploaded custom or unclassified dataset")
                st.info(f"**Detected Type:** `{detected}` — {desc}")

                ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([3, 2, 2])
                with ctrl_col1:
                    search_term = st.text_input(
                        "🔍 Quick Filter / Search across all columns",
                        key=f"search_{file_name}",
                        placeholder="Type keyword, hostname, app number, IP..."
                    )
                with ctrl_col2:
                    all_cols = list(df.columns)
                    selected_cols = st.multiselect(
                        "Select Columns to Display",
                        options=all_cols,
                        default=all_cols if len(all_cols) <= 15 else all_cols[:15],
                        key=f"cols_{file_name}",
                        help=f"Total columns available: {len(all_cols)}"
                    )
                with ctrl_col3:
                    st.write("")
                    st.write("")
                    col_d1, col_d2 = st.columns(2)
                    with col_d1:
                        csv_data = df.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            label="📄 CSV",
                            data=csv_data,
                            file_name=f"{file_name.split('.')[0]}.csv",
                            mime="text/csv",
                            key=f"dl_csv_{file_name}"
                        )
                    with col_d2:
                        excel_bytes = convert_df_to_excel_bytes({file_name.split(".")[0]: df})
                        st.download_button(
                            label="📗 Excel",
                            data=excel_bytes,
                            file_name=f"{file_name.split('.')[0]}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_xlsx_{file_name}"
                        )

                display_df = df if not selected_cols else df[selected_cols]
                if search_term.strip():
                    mask = display_df.astype(str).apply(
                        lambda row: row.str.contains(search_term.strip(), case=False, na=False).any(),
                        axis=1
                    )
                    filtered_df = display_df[mask]
                    st.caption(f"Showing **{len(filtered_df):,}** of **{len(df):,}** rows matching `'{search_term}'`")
                else:
                    filtered_df = display_df
                    st.caption(f"Displaying **{len(filtered_df):,}** rows and **{len(filtered_df.columns)}** columns")

                st.dataframe(
                    filtered_df,
                    height=450
                )

                with st.expander(f"📋 Column Details & Data Types ({len(df.columns)} columns)"):
                    col_stats = []
                    for col in df.columns:
                        col_stats.append({
                            "Column Name": col,
                            "Data Type": str(df[col].dtype),
                            "Non-Null Count": f"{df[col].notna().sum():,} / {len(df):,}",
                            "Unique Values": df[col].nunique(),
                            "Sample Value": str(df[col].dropna().iloc[0]) if not df[col].dropna().empty else "—"
                        })
                    st.dataframe(pd.DataFrame(col_stats), height=250)
