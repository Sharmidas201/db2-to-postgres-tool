"""Evidence-based Db2-to-PostgreSQL compatibility and sizing checks.

Rules compare imported Db2 catalog facts with the selected PostgreSQL target.
Unknown types and semantics are sent for review; no project-specific hard limits
or readiness score are invented here.
"""

import re

import pandas as pd


PG_VERSIONS = ["14", "15", "16", "17", "18"]
PG_VARCHAR_MAX = 10_485_760
PG_NUMERIC_MAX_PRECISION = 1000

# Conservative starter mappings. A mapping says what to investigate/create in
# target DDL; it does not claim automatic schema conversion.
TYPE_RULES = [
    (r"^(SMALLINT|INT2)$", "smallint", "Compatible", "Direct built-in type mapping; verify value range."),
    (r"^(INTEGER|INT|INT4)$", "integer", "Compatible", "Direct built-in type mapping; verify value range."),
    (r"^(BIGINT|INT8)$", "bigint", "Compatible", "Direct built-in type mapping; verify value range."),
    (r"^(DECIMAL|DEC|NUMERIC)(\b|\()", "numeric", "Compatible", "Map precision and scale to PostgreSQL numeric; compare catalog precision and scale."),
    (r"^(REAL|FLOAT\s*\(?(\s*[1-24])?\)?|DOUBLE|DOUBLE PRECISION)$", "real / double precision", "Review required", "Floating-point formats and rounding behavior need workload and value validation."),
    (r"^(CHARACTER VARYING|VARCHAR)(\b|\()", "varchar(n) or text", "Compatible", "Preserve declared length when it is within the selected PostgreSQL type's supported range."),
    (r"^(CHARACTER|CHAR)(\b|\()", "character(n)", "Review required", "Check blank-padding and trailing-space behavior in applications and predicates."),
    (r"^(CLOB|DBCLOB|LONG VARCHAR|LONGVAR)\b", "text", "Review required", "Validate large-value limits, encoding, access patterns, and target storage."),
    (r"^(BLOB|LONG VARBINARY|VARBINARY|BINARY)\b", "bytea", "Review required", "Validate binary payload size, transfer path, and application binding behavior."),
    (r"^XML\b", "xml", "Review required", "Review Db2 XML features, indexing, validation, and application queries."),
    (r"^DECFLOAT\b", "numeric (candidate)", "Review required", "Check exponent range, special values, rounding, and arithmetic semantics."),
    (r"^DATE\b", "date", "Compatible", "Check application date handling and boundary values."),
    (r"^TIME\b", "time / time with time zone", "Review required", "Confirm time-zone semantics and fractional precision."),
    (r"^TIMESTAMP\b", "timestamp / timestamptz", "Review required", "Confirm time-zone semantics and fractional precision; PostgreSQL timestamp precision is at most 6."),
    (r"^(BOOLEAN|CHAR\s*\(\s*1\s*\))$", "boolean (candidate)", "Review required", "Check source values and application conventions before converting to boolean."),
]


def _integer(value):
    value = pd.to_numeric(str(value).strip(), errors="coerce")
    return int(value) if pd.notna(value) else None


def _type_details(raw_type):
    normalized = re.sub(r"\s+", " ", str(raw_type or "").strip().upper())
    match = re.search(r"\((\s*\d+\s*)(?:,\s*(-?\d+)\s*)?\)", normalized)
    inline_length = int(match.group(1)) if match else None
    inline_precision = inline_length if normalized.startswith(("DECIMAL", "DEC", "NUMERIC")) else None
    inline_scale = int(match.group(2)) if match and match.group(2) is not None else None
    return normalized, inline_length, inline_precision, inline_scale


def _column_facts(row):
    raw_type = str(row.get("data_type", "")).strip()
    normalized, inline_length, inline_precision, inline_scale = _type_details(raw_type)
    length = _integer(row.get("length", "")) or inline_length
    precision = _integer(row.get("precision", "")) or inline_precision
    scale = _integer(row.get("scale", ""))
    if scale is None:
        scale = inline_scale
    return normalized, length, precision, scale


def _mapping(source_type):
    if "FOR BIT DATA" in source_type or "BINARY" in source_type:
        return "bytea", "Review required", "Binary representation and application bindings need validation."
    for pattern, target_type, status, note in TYPE_RULES:
        if re.search(pattern, source_type):
            return target_type, status, note
    return "Needs mapping", "Insufficient evidence", "No reviewed mapping exists for this Db2 type; add source and target catalog evidence before classifying it."


def evaluate_column_rules(columns, target_version="16"):
    """Compare column facts against PostgreSQL type capabilities for a version."""
    result_columns = [
        "Rule ID", "Status", "Severity", "Schema", "Table", "Column", "Source type",
        "Source length", "Source precision", "Source scale", "Proposed target type",
        "Evidence", "Recommendation", "Effort", "Documentation",
    ]
    if columns is None or columns.empty or "data_type" not in columns:
        return pd.DataFrame(columns=result_columns)

    pg_version = int(target_version)
    rows = []
    for _, row in columns.iterrows():
        source_type, length, precision, scale = _column_facts(row)
        target_type, status, note = _mapping(source_type)
        schema, table, column = (str(row.get(field, "")).strip() for field in ("table_schema", "table_name", "column_name"))
        object_name = ".".join(part for part in (schema, table, column) if part) or "Unidentified column"
        evidence = f"{object_name}: Db2 {source_type or 'type not supplied'}; proposed PostgreSQL type {target_type}. {note}"
        recommendation = "Confirm with representative values and application behavior; retain the evidence and decision in the assessment."

        if source_type.startswith(("VARCHAR", "CHARACTER VARYING")) and "FOR BIT DATA" not in source_type:
            if length is None:
                status = "Insufficient evidence"
                evidence += " Declared source length is unavailable."
                recommendation = "Re-export the column's declared length from the Db2 catalog."
            elif length > PG_VARCHAR_MAX:
                status = "Potential incompatibility"
                evidence += f" Declared length {length} exceeds PostgreSQL's declared varchar limit {PG_VARCHAR_MAX}."
                recommendation = "Use text/LOB design or split the value after validating actual lengths and target service behavior."
            else:
                target_type = f"varchar({length})"
                evidence += f" Declared length {length} is within PostgreSQL's declared varchar limit {PG_VARCHAR_MAX}."

        if source_type.startswith(("DECIMAL", "DEC", "NUMERIC")):
            if precision is None:
                status = "Insufficient evidence"
                evidence += " Numeric precision is unavailable."
                recommendation = "Re-export numeric precision and scale from the Db2 catalog."
            elif precision > PG_NUMERIC_MAX_PRECISION:
                status = "Potential incompatibility"
                evidence += f" Precision {precision} exceeds PostgreSQL's declared numeric precision limit {PG_NUMERIC_MAX_PRECISION}."
                recommendation = "Validate observed ranges and design an alternate representation or split the value."
            elif scale is not None and scale > precision:
                status = "Review required"
                evidence += f" Scale {scale} exceeds precision {precision}; verify source catalog semantics and values."

        severity = {
            "Compatible": "Info",
            "Review required": "Warning",
            "Potential incompatibility": "High",
            "Insufficient evidence": "Warning",
        }[status]
        if source_type.startswith(("DECIMAL", "DEC", "NUMERIC")):
            pg_doc = f"https://www.postgresql.org/docs/{pg_version}/datatype-numeric.html"
        elif source_type.startswith(("VARCHAR", "CHARACTER", "CHAR")):
            pg_doc = f"https://www.postgresql.org/docs/{pg_version}/datatype-character.html"
        elif source_type.startswith(("DATE", "TIME", "TIMESTAMP")):
            pg_doc = f"https://www.postgresql.org/docs/{pg_version}/datatype-datetime.html"
        else:
            pg_doc = f"https://www.postgresql.org/docs/{pg_version}/datatype.html"
        rows.append({
            "Rule ID": "PG-TYPE-MAPPING",
            "Status": status,
            "Severity": severity,
            "Schema": schema,
            "Table": table,
            "Column": column,
            "Source type": str(row.get("data_type", "")).strip(),
            "Source length": length,
            "Source precision": precision,
            "Source scale": scale,
            "Proposed target type": target_type,
            "Evidence": evidence,
            "Recommendation": recommendation,
            "Effort": "Unknown until DDL and value validation" if status != "Compatible" else "Small",
            "Documentation": pg_doc,
        })
    return pd.DataFrame(rows, columns=result_columns)


def evaluate_object_rules(objects, target_service):
    """Check object features with known target-service constraints."""
    result_columns = ["Rule ID", "Status", "Severity", "Object", "Source feature", "Evidence", "Recommendation", "Documentation"]
    if objects is None or objects.empty or "object_type" not in objects:
        return pd.DataFrame(columns=result_columns)
    if target_service != "Azure Database for PostgreSQL Flexible Server":
        return pd.DataFrame(columns=result_columns)

    rows = []
    for _, row in objects.iterrows():
        object_type = str(row.get("object_type", "")).strip().upper()
        if "TABLESPACE" not in object_type:
            continue
        schema = str(row.get("schema_name", "")).strip()
        name = str(row.get("object_name", "")).strip()
        rows.append({
            "Rule ID": "AZURE-PG-TABLESPACE-SERVICE-LIMIT",
            "Status": "Potential incompatibility",
            "Severity": "High",
            "Object": ".".join(part for part in (schema, name) if part) or object_type,
            "Source feature": object_type,
            "Evidence": "Azure Database for PostgreSQL Flexible Server does not support user-created tablespaces.",
            "Recommendation": "Review the Db2 tablespace's placement and storage role; redesign target placement using the service's supported storage model.",
            "Documentation": "https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/concepts-limits",
        })
    return pd.DataFrame(rows, columns=result_columns)


def estimate_target_storage(metrics, growth_percent=0, headroom_percent=20, target_storage_gib=None):
    """Build a transparent planning estimate from source allocated-size metrics."""
    result_columns = ["Status", "Source allocated GiB", "Growth assumption %", "Headroom assumption %", "Estimated target GiB", "Configured target GiB", "Evidence", "Recommendation"]
    empty = pd.DataFrame(columns=result_columns)
    if metrics is None or metrics.empty:
        return empty
    metric_names = metrics.get("metric_name", pd.Series(dtype=str)).astype(str).str.lower()
    units = metrics.get("unit", pd.Series(dtype=str)).astype(str).str.lower()
    scopes = metrics.get("scope_type", pd.Series(dtype=str)).astype(str).str.upper()
    values = pd.to_numeric(metrics.get("metric_value", pd.Series(dtype=str)), errors="coerce")
    candidates = metrics[metric_names.str.contains(r"allocated_size|used_size|storage_used|database_size|db_size", regex=True) & scopes.isin(["DATABASE", "DB", "SYSTEM"])].copy()
    candidates["_numeric"] = values.loc[candidates.index]
    candidates["_unit"] = units.loc[candidates.index]
    candidates = candidates[candidates["_numeric"].notna()]
    if candidates.empty:
        return pd.DataFrame([{
            "Status": "Insufficient evidence", "Source allocated GiB": None,
            "Growth assumption %": growth_percent, "Headroom assumption %": headroom_percent,
            "Estimated target GiB": None, "Configured target GiB": target_storage_gib,
            "Evidence": "No database-level allocated/used-size metric with a recognized unit was provided.",
            "Recommendation": "Export database-level allocated and used storage from Db2; table row counts alone do not establish a target storage requirement.",
        }], columns=result_columns)

    factors = {"bytes": 1 / (1024 ** 3), "byte": 1 / (1024 ** 3), "kib": 1 / (1024 ** 2), "mib": 1 / 1024, "gib": 1, "gb": 1 / 1.073741824, "tb": 1024 / 1.073741824}
    converted = []
    for _, metric in candidates.iterrows():
        unit = str(metric["_unit"]).strip().lower()
        if unit not in factors:
            continue
        converted.append((float(metric["_numeric"]) * factors[unit], str(metric.get("metric_name", ""))))
    if not converted:
        return pd.DataFrame([{
            "Status": "Insufficient evidence", "Source allocated GiB": None,
            "Growth assumption %": growth_percent, "Headroom assumption %": headroom_percent,
            "Estimated target GiB": None, "Configured target GiB": target_storage_gib,
            "Evidence": "Database-level size metrics were supplied, but their units are not recognized.",
            "Recommendation": "Use bytes, KiB, MiB, GiB, GB, or TB and identify whether the value is allocated or used size.",
        }], columns=result_columns)

    base_gib = max(value for value, _ in converted)
    estimated = base_gib * (1 + float(growth_percent) / 100) * (1 + float(headroom_percent) / 100)
    over_capacity = target_storage_gib is not None and estimated > float(target_storage_gib)
    status = "Review required" if over_capacity else "Estimate available"
    evidence = f"Largest recognized database-level source size metric is {base_gib:.2f} GiB. Estimate applies configured growth and headroom assumptions; it is a planning baseline, not a Db2-to-PostgreSQL physical-size conversion."
    recommendation = "Validate with a representative data load and include indexes, WAL, temporary space, backup/replica requirements, and workload growth in target sizing."
    if over_capacity:
        evidence += f" Estimated need {estimated:.2f} GiB exceeds configured target capacity {float(target_storage_gib):.2f} GiB."
        recommendation = "Select a larger target storage allocation or revise assumptions after a representative migration test."
    return pd.DataFrame([{
        "Status": status, "Source allocated GiB": round(base_gib, 2),
        "Growth assumption %": float(growth_percent), "Headroom assumption %": float(headroom_percent),
        "Estimated target GiB": round(estimated, 2), "Configured target GiB": target_storage_gib,
        "Evidence": evidence, "Recommendation": recommendation,
    }], columns=result_columns)


def readiness_label(coverage, rule_results):
    """Return a conservative status; a ruleset cannot mark a DB migration-ready."""
    required_areas = {"Objects", "Columns"}
    available = set(coverage.loc[coverage["Status"] == "Ready", "Area"]) if not coverage.empty else set()
    if not required_areas.issubset(available):
        return "Insufficient evidence"
    if not rule_results.empty and rule_results["Status"].isin(["Review required", "Potential incompatibility", "Insufficient evidence"]).any():
        return "Review required"
    return "No findings under current rules — assessment incomplete"
