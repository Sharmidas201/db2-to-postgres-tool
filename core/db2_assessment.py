"""Offline Db2 assessment intake for DBA-provided catalog exports.

The module has no database connectivity. It validates a platform-neutral export
bundle so exports from Db2 LUW, Db2 for z/OS, and Db2 for i can be assessed through
the same normalized object and dependency model.
"""

import io
import json
import zipfile
from pathlib import PurePosixPath

import pandas as pd

from core.db2_rules import (
    evaluate_column_rules,
    evaluate_object_rules,
    estimate_target_storage,
    readiness_label,
)


PLATFORMS = {
    "Db2 LUW": "Db2 for Linux, UNIX, and Windows",
    "Db2 for z/OS": "Db2 subsystem running on z/OS",
    "Db2 for i": "Db2 relational database on IBM i",
}

CSV_FIELDS = {
    "objects": [
        "object_type", "catalog_name", "schema_name", "object_name", "specific_name",
        "status", "created_at", "last_altered_at", "source_catalog",
    ],
    "columns": [
        "table_catalog", "table_schema", "table_name", "column_name", "ordinal_position",
        "data_type", "length", "precision", "scale", "nullable", "default_expression",
        "generated_expression",
    ],
    "dependencies": [
        "dependent_type", "dependent_catalog", "dependent_schema", "dependent_name",
        "referenced_type", "referenced_catalog", "referenced_schema", "referenced_name",
        "dependency_type", "capture_method",
    ],
    "metrics": [
        "scope_type", "catalog_name", "schema_name", "object_name", "metric_name",
        "metric_value", "unit", "observed_at",
    ],
}

REQUIRED_FIELDS = {
    "objects": ["object_type", "schema_name", "object_name"],
    "columns": ["table_schema", "table_name", "column_name", "data_type"],
    "dependencies": [
        "dependent_type", "dependent_schema", "dependent_name",
        "referenced_type", "referenced_schema", "referenced_name",
    ],
    "metrics": ["scope_type", "metric_name", "metric_value", "unit"],
}

PLATFORM_GUIDANCE = {
    "Db2 LUW": "Start with SYSCAT catalog views. Common dependency exports include TABDEP, ROUTINEDEP, PACKAGEDEP, and TRIGDEP.",
    "Db2 for z/OS": "Start with SYSIBM catalog tables. Dependency coverage can involve SYSDEPENDENCIES, SYSVIEWDEP, SYSPACKDEP, and version or function-level-specific catalogs.",
    "Db2 for i": "Start with QSYS2 catalog views, including SYSVIEWDEP, SYSROUTINEDEP, SYSTRIGDEP, and SYSCSTDEP.",
}


def _decode_csv(raw_bytes):
    """Read UTF-8 CSV exports, tolerating a UTF-8 BOM."""
    return pd.read_csv(io.BytesIO(raw_bytes), encoding="utf-8-sig", dtype=str, keep_default_na=False)


def load_bundle(uploaded_file):
    """Read a .zip assessment bundle with manifest.json and canonical CSV files."""
    errors = []
    frames = {}
    manifest = {}
    try:
        with zipfile.ZipFile(uploaded_file) as archive:
            for member in archive.namelist():
                if member.endswith("/"):
                    continue
                basename = PurePosixPath(member).name.lower()
                if basename == "manifest.json":
                    try:
                        manifest = json.loads(archive.read(member).decode("utf-8-sig"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        errors.append(f"manifest.json could not be read: {exc}")
                elif basename in {f"{name}.csv" for name in CSV_FIELDS}:
                    key = basename[:-4]
                    if key in frames:
                        errors.append(f"More than one {basename} was found in the bundle; only the first was loaded.")
                        continue
                    try:
                        frames[key] = _decode_csv(archive.read(member))
                    except Exception as exc:
                        errors.append(f"{member} could not be read as CSV: {exc}")
    except (zipfile.BadZipFile, OSError) as exc:
        errors.append(f"Bundle is not a readable ZIP file: {exc}")
    return manifest, frames, errors


def load_csv_uploads(uploaded_files):
    """Read individually uploaded canonical CSV files by their filename stem."""
    frames, errors = {}, []
    for uploaded in uploaded_files or []:
        key = PurePosixPath(uploaded.name).stem.lower()
        if key not in CSV_FIELDS:
            errors.append(f"Ignored `{uploaded.name}`: expected one of {', '.join(name + '.csv' for name in CSV_FIELDS)}.")
            continue
        if key in frames:
            errors.append(f"Duplicate `{key}.csv` upload; only the first was loaded.")
            continue
        try:
            frames[key] = _decode_csv(uploaded.getvalue())
        except Exception as exc:
            errors.append(f"`{uploaded.name}` could not be read as CSV: {exc}")
    return frames, errors


def validate_assessment(
    platform,
    source_version,
    extracted_at,
    frames,
    target_version="16",
    target_service="PostgreSQL (self-managed)",
    growth_percent=0,
    headroom_percent=20,
    target_storage_gib=None,
):
    """Validate files and derive evidence-based coverage and findings."""
    errors = []
    coverage = []
    normalized = {}
    for name, required in REQUIRED_FIELDS.items():
        frame = frames.get(name)
        if frame is None:
            coverage.append({"Area": name.title(), "Status": "Not provided", "Rows": 0, "Missing required fields": ", ".join(required)})
            continue
        # Header matching is case-insensitive and ignores spaces, underscores, and punctuation.
        actual = {"".join(char for char in str(column).lower() if char.isalnum()): column for column in frame.columns}
        rename = {}
        for canonical in CSV_FIELDS[name]:
            compact = "".join(char for char in canonical.lower() if char.isalnum())
            if compact in actual:
                rename[actual[compact]] = canonical
        frame = frame.rename(columns=rename).copy()
        missing = [field for field in required if field not in frame.columns]
        if missing:
            errors.append(f"{name}.csv is missing required columns: {', '.join(missing)}")
        coverage.append({
            "Area": name.title(),
            "Status": "Ready" if not missing and len(frame) else "Needs attention" if len(frame) else "Empty",
            "Rows": len(frame),
            "Missing required fields": ", ".join(missing) if missing else "None",
        })
        normalized[name] = frame

    findings = []

    def add_finding(severity, category, title, detail, recommendation):
        findings.append({"Severity": severity, "Category": category, "Finding": title, "Evidence": detail, "Next step": recommendation})

    if platform not in PLATFORMS:
        errors.append("Select a supported Db2 platform.")
    if not source_version.strip():
        errors.append("Provide the Db2 version or function level.")
    if not extracted_at.strip():
        errors.append("Provide the metadata extraction date.")

    objects = normalized.get("objects")
    columns = normalized.get("columns")
    dependencies = normalized.get("dependencies")
    metrics = normalized.get("metrics")

    if objects is None or objects.empty:
        add_finding("High", "Coverage", "No Db2 object inventory", "No object rows were imported.", "Request an object inventory export before estimating migration scope.")
    elif "object_type" in objects.columns:
        counts = objects["object_type"].str.strip().str.upper().value_counts()
        routines = int(counts.get("PROCEDURE", 0) + counts.get("FUNCTION", 0) + counts.get("ROUTINE", 0))
        add_finding("Info", "Inventory", "Db2 inventory loaded", f"{len(objects):,} objects across {objects['object_type'].nunique():,} object types; {routines:,} routines detected.", "Review object counts and confirm that the export covers the full database scope.")
        object_key_cols = [c for c in ["catalog_name", "schema_name", "object_name", "object_type"] if c in objects.columns]
        if len(object_key_cols) >= 3:
            dupes = objects.duplicated(subset=object_key_cols, keep=False)
            if dupes.any():
                add_finding("Warning", "Data quality", "Duplicate object identifiers", f"{int(dupes.sum()):,} rows share a catalog/schema/name/type identifier.", "Confirm whether duplicates are separate versions, partitions, or repeated export rows.")

    if columns is None or columns.empty:
        add_finding("High", "Coverage", "Column and data type details missing", "No column-level metadata was imported.", "Request table-column metadata; without it, data-type and column-level compatibility cannot be assessed.")
    elif "data_type" in columns.columns:
        add_finding("Info", "Inventory", "Column metadata loaded", f"{len(columns):,} columns and {columns['data_type'].str.upper().nunique():,} distinct source data types detected.", "Use this inventory for a later Db2-to-PostgreSQL type compatibility ruleset.")

    if dependencies is None or dependencies.empty:
        add_finding("High", "Coverage", "Dependency metadata missing", "No dependency edges were imported.", "Request view, routine, trigger, package, constraint, and object dependency exports for this platform/version.")
    else:
        add_finding("Info", "Dependencies", "Dependency edges loaded", f"{len(dependencies):,} dependency rows were imported.", "Validate edge coverage against the source platform's catalog documentation and supplement with application/runtime dependencies.")
        if objects is not None and not objects.empty and all(c in objects for c in ("schema_name", "object_name", "object_type")):
            known = set(zip(objects["schema_name"].str.upper(), objects["object_name"].str.upper(), objects["object_type"].str.upper()))
            dangling = 0
            for _, edge in dependencies.iterrows():
                for prefix in ("dependent", "referenced"):
                    required = [f"{prefix}_schema", f"{prefix}_name", f"{prefix}_type"]
                    if all(field in edge.index for field in required):
                        key = tuple(str(edge[field]).strip().upper() for field in required)
                        if all(key) and key not in known:
                            dangling += 1
            if dangling:
                add_finding("Warning", "Data quality", "Dependency endpoints absent from object inventory", f"{dangling:,} dependency endpoints did not match an imported object identifier.", "Check naming/type normalization and request any missing objects or catalog exports.")

    if metrics is None or metrics.empty:
        add_finding("Medium", "Coverage", "Database size and workload metrics missing", "No storage, row-count, or workload metrics were imported.", "Request database/table size and any available workload statistics before target sizing.")
    else:
        add_finding("Info", "Inventory", "Metrics loaded", f"{len(metrics):,} metric rows were imported.", "Confirm units, collection window, and whether metrics represent peak or average values.")

    has_routines = objects is not None and "object_type" in objects.columns and objects["object_type"].str.upper().isin(["PROCEDURE", "FUNCTION", "ROUTINE", "TRIGGER", "PACKAGE"]).any()
    if has_routines:
        add_finding("Info", "Scope", "Routine or package objects present", "The inventory includes executable Db2 object types. DDL/source text was not requested in this intake phase.", "Track routines, triggers, and packages for a later DDL and procedural-code review.")
    add_finding("Info", "Scope", "No schema conversion performed", "This milestone inventories evidence and dependencies; it does not convert DDL or claim PostgreSQL compatibility.", "Run compatibility rules after the platform export contract and rule sources are approved.")

    rule_results = evaluate_column_rules(columns, target_version=target_version)
    for _, rule_result in rule_results[rule_results["Status"].isin(["Review required", "Potential incompatibility", "Insufficient evidence"])].iterrows():
        findings.append({
            "Severity": rule_result["Severity"],
            "Category": "Type compatibility",
            "Finding": f"{rule_result['Rule ID']}: {rule_result['Status']}",
            "Object": ".".join(part for part in (rule_result["Schema"], rule_result["Table"], rule_result["Column"]) if part),
            "Evidence": rule_result["Evidence"],
            "Next step": rule_result["Recommendation"],
            "Effort": rule_result["Effort"],
        })

    object_rule_results = evaluate_object_rules(objects, target_service)
    for _, object_result in object_rule_results.iterrows():
        findings.append({
            "Severity": object_result["Severity"],
            "Category": "Target service compatibility",
            "Finding": f"{object_result['Rule ID']}: {object_result['Status']}",
            "Object": object_result["Object"],
            "Evidence": object_result["Evidence"],
            "Next step": object_result["Recommendation"],
            "Effort": "Requires target design review",
        })

    sizing = estimate_target_storage(metrics, growth_percent, headroom_percent, target_storage_gib)
    for _, sizing_result in sizing[sizing["Status"].isin(["Review required", "Insufficient evidence"])].iterrows():
        findings.append({
            "Severity": "Warning" if sizing_result["Status"] == "Review required" else "Medium",
            "Category": "Target sizing",
            "Finding": f"Storage estimate: {sizing_result['Status']}",
            "Evidence": sizing_result["Evidence"],
            "Next step": sizing_result["Recommendation"],
            "Effort": "Requires source metrics and target design",
        })

    coverage_frame = pd.DataFrame(coverage)
    findings_frame = pd.DataFrame(findings)
    readiness_rules = pd.concat([rule_results[["Status"]], object_rule_results[["Status"]]], ignore_index=True)
    readiness = readiness_label(coverage_frame, readiness_rules)

    context = {
        "platform": platform,
        "platform_description": PLATFORMS.get(platform, ""),
        "source_version": source_version.strip(),
        "extracted_at": extracted_at.strip(),
        "object_count": len(objects) if objects is not None else 0,
        "column_count": len(columns) if columns is not None else 0,
        "dependency_count": len(dependencies) if dependencies is not None else 0,
        "metric_count": len(metrics) if metrics is not None else 0,
        "preliminary_readiness": readiness,
        "target_version": str(target_version),
        "target_service": str(target_service),
        "growth_percent": float(growth_percent),
        "headroom_percent": float(headroom_percent),
        "target_storage_gib": target_storage_gib,
    }
    return {
        "context": context,
        "frames": normalized,
        "coverage": coverage_frame,
        "findings": findings_frame,
        "rule_results": rule_results,
        "object_rule_results": object_rule_results,
        "sizing": sizing,
        "errors": errors,
    }


def make_template_bundle():
    """Create a header-only ZIP that a DBA can use as the normalized export contract."""
    output = io.BytesIO()
    manifest = {
        "platform": "",
        "source_version": "",
        "source_name": "",
        "extracted_at": "YYYY-MM-DD",
        "extraction_method": "DBA-provided catalog export",
        "notes": "Populate the CSV templates. Preserve one row per object, column, dependency edge, or metric.",
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        for name, fields in CSV_FIELDS.items():
            archive.writestr(f"{name}.csv", ",".join(fields) + "\n")
        archive.writestr(
            "README.txt",
            "Db2 assessment intake bundle\n\n"
            "This is an offline metadata format; it contains no database connection settings.\n"
            "Select Db2 LUW, Db2 for z/OS, or Db2 for i in the assessment UI.\n"
            "Populate each CSV with catalog export rows. Leave unavailable optional fields blank.\n"
            "Capture dependencies as one row per dependent-object -> referenced-object edge.\n"
            "Keep catalog/schema/object names and platform-specific source_catalog values intact.\n"
            "Do not include passwords or connection strings.\n",
        )
    output.seek(0)
    return output.getvalue()


def make_demo_bundle(platform="Db2 LUW"):
    """Create a platform-specific fictional export bundle for UI demos and tests."""
    demo_data = {
        "Db2 LUW": {
            "version": "11.5 synthetic demo", "database": "DEMO_LUW", "schema": "APP",
            "objects": [
                ["TABLE", "CUSTOMER", "SYSCAT.TABLES"], ["TABLE", "ORDERS", "SYSCAT.TABLES"],
                ["SEQUENCE", "ORDER_SEQ", "SYSCAT.SEQUENCES"], ["PROCEDURE", "CLOSE_ORDERS", "SYSCAT.ROUTINES"],
            ],
            "columns": [
                ["CUSTOMER", "CUSTOMER_ID", "INTEGER", "4", "10", "0", "N", "", ""],
                ["CUSTOMER", "CUSTOMER_NAME", "VARCHAR", "100", "", "", "Y", "", ""],
                ["CUSTOMER", "CREATED_AT", "TIMESTAMP", "10", "", "", "N", "CURRENT TIMESTAMP", ""],
                ["ORDERS", "ORDER_ID", "BIGINT", "8", "19", "0", "N", "", ""],
                ["ORDERS", "CUSTOMER_ID", "INTEGER", "4", "10", "0", "N", "", ""],
                ["ORDERS", "TOTAL_AMOUNT", "DECIMAL", "10", "12", "2", "N", "", ""],
            ],
            "dependencies": [
                ["TABLE", "ORDERS", "TABLE", "CUSTOMER", "FOREIGN KEY", "SYSCAT.REFERENCES"],
                ["TABLE", "ORDERS", "SEQUENCE", "ORDER_SEQ", "IDENTITY/SEQUENCE", "SYSCAT.TABDEP"],
                ["PROCEDURE", "CLOSE_ORDERS", "TABLE", "ORDERS", "ROUTINE REFERENCE", "SYSCAT.ROUTINEDEP"],
            ],
            "metrics": [["DATABASE", "", "allocated_size", "268435456", "bytes"], ["TABLE", "CUSTOMER", "row_count", "12000", "rows"], ["TABLE", "ORDERS", "row_count", "98500", "rows"]],
        },
        "Db2 for z/OS": {
            "version": "13 synthetic demo", "database": "DSN8D13A", "schema": "DSN8C13",
            "objects": [
                ["TABLE", "EMP", "SYSIBM.SYSTABLES"], ["TABLE", "DEPT", "SYSIBM.SYSTABLES"],
                ["TABLESPACE", "DSN8S13E", "SYSIBM.SYSTABLESPACE"], ["PROCEDURE", "RAISE_SALARY", "SYSIBM.SYSROUTINES"],
            ],
            "columns": [
                ["EMP", "EMPNO", "CHAR", "6", "", "", "N", "", ""],
                ["EMP", "LASTNAME", "VARCHAR", "40", "", "", "N", "", ""],
                ["EMP", "SALARY", "DECIMAL", "10", "9", "2", "N", "", ""],
                ["EMP", "BONUS_FACTOR", "DECFLOAT(16)", "8", "16", "", "Y", "", ""],
                ["EMP", "HIRE_TS", "TIMESTAMP(12)", "12", "", "", "N", "CURRENT TIMESTAMP", ""],
                ["DEPT", "DEPTNO", "CHAR", "3", "", "", "N", "", ""],
                ["DEPT", "DEPTNAME", "VARCHAR", "36", "", "", "N", "", ""],
            ],
            "dependencies": [
                ["TABLE", "EMP", "TABLE", "DEPT", "FOREIGN KEY", "SYSIBM.SYSRELS"],
                ["PROCEDURE", "RAISE_SALARY", "TABLE", "EMP", "ROUTINE DEPENDENCY", "SYSIBM.SYSROUTINES"],
                ["TABLE", "EMP", "TABLESPACE", "DSN8S13E", "STORAGE PLACEMENT", "SYSIBM.SYSTABLESPACE"],
            ],
            "metrics": [["DATABASE", "", "allocated_size", str(12 * 1024**3), "bytes"], ["TABLE", "EMP", "row_count", "250000", "rows"], ["DATABASE", "", "active_log_size", "2048", "MiB"]],
        },
        "Db2 for i": {
            "version": "7.5 synthetic demo", "database": "DEMO_IBMI", "schema": "SAMPLE",
            "objects": [
                ["TABLE", "EMPLOYEE", "QSYS2.SYSTABLES"], ["TABLE", "DEPARTMENT", "QSYS2.SYSTABLES"],
                ["TRIGGER", "EMPLOYEE_AUDIT", "QSYS2.SYSTRIGGERS"], ["FUNCTION", "GET_DEPT_NAME", "QSYS2.SYSROUTINES"],
            ],
            "columns": [
                ["EMPLOYEE", "EMPNO", "CHAR", "6", "", "", "N", "", ""],
                ["EMPLOYEE", "FIRSTNME", "VARCHAR", "12", "", "", "N", "", ""],
                ["EMPLOYEE", "SALARY", "DECIMAL", "9", "9", "2", "N", "", ""],
                ["EMPLOYEE", "PHOTO", "BLOB", "1048576", "", "", "Y", "", ""],
                ["DEPARTMENT", "DEPTNO", "CHAR", "3", "", "", "N", "", ""],
                ["DEPARTMENT", "DEPTNAME", "VARGRAPHIC", "30", "", "", "N", "", ""],
            ],
            "dependencies": [
                ["TABLE", "EMPLOYEE", "TABLE", "DEPARTMENT", "FOREIGN KEY", "QSYS2.SYSCSTDEP"],
                ["TRIGGER", "EMPLOYEE_AUDIT", "TABLE", "EMPLOYEE", "TRIGGER REFERENCE", "QSYS2.SYSTRIGDEP"],
                ["FUNCTION", "GET_DEPT_NAME", "TABLE", "DEPARTMENT", "ROUTINE REFERENCE", "QSYS2.SYSROUTINEDEP"],
            ],
            "metrics": [["DATABASE", "", "allocated_size", str(3 * 1024**3), "bytes"], ["TABLE", "EMPLOYEE", "row_count", "18500", "rows"], ["DATABASE", "", "used_size", "2.4", "GiB"]],
        },
    }
    if platform not in demo_data:
        raise ValueError(f"Unsupported demo platform: {platform}")
    sample = demo_data[platform]
    database, schema = sample["database"], sample["schema"]
    extracted_at = "2026-11-09"
    demo_manifest = {
        "platform": platform,
        "source_version": sample["version"],
        "source_name": database,
        "extracted_at": extracted_at,
        "extraction_method": "Synthetic fixture; not exported from a real database",
        "notes": f"Fictional {platform} catalog-shaped metadata for UI and ruleset testing.",
    }
    records = {
        "objects": [
            [kind, database, schema, name, "", "VALID", "", "", catalog]
            for kind, name, catalog in sample["objects"]
        ],
        "columns": [],
        "dependencies": [
            [dependent_type, database, schema, dependent_name, referenced_type, database, schema, referenced_name, dep_type, catalog]
            for dependent_type, dependent_name, referenced_type, referenced_name, dep_type, catalog in sample["dependencies"]
        ],
        "metrics": [
            [scope, database, schema if scope == "TABLE" else "", name, metric, value, unit, extracted_at]
            for scope, name, metric, value, unit in sample["metrics"]
        ],
    }
    # Use a deterministic position while keeping the fixture definitions readable.
    table_positions = {}
    records["columns"] = []
    for table, column, data_type, length, precision, scale, nullable, default, generated in sample["columns"]:
        table_positions[table] = table_positions.get(table, 0) + 1
        records["columns"].append([database, schema, table, column, str(table_positions[table]), data_type, length, precision, scale, nullable, default, generated])
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(demo_manifest, indent=2))
        for name, fields in CSV_FIELDS.items():
            frame = pd.DataFrame(records[name], columns=fields)
            archive.writestr(f"{name}.csv", frame.to_csv(index=False))
        archive.writestr(
            "README.txt",
            f"Synthetic {platform} demo bundle. All names, metadata, and counts are fictional.\n"
            "Use this only to demonstrate the intake workflow, not for migration planning.\n",
        )
    output.seek(0)
    return output.getvalue()


def make_report_bytes(assessment):
    """Export assessment coverage, findings, and imported canonical metadata to Excel."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame([assessment["context"]]).to_excel(writer, sheet_name="Assessment", index=False)
        assessment["coverage"].to_excel(writer, sheet_name="Evidence Coverage", index=False)
        assessment["findings"].to_excel(writer, sheet_name="Findings", index=False)
        assessment.get("rule_results", pd.DataFrame()).to_excel(writer, sheet_name="Type Compatibility", index=False)
        assessment.get("object_rule_results", pd.DataFrame()).to_excel(writer, sheet_name="Object Compatibility", index=False)
        assessment.get("sizing", pd.DataFrame()).to_excel(writer, sheet_name="Target Sizing", index=False)
        for name, frame in assessment["frames"].items():
            frame.to_excel(writer, sheet_name=name.title()[:31], index=False)
    output.seek(0)
    return output.getvalue()
