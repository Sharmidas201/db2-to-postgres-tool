"""
Dataset schemas and signature definitions based on schema.md.
Used for automatic dataset recognition based on filename keyword matching.
"""

import re

KNOWN_SCHEMAS = {
    "ARM SERVICE NOW FILE": {
        "description": "Application inventory, ownership, criticality, and metadata",
        "key_columns": [
            "Number", "Name", "Business criticality", "Install Status", 
            "Environment", "Application family", "IT Application owner"
        ],
        "primary_id": "Number",
        "keyword": "ARM Service now"
    },
    "BA-AS-A-SERVER": {
        "description": "Business application to service to server mapping",
        "key_columns": [
            "u_business_application_1.number", "u_server_1.fqdn", 
            "u_server_1.ip_address", "u_business_application_1", "u_server_1"
        ],
        "primary_id": "u_business_application_1.number",
        "keyword": "ba_as_server"
    },
    "CMDB-CI-SERVER": {
        "description": "Enterprise configuration database (physical & cloud servers)",
        "key_columns": [
            "fqdn", "cpu_core_count", "ram", "disk_space", "operational_status", "name"
        ],
        "primary_id": "fqdn",
        "keyword": "cmdb_ci_server"
    },
    "AXONIUS DEVICES": {
        "description": "Device inventory with compute, memory, storage, and operating system attributes",
        "key_columns": ["Aggregated: Preferred Host Name (FQDN)", "Aggregated: Preferred Total CPU Cores", "Aggregated: Preferred Total RAM (GB)"],
        "primary_id": "Aggregated: Preferred Host Name (FQDN)",
        "keyword": "axonius"
    },
    "RV_TOOLS": {
        "description": "VMware virtual machine inventory with compute and storage attributes",
        "key_columns": ["VM", "DNS Name", "CPUs", "Memory", "Total disk capacity MiB"],
        "primary_id": "VM",
        "keyword": "rvtools"
    },
    "VISUAL-GROUP": {
        "description": "Application portfolio, grouping, and dependency inventory",
        "key_columns": ["Number", "DisplayName", "Hostname"],
        "primary_id": "Number",
        "keyword": "visualgroup"
    },
    "SIZING REPORT": {
        "description": "Previously generated application hardware sizing report",
        "key_columns": ["Server FQDN", "vCPUs", "RAM (GB)", "Allocated Disk (GB)"],
        "primary_id": "Server FQDN",
        "keyword": "sizingreport"
    }
}


def normalize_name(text: str) -> str:
    """Converts string to lowercase and removes all non-alphanumeric special characters."""
    return re.sub(r'[^a-z0-9]', '', str(text).lower())


def check_filename_includes(filename: str, keyword: str) -> bool:
    """
    Checks whether a filename includes a keyword using a lowercase match
    with special characters removed.
    """
    clean_filename = normalize_name(filename)
    clean_keyword = normalize_name(keyword)
    return clean_keyword in clean_filename


def detect_schema(filename_or_text):
    """
    Identifies the dataset schema based on lowercase match with special characters removed:
    - 'ba_as_server' -> BA-AS-A-SERVER
    - 'cmdb_ci_server' -> CMDB-CI-SERVER
    - 'ARM Service now' (or 'arm' and 'service') -> ARM SERVICE NOW FILE
    """
    if not isinstance(filename_or_text, str):
        # Fallback if an iterable of column names was passed
        from core.source_adapters import source_for_columns
        return source_for_columns(filename_or_text)

    clean = normalize_name(filename_or_text)

    if check_filename_includes(clean, "ba_as_server") or check_filename_includes(clean, "ba_as_a_server"):
        return "BA-AS-A-SERVER"
    elif check_filename_includes(clean, "cmdb_ci_server"):
        return "CMDB-CI-SERVER"
    elif "axonius" in clean:
        return "AXONIUS DEVICES"
    elif "rvtools" in clean or "rvtoolsexport" in clean:
        return "RV_TOOLS"
    elif "visualgroup" in clean:
        return "VISUAL-GROUP"
    elif "sizingreport" in clean:
        return "SIZING REPORT"
    elif check_filename_includes(clean, "ARM Service now") or ("arm" in clean and "service" in clean):
        return "ARM SERVICE NOW FILE"

    return "Custom / Unknown"

