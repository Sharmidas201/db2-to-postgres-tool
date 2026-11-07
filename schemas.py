"""
Dataset schemas and signature definitions based on schema.md.
Used for automatic dataset recognition and column metadata.
"""

KNOWN_SCHEMAS = {
    "ARM SERVICE NOW FILE": {
        "description": "Application inventory, ownership, criticality, and metadata",
        "key_columns": [
            "Number", "Name", "Business criticality", "Install Status", 
            "Environment", "Application family", "IT Application owner"
        ],
        "primary_id": "Number"
    },
    "BA-AS-A-SERVER": {
        "description": "Business application to service to server mapping",
        "key_columns": [
            "u_business_application_1.number", "u_server_1.fqdn", 
            "u_server_1.ip_address", "u_business_application_1", "u_server_1"
        ],
        "primary_id": "u_business_application_1.number"
    },
    "RV_TOOLS": {
        "description": "VMware hypervisor VM inventory, vCPUs, memory, and storage",
        "key_columns": [
            "DNS Name", "VM", "CPUs", "Memory", "Total disk capacity MiB", "In Use MiB"
        ],
        "primary_id": "DNS Name"
    },
    "CMDB-CI-SERVER": {
        "description": "Enterprise configuration database (physical & cloud servers)",
        "key_columns": [
            "fqdn", "cpu_core_count", "ram", "disk_space", "operational_status", "name"
        ],
        "primary_id": "fqdn"
    },
    "AXONIUS DEVICES": {
        "description": "Asset & multi-source reconciliation data",
        "key_columns": [
            "Aggregated: Preferred Host Name (FQDN)",
            "Aggregated: Preferred Total CPU Cores",
            "Aggregated: Preferred Total RAM (GB)"
        ],
        "primary_id": "Aggregated: Preferred Host Name (FQDN)"
    },
    "VISUAL-GROUP": {
        "description": "Visual grouping and architectural relationships",
        "key_columns": [
            "POID", "Contains_Ref_List", "DisplayName", "META_Ref"
        ],
        "primary_id": "POID"
    }
}


def detect_schema(columns):
    """
    Given a list or Index of column names, return the best-matching dataset schema name
    or 'Custom / Unknown' if no strong match is found.
    """
    col_set = {str(c).strip().lower() for c in columns}
    best_match = None
    best_score = 0.0

    for name, spec in KNOWN_SCHEMAS.items():
        spec_keys = {k.lower() for k in spec["key_columns"]}
        matches = sum(1 for k in spec_keys if k in col_set)
        score = matches / len(spec_keys)
        if score > 0.35 and score > best_score:
            best_score = score
            best_match = name

    return best_match or "Custom / Unknown"
