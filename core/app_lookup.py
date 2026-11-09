"""
Application lookup and hardware rollup logic.
Allows looking up an application by Application Number across all uploaded datasets.
"""

import re
import pandas as pd


def normalize_str(val):
    if pd.isna(val):
        return ""
    return str(val).strip()


def parse_ram_to_gb(val):
    """Converts various RAM representations (e.g. 16384 MB, '64 GB', 16) into numeric GB."""
    if pd.isna(val):
        return 0.0
    val_str = str(val).strip().lower()
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", val_str)
    if not m:
        return 0.0
    num = float(m.group(1))
    if "mb" in val_str or "mib" in val_str or num > 1024:
        # Treat as MB
        return round(num / 1024.0, 1)
    return round(num, 1)


def parse_disk_to_gb(val, is_mib=False):
    """Converts disk capacity (MiB or GB) to numeric GB."""
    if pd.isna(val):
        return 0.0
    val_str = str(val).strip().lower()
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", val_str)
    if not m:
        return 0.0
    num = float(m.group(1))
    if is_mib or "mib" in val_str or "mb" in val_str or num > 10000:
        return round(num / 1024.0, 1)
    return round(num, 1)


def extract_app_numbers(datasets):
    """Collects all unique application numbers from ARM and BA datasets."""
    app_numbers = set()

    for meta in datasets.values():
        df = meta["df"]
        schema = meta.get("detected_schema", "")

        # Check ARM
        if schema == "ARM SERVICE NOW FILE" or "Number" in df.columns:
            for col in ["Number", "number", "u_number"]:
                if col in df.columns:
                    app_numbers.update(df[col].dropna().astype(str).str.strip().unique())

        # Check BA-AS-A-SERVER
        if schema == "BA-AS-A-SERVER" or "u_business_application_1.number" in df.columns:
            for col in ["u_business_application_1.number", "number"]:
                if col in df.columns:
                    app_numbers.update(df[col].dropna().astype(str).str.strip().unique())

    # Filter out empty or whitespace strings
    return sorted([a for a in app_numbers if a])


def lookup_application(app_number, datasets):
    """
    Given an app_number and the loaded datasets, returns:
    - app_info: dict of application metadata from ARM
    - servers_df: DataFrame of linked servers with matched hardware specs
    - rollup: summary dict of total servers, vCPU, RAM (GB), Allocated Storage (GB), Consumed Storage (GB)
    """
    app_number_clean = str(app_number).strip().lower()

    # 1. Identify dataset DataFrames
    arm_df = None
    ba_df = None
    rv_df = None
    cmdb_df = None
    axonius_df = None

    for meta in datasets.values():
        schema = meta.get("detected_schema")
        df = meta["df"]
        if schema == "ARM SERVICE NOW FILE":
            arm_df = df
        elif schema == "BA-AS-A-SERVER":
            ba_df = df
        elif schema == "RV_TOOLS":
            rv_df = df
        elif schema == "CMDB-CI-SERVER":
            cmdb_df = df
        elif schema == "AXONIUS DEVICES":
            axonius_df = df

    # Fallback to column matching if schema detection didn't set the exact name
    if arm_df is None:
        for meta in datasets.values():
            if "Number" in meta["df"].columns and "Install Status" in meta["df"].columns:
                arm_df = meta["df"]
                break

    if ba_df is None:
        for meta in datasets.values():
            if "u_business_application_1.number" in meta["df"].columns:
                ba_df = meta["df"]
                break

    # 2. Get Application Info from ARM
    app_info = {"Application Number": app_number}
    if arm_df is not None:
        # Match on Number column
        col_candidates = [c for c in arm_df.columns if c.strip().lower() in ["number", "u_number"]]
        if col_candidates:
            match = arm_df[arm_df[col_candidates[0]].astype(str).str.strip().str.lower() == app_number_clean]
            if not match.empty:
                row = match.iloc[0]
                for col in arm_df.columns:
                    if pd.notna(row[col]):
                        app_info[col] = str(row[col])

    # 3. Find Servers from BA-AS-A-SERVER
    servers_list = []
    if ba_df is not None:
        col_app_num = None
        for c in ["u_business_application_1.number", "Number", "number"]:
            if c in ba_df.columns:
                col_app_num = c
                break

        if col_app_num:
            matched_ba = ba_df[ba_df[col_app_num].astype(str).str.strip().str.lower() == app_number_clean]
            for _, row in matched_ba.iterrows():
                fqdn = normalize_str(row.get("u_server_1.fqdn", row.get("fqdn", "")))
                ip = normalize_str(row.get("u_server_1.ip_address", row.get("ip_address", "")))
                app_name = normalize_str(row.get("u_business_application_1", app_info.get("Name", "")))
                is_virt = normalize_str(row.get("u_server_1.virtual", row.get("virtual", "")))
                env = normalize_str(row.get("u_server_1.environment", row.get("environment", "")))
                os_name = normalize_str(row.get("u_server_1.os", row.get("os", "")))

                servers_list.append({
                    "Server FQDN": fqdn,
                    "Hostname": fqdn.split(".")[0] if fqdn else "",
                    "IP Address": ip,
                    "Virtual": is_virt,
                    "Environment": env,
                    "OS": os_name,
                    "Application Name": app_name
                })

    # If BA is not provided but RV/CMDB is, we don't have mapping, but let's check
    if not servers_list and "Name" in app_info and not ba_df:
        # No BA mapping uploaded
        pass

    # 4. Enrich Servers with Hardware Specs (RV_TOOLS primary for VMs, CMDB for physical/fallback)
    enriched_servers = []

    # Pre-index RV_Tools by lowercase FQDN/DNS Name and VM name
    rv_map = {}
    if rv_df is not None:
        for _, r in rv_df.iterrows():
            dns = normalize_str(r.get("DNS Name", "")).lower()
            vm = normalize_str(r.get("VM", "")).lower()
            if dns:
                rv_map[dns] = r
            if vm:
                rv_map[vm] = r

    # Pre-index CMDB by lowercase FQDN and Name
    cmdb_map = {}
    if cmdb_df is not None:
        for _, r in cmdb_df.iterrows():
            fqdn = normalize_str(r.get("fqdn", "")).lower()
            name = normalize_str(r.get("name", "")).lower()
            if fqdn:
                cmdb_map[fqdn] = r
            if name:
                cmdb_map[name] = r

    for s in servers_list:
        fqdn = s["Server FQDN"].lower()
        host = s["Hostname"].lower()

        cpus = 0
        ram_gb = 0.0
        alloc_disk_gb = 0.0
        in_use_disk_gb = 0.0
        hardware_source = "None (Unmatched)"

        # Check RV_Tools first
        rv_match = rv_map.get(fqdn)
        if rv_match is None:
            rv_match = rv_map.get(host)

        if rv_match is not None:
            hardware_source = "RV_TOOLS (VMware)"
            try:
                cpus = int(pd.to_numeric(rv_match.get("CPUs", 0), errors="coerce") or 0)
            except Exception:
                cpus = 0
            ram_gb = parse_ram_to_gb(rv_match.get("Memory", 0))
            alloc_disk_gb = parse_disk_to_gb(rv_match.get("Total disk capacity MiB", 0), is_mib=True)
            in_use_disk_gb = parse_disk_to_gb(rv_match.get("In Use MiB", 0), is_mib=True)
            if not s["OS"] and pd.notna(rv_match.get("OS according to the configuration file")):
                s["OS"] = str(rv_match.get("OS according to the configuration file"))
            s["Virtual"] = "true"
        else:
            # Check CMDB-CI-SERVER
            cmdb_match = cmdb_map.get(fqdn)
            if cmdb_match is None:
                cmdb_match = cmdb_map.get(host)

            if cmdb_match is not None:
                hardware_source = "CMDB-CI-SERVER"
                try:
                    cpus = int(pd.to_numeric(cmdb_match.get("cpu_core_count", 0), errors="coerce") or 0)
                except Exception:
                    cpus = 0
                ram_gb = parse_ram_to_gb(cmdb_match.get("ram", 0))
                alloc_disk_gb = parse_disk_to_gb(cmdb_match.get("disk_space", 0), is_mib=False)
                in_use_disk_gb = alloc_disk_gb  # In-use usually not reported in CMDB
                if not s["OS"] and pd.notna(cmdb_match.get("os")):
                    s["OS"] = str(cmdb_match.get("os"))

        enriched_servers.append({
            "Server FQDN": s["Server FQDN"],
            "IP Address": s["IP Address"],
            "Environment": s["Environment"],
            "Virtual": s["Virtual"],
            "OS": s["OS"],
            "vCPUs": cpus,
            "RAM (GB)": ram_gb,
            "Allocated Disk (GB)": alloc_disk_gb,
            "In-Use Disk (GB)": in_use_disk_gb,
            "Hardware Source": hardware_source
        })

    servers_df = pd.DataFrame(enriched_servers)

    # 5. Compute Rollup Metrics
    if not servers_df.empty:
        rollup = {
            "Total Servers": len(servers_df),
            "Total vCPUs": int(servers_df["vCPUs"].sum()),
            "Total RAM (GB)": round(servers_df["RAM (GB)"].sum(), 1),
            "Total Allocated Disk (GB)": round(servers_df["Allocated Disk (GB)"].sum(), 1),
            "Total In-Use Disk (GB)": round(servers_df["In-Use Disk (GB)"].sum(), 1),
            "Virtual Servers": int((servers_df["Virtual"].str.lower() == "true").sum()),
            "Physical Servers": int((servers_df["Virtual"].str.lower() != "true").sum()),
        }
    else:
        rollup = {
            "Total Servers": 0,
            "Total vCPUs": 0,
            "Total RAM (GB)": 0.0,
            "Total Allocated Disk (GB)": 0.0,
            "Total In-Use Disk (GB)": 0.0,
            "Virtual Servers": 0,
            "Physical Servers": 0,
        }

    return app_info, servers_df, rollup


def generate_app_excel_bytes(app_info, servers_df, rollup, azure_rec=None, **kwargs):
    """Generates a formatted Excel report for a single application, including Azure recommendation if available."""
    import io
    output = io.BytesIO()

    # Format app_info and rollup as a clean vertical table
    summary_rows = []
    summary_rows.append({"Category": "Lookup", "Property": "Application Number", "Value": app_info.get("Application Number", "")})
    summary_rows.append({"Category": "Lookup", "Property": "Application Name", "Value": app_info.get("Name", "")})
    summary_rows.append({"Category": "Context", "Property": "Environment", "Value": app_info.get("Environment", "N/A")})
    summary_rows.append({"Category": "Context", "Property": "Business Criticality", "Value": app_info.get("Business criticality", "N/A")})
    summary_rows.append({"Category": "Context", "Property": "Install Status", "Value": app_info.get("Install Status", "N/A")})
    summary_rows.append({"Category": "Context", "Property": "IT Owner", "Value": app_info.get("IT Application owner", "N/A")})
    summary_rows.append({"Category": "Context", "Property": "Architecture Type", "Value": app_info.get("Architecture type", "N/A")})
    
    summary_rows.append({"Category": "Hardware Rollup", "Property": "Total Servers", "Value": rollup.get("Total Servers", 0)})
    summary_rows.append({"Category": "Hardware Rollup", "Property": "Virtual Servers (VMs)", "Value": rollup.get("Virtual Servers", 0)})
    summary_rows.append({"Category": "Hardware Rollup", "Property": "Physical Servers (Bare-Metal)", "Value": rollup.get("Physical Servers", 0)})
    summary_rows.append({"Category": "Hardware Rollup", "Property": "Total vCPUs / Cores", "Value": rollup.get("Total vCPUs", 0)})
    summary_rows.append({"Category": "Hardware Rollup", "Property": "Total RAM (GB)", "Value": rollup.get("Total RAM (GB)", 0.0)})
    summary_rows.append({"Category": "Hardware Rollup", "Property": "Total Allocated Disk (GB)", "Value": rollup.get("Total Allocated Disk (GB)", 0.0)})
    summary_rows.append({"Category": "Hardware Rollup", "Property": "Total Consumed/In-Use Disk (GB)", "Value": rollup.get("Total In-Use Disk (GB)", 0.0)})

    summary_df = pd.DataFrame(summary_rows)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if azure_rec:
            # 1. Primary Sheet: Azure Target Recommendation & Justifications
            sku = azure_rec.get("recommended_sku", {})
            reasoning = azure_rec.get("reasoning", {})
            
            rec_rows = [
                {"Category": "Application Context", "Attribute": "Application Number", "Specification": str(app_info.get("Application Number", ""))},
                {"Category": "Application Context", "Attribute": "Application Name", "Specification": str(app_info.get("Name", ""))},
                {"Category": "Application Context", "Attribute": "Environment", "Specification": str(app_info.get("Environment", "N/A"))},
                {"Category": "Application Context", "Attribute": "Business Criticality", "Specification": str(app_info.get("Business criticality", "N/A"))},
                {"Category": "Application Context", "Attribute": "Application Owner", "Specification": str(app_info.get("IT Application owner", "N/A"))},
                
                {"Category": "Target Cloud Service", "Attribute": "Service Name", "Specification": "Azure Database for PostgreSQL - Flexible Server"},
                {"Category": "Target Cloud Service", "Attribute": "Target Engine", "Specification": "PostgreSQL (migrated from IBM Db2)"},
                
                {"Category": "Compute Sizing", "Attribute": "Recommended SKU", "Specification": sku.get("sku", "")},
                {"Category": "Compute Sizing", "Attribute": "Compute Tier", "Specification": f"{sku.get('tier', '')} ({sku.get('family', '')})"},
                {"Category": "Compute Sizing", "Attribute": "Provisioned vCPUs", "Specification": f"{sku.get('vcpus', 0)} cores (sized from peak CPU if provided, else allocated cores)"},
                {"Category": "Compute Sizing", "Attribute": "Target Memory", "Specification": f"{sku.get('memory_gib', 0)} GiB (sized from {reasoning.get('compute_sizing', {}).get('headroom_label', 'source RAM')})"},
                
                {"Category": "Storage Sizing", "Attribute": "Provisioned Storage", "Specification": f"{azure_rec.get('target_storage_gib', 0):,} GiB (incorporates +30% MVCC/WAL headroom)"},
                {"Category": "Storage Sizing", "Attribute": "Effective IOPS", "Specification": f"{azure_rec.get('effective_iops', 3000):,} IOPS (Premium SSD v2 free tier, capped by the VM limit)"},
                
                {"Category": "High Availability", "Attribute": "Resilience Architecture", "Specification": reasoning.get("high_availability", {}).get("mode", "")},
                
                {"Category": "Architectural Justification", "Attribute": "1. Tier Selection Rationale", "Specification": reasoning.get("tier_selection", {}).get("justification", "")},
                {"Category": "Architectural Justification", "Attribute": "2. Compute Headroom Rationale", "Specification": reasoning.get("compute_sizing", {}).get("justification", "")},
                {"Category": "Architectural Justification", "Attribute": "3. Storage & MVCC Rationale", "Specification": reasoning.get("storage_sizing", {}).get("justification", "")},
                {"Category": "Architectural Justification", "Attribute": "4. High Availability Rationale", "Specification": reasoning.get("high_availability", {}).get("justification", "")},
            ]
            rec_df = pd.DataFrame(rec_rows)
            rec_df.to_excel(writer, sheet_name="Azure Sizing Recommendation", index=False)

        # 2. Mapped Servers Sheet
        if not servers_df.empty:
            servers_df.to_excel(writer, sheet_name="Mapped Host Servers", index=False)
        else:
            pd.DataFrame([{"Message": "No host servers mapped in BA-AS-A-SERVER"}]).to_excel(writer, sheet_name="Mapped Host Servers", index=False)

        # 3. Application Summary Sheet
        summary_df.to_excel(writer, sheet_name="App Summary & Hardware Rollup", index=False)

    output.seek(0)
    return output.getvalue()

