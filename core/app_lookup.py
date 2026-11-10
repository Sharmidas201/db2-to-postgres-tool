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
        df = meta.get("normalized_df", meta["df"])
        schema = meta.get("detected_schema", "")

        # Check ARM
        if schema in {"ARM SERVICE NOW FILE", "VISUAL-GROUP"} or "application_id" in df.columns or "Number" in df.columns:
            for col in ["application_id", "Number", "number", "u_number"]:
                if col in df.columns:
                    app_numbers.update(df[col].dropna().astype(str).str.strip().unique())

        # Check BA-AS-A-SERVER
        if schema == "BA-AS-A-SERVER" or "application_id" in df.columns or "u_business_application_1.number" in df.columns:
            for col in ["application_id", "u_business_application_1.number", "number"]:
                if col in df.columns:
                    app_numbers.update(df[col].dropna().astype(str).str.strip().unique())

    # Filter out empty or whitespace strings
    return sorted([a for a in app_numbers if a])


def lookup_application(app_number, datasets):
    """Join canonical application, relationship, and server records dynamically."""
    from core.source_adapters import normalize_frame

    app_key = str(app_number).strip().casefold()
    apps, links, servers = [], [], []
    for filename, meta in datasets.items():
        schema = meta.get("detected_schema", "Custom / Unknown")
        raw = meta["df"]
        canonical = meta.get("normalized_df")
        if canonical is None:
            canonical, _ = normalize_frame(raw, schema, filename)
        if schema in {"ARM SERVICE NOW FILE", "VISUAL-GROUP"}:
            apps.append((raw, canonical))
        if schema in {"BA-AS-A-SERVER", "VISUAL-GROUP"}:
            links.append(canonical)
        if schema in {"CMDB-CI-SERVER", "AXONIUS DEVICES", "RV_TOOLS", "SIZING REPORT"}:
            servers.append((schema, canonical))

    app_info = {"Application Number": app_number}
    app_match = None
    for raw, canonical in apps:
        if "application_id" not in canonical:
            continue
        matches = canonical[canonical["application_id"].astype(str).str.strip().str.casefold() == app_key]
        if not matches.empty:
            app_match = matches.iloc[0]
            raw_match = raw.loc[matches.index[0]]
            app_info.update({str(c): str(raw_match[c]) for c in raw.columns if pd.notna(raw_match[c])})
            break
    if app_match is not None:
        def app_value(field, legacy, default):
            value = app_match.get(field)
            return str(value) if pd.notna(value) and str(value).strip() else app_info.get(legacy, default)

        app_info.update({
            "Name": app_value("application_name", "Name", "Name Not Specified in Catalog"),
            "Environment": app_value("environment", "Environment", "Unknown"),
            "Business criticality": app_value("business_criticality", "Business criticality", "Unknown"),
            "IT Application owner": app_value("application_owner", "IT Application owner", "Not Listed"),
            "Install Status": app_value("install_status", "Install Status", "Unknown"),
            "Architecture type": app_value("architecture_type", "Architecture type", "N/A"),
        })

    link_rows = []
    for frame in links:
        if "application_id" not in frame:
            continue
        matched = frame[frame["application_id"].astype(str).str.strip().str.casefold() == app_key]
        link_rows.extend(matched.to_dict("records"))

    # Index hardware records by normalized FQDN and hostname. Later sources only
    # fill missing values, preserving the richer record where multiple sources match.
    hardware = {}
    source_priority = {"RV_TOOLS": 0, "CMDB-CI-SERVER": 1, "AXONIUS DEVICES": 2, "SIZING REPORT": 3}
    servers.sort(key=lambda item: source_priority.get(item[0], 10))
    for source, frame in servers:
        for _, row in frame.iterrows():
            fqdn = normalize_str(row.get("server_fqdn", "")).casefold()
            name = normalize_str(row.get("server_name", "")).casefold()
            for key in (fqdn, name, name.split(".")[0] if name else ""):
                if key:
                    hardware.setdefault(key, {})
                    for field, value in row.items():
                        if field.startswith("extra:") or pd.isna(value) or str(value).strip() == "":
                            continue
                        hardware[key].setdefault(field, value)
                    hardware[key].setdefault("hardware_source", source)

    output = []
    seen = set()
    for link in link_rows:
        fqdn = normalize_str(link.get("server_fqdn", ""))
        hostname = fqdn.split(".")[0]
        if (fqdn or hostname).casefold() in seen:
            continue
        seen.add((fqdn or hostname).casefold())
        hw = hardware.get(fqdn.casefold(), hardware.get(hostname.casefold(), {}))
        cpu = pd.to_numeric(hw.get("cpu_cores", 0), errors="coerce")
        cpu = int(cpu) if pd.notna(cpu) else 0
        ram_value = hw.get("memory_gb", hw.get("memory", 0))
        disk_value = hw.get("allocated_storage_gb", hw.get("allocated_storage_mib", hw.get("allocated_storage", 0)))
        disk_mib = "allocated_storage_mib" in hw
        used_value = hw.get("used_storage_mib", hw.get("used_storage_gb", 0))
        allocated_gb = parse_disk_to_gb(disk_value, is_mib=disk_mib)
        used_gb = parse_disk_to_gb(used_value, is_mib="used_storage_mib" in hw) if ("used_storage_mib" in hw or "used_storage_gb" in hw) else allocated_gb
        virtual = link.get("is_virtual", hw.get("is_virtual", ""))
        output.append({
            "Server FQDN": fqdn or normalize_str(hw.get("server_fqdn", "")),
            "IP Address": normalize_str(link.get("server_ip", hw.get("server_ip", ""))),
            "Environment": normalize_str(link.get("environment", hw.get("environment", ""))),
            "Virtual": normalize_str(virtual),
            "OS": normalize_str(link.get("operating_system", hw.get("operating_system", ""))),
            "vCPUs": cpu,
            "RAM (GB)": parse_ram_to_gb(ram_value),
            "Allocated Disk (GB)": allocated_gb,
            "In-Use Disk (GB)": used_gb,
            "Hardware Source": hw.get("hardware_source", "None (Unmatched)"),
        })

    servers_df = pd.DataFrame(output, columns=["Server FQDN", "IP Address", "Environment", "Virtual", "OS", "vCPUs", "RAM (GB)", "Allocated Disk (GB)", "In-Use Disk (GB)", "Hardware Source"])
    virtual = servers_df["Virtual"].fillna("").astype(str).str.casefold().isin(["true", "yes", "1", "virtual"])
    rollup = {
        "Total Servers": len(servers_df),
        "Total vCPUs": int(servers_df["vCPUs"].sum()) if not servers_df.empty else 0,
        "Total RAM (GB)": round(servers_df["RAM (GB)"].sum(), 1) if not servers_df.empty else 0.0,
        "Total Allocated Disk (GB)": round(servers_df["Allocated Disk (GB)"].sum(), 1) if not servers_df.empty else 0.0,
        "Total In-Use Disk (GB)": round(servers_df["In-Use Disk (GB)"].sum(), 1) if not servers_df.empty else 0.0,
        "Virtual Servers": int(virtual.sum()),
        "Physical Servers": int((~virtual).sum()),
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

