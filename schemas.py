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
        col_str = " ".join([str(c) for c in filename_or_text]).lower()
        clean_cols = normalize_name(col_str)
        if "u_business_application_1" in col_str or "baasserver" in clean_cols:
            return "BA-AS-A-SERVER"
        elif "cmdbciserver" in clean_cols or ("cpu_core_count" in col_str and "fqdn" in col_str):
            return "CMDB-CI-SERVER"
        elif "armservicenow" in clean_cols or ("arm" in col_str and "service" in col_str):
            return "ARM SERVICE NOW FILE"
        return "Custom / Unknown"

    clean = normalize_name(filename_or_text)

    if check_filename_includes(clean, "ba_as_server") or check_filename_includes(clean, "ba_as_a_server"):
        return "BA-AS-A-SERVER"
    elif check_filename_includes(clean, "cmdb_ci_server"):
        return "CMDB-CI-SERVER"
    elif check_filename_includes(clean, "ARM Service now") or ("arm" in clean and "service" in clean):
        return "ARM SERVICE NOW FILE"

    return "Custom / Unknown"

