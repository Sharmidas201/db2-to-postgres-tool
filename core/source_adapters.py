"""Configurable workbook adapters and canonical field mappings.

Adapters describe source structure only. They never depend on example record values.
Each adapter maps source headers to canonical fields used by the assessment UI.
"""

from core.schemas import normalize_name


SOURCE_ADAPTERS = {
    "ARM SERVICE NOW FILE": {
        "entity": "application",
        "required": ["application_id", "application_name"],
        "signatures": ["number", "name", "businesscriticality", "installstatus"],
        "fields": {
            "number": "application_id", "u_number": "application_id",
            "name": "application_name", "applicationfamily": "application_family",
            "businesscriticality": "business_criticality", "installstatus": "install_status",
            "environment": "environment", "architecturetype": "architecture_type",
            "itapplicationowner": "application_owner", "businessowner": "business_owner",
            "technologyrto": "recovery_time_objective", "technologyrpo": "recovery_point_objective",
            "technologyrecoverytimeobjectivetechnologyrto": "recovery_time_objective",
            "technologyrecoverypointobjectivetechnologyrpo": "recovery_point_objective",
        },
    },
    "BA-AS-A-SERVER": {
        "entity": "application_server_relationship",
        "required": ["application_id", "server_fqdn"],
        "signatures": ["ubusinessapplication1number", "userver1fqdn"],
        "fields": {
            "ubusinessapplication1number": "application_id", "number": "application_id",
            "ubusinessapplication1": "application_name", "userver1fqdn": "server_fqdn",
            "fqdn": "server_fqdn", "userver1ipaddress": "server_ip", "ipaddress": "server_ip",
            "userver1virtual": "is_virtual", "virtual": "is_virtual",
            "userver1environment": "environment", "environment": "environment",
            "userver1os": "operating_system", "os": "operating_system", "userver1ram": "memory",
        },
    },
    "CMDB-CI-SERVER": {
        "entity": "server",
        "required": ["server_fqdn"],
        "signatures": ["fqdn", "cpucorecount", "ram", "diskspace"],
        "fields": {
            "fqdn": "server_fqdn", "name": "server_name", "hostname": "server_name",
            "ipaddress": "server_ip", "cpucorecount": "cpu_cores", "ram": "memory",
            "diskspace": "allocated_storage", "os": "operating_system", "virtual": "is_virtual",
            "environment": "environment", "operationalstatus": "operational_status",
        },
    },
    "AXONIUS DEVICES": {
        "entity": "server",
        "required": ["server_fqdn"],
        "signatures": ["aggregatedpreferredhostnamefqdn", "aggregatedpreferredtotalcpucores", "aggregatedpreferredtotalramgb"],
        "fields": {
            "aggregatedpreferredhostnamefqdn": "server_fqdn",
            "aggregatedpreferredhostname": "server_name",
            "aggregatedpreferredtotalcpucores": "cpu_cores",
            "aggregatedpreferredtotalramgb": "memory_gb",
            "aggregatedpreferredtotaldiskspacegb": "allocated_storage_gb",
            "aggregatedpreferredisvirtual": "is_virtual",
            "aggregatedpreferredosfullstring": "operating_system",
            "aggregatedpreferredriskscore": "risk_score",
        },
    },
    "RV_TOOLS": {
        "entity": "server",
        "required": ["server_name"],
        "signatures": ["vm", "cpus", "memory", "totaldiskcapacitymib"],
        "fields": {
            "vm": "server_name", "dnsname": "server_fqdn", "primaryipaddress": "server_ip",
            "cpus": "cpu_cores", "memory": "memory_gb", "totaldiskcapacitymib": "allocated_storage_mib",
            "inusemib": "used_storage_mib", "osaccordingtotheconfigurationfile": "operating_system",
            "powerstate": "operational_status", "datacenter": "datacenter", "cluster": "cluster",
        },
    },
    "VISUAL-GROUP": {
        "entity": "application",
        "required": ["application_id", "application_name"],
        "signatures": ["number", "displayname", "hostname"],
        "fields": {
            "number": "application_id", "displayname": "application_name", "name": "application_name",
            "environment": "environment", "businesscriticality": "business_criticality",
            "architecturetype": "architecture_type", "itapplicationowner": "application_owner",
            "resiliencyclass": "resiliency_class", "hostname": "server_fqdn",
        },
    },
    "SIZING REPORT": {
        "entity": "server",
        "required": ["server_fqdn"],
        "signatures": ["serverfqdn", "vcpus", "ramgb", "allocateddiskgb"],
        "fields": {
            "serverfqdn": "server_fqdn", "ipaddress": "server_ip", "environment": "environment",
            "virtual": "is_virtual", "os": "operating_system", "vcpus": "cpu_cores",
            "ramgb": "memory_gb", "allocateddiskgb": "allocated_storage_gb",
            "inusediskgb": "used_storage_gb", "hardwaresource": "hardware_source",
        },
    },
}


def source_for_columns(columns):
    """Return the best matching source adapter, or Custom / Unknown."""
    available = {normalize_name(column) for column in columns}
    ranked = []
    for source, adapter in SOURCE_ADAPTERS.items():
        signatures = adapter["signatures"]
        matched = sum(signature in available for signature in signatures)
        if matched == len(signatures):
            ranked.append((matched, source))
    return max(ranked)[1] if ranked else "Custom / Unknown"


def normalize_frame(df, source, filename="", overrides=None):
    """Map known columns to canonical fields while retaining per-value lineage.

    Unmapped source columns are retained as ``extra:<column>`` fields so no source
    attributes are discarded. A companion lineage map identifies the original
    file and column for every canonical field.
    """
    import pandas as pd

    adapter = SOURCE_ADAPTERS.get(source)
    if not adapter:
        return df.copy(), {}
    mapped = {}
    lineage = {}
    overrides = overrides or {}
    for column in df.columns:
        canonical = overrides.get(str(column), adapter["fields"].get(normalize_name(column)))
        target = canonical or f"extra:{column}"
        if target in mapped.values():
            continue
        mapped[column] = target
        if canonical:
            lineage[canonical] = {"file": filename, "column": str(column)}
    normalized = df.rename(columns=mapped).copy()
    normalized.attrs["source_lineage"] = lineage
    normalized.attrs["source_adapter"] = source
    return normalized, lineage


def validate_source(df, source, overrides=None):
    """Return missing required canonical fields and unmapped original headers."""
    adapter = SOURCE_ADAPTERS.get(source)
    if not adapter:
        return {"missing_required": [], "unmapped_columns": list(map(str, df.columns))}
    overrides = overrides or {}
    mapped_headers = {overrides.get(str(c), adapter["fields"].get(normalize_name(c))) for c in df.columns}
    missing = [field for field in adapter["required"] if field not in mapped_headers]
    unmapped = [str(c) for c in df.columns if not overrides.get(str(c), adapter["fields"].get(normalize_name(c)))]
    return {"missing_required": missing, "unmapped_columns": unmapped}
