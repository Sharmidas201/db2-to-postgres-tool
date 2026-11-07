"""
Sample mock data generator matching the schema definitions in schema.md.
Allows testing the UI immediately without having real data files.
"""

import pandas as pd


def generate_sample_datasets():
    """Generates a dict of sample DataFrames matching schema.md datasets."""

    # 1. ARM SERVICE NOW FILE
    arm_data = {
        "Number": ["APP0001", "APP0002", "APP0003", "APP0004"],
        "Name": ["Customer Portal", "Core ERP", "Analytics Warehouse", "Identity Broker"],
        "Application family": ["Commercial", "Finance", "Data Science", "Security"],
        "Install Status": ["Installed", "Installed", "Installed", "Under Review"],
        "Environment": ["Production", "Production", "Non-Production", "Production"],
        "Business criticality": ["Critical", "Critical", "Medium", "High"],
        "Architecture type": ["N-Tier", "Client-Server", "Microservices", "SOA"],
        "IT Application owner": ["alice@company.com", "bob@company.com", "charlie@company.com", "dan@company.com"],
        "Data classification": ["Confidential", "Restricted", "Internal", "Restricted"],
    }
    df_arm = pd.DataFrame(arm_data)

    # 2. BA-AS-A-SERVER
    ba_data = {
        "u_business_application_1.number": ["APP0001", "APP0001", "APP0002", "APP0003", "APP0004"],
        "u_business_application_1": ["Customer Portal", "Customer Portal", "Core ERP", "Analytics Warehouse", "Identity Broker"],
        "u_server_1.fqdn": [
            "web01.prod.corp.local",
            "db01.prod.corp.local",
            "erp-app01.prod.corp.local",
            "spark-worker01.data.corp.local",
            "auth01.sec.corp.local"
        ],
        "u_server_1.ip_address": ["10.10.1.20", "10.10.1.21", "10.10.2.15", "10.20.5.101", "10.30.1.50"],
        "u_server_1.virtual": ["true", "true", "false", "true", "true"],
        "u_server_1.environment": ["Production", "Production", "Production", "Non-Production", "Production"],
        "u_server_1.os": ["Red Hat Enterprise Linux 8", "Windows Server 2022", "Windows Server 2019", "Ubuntu 22.04 LTS", "Windows Server 2022"],
    }
    df_ba = pd.DataFrame(ba_data)

    # 3. RV_TOOLS (VMware VMs)
    rv_data = {
        "VM": ["web01-vm", "db01-vm", "spark-worker01-vm", "auth01-vm"],
        "DNS Name": [
            "web01.prod.corp.local",
            "db01.prod.corp.local",
            "spark-worker01.data.corp.local",
            "auth01.sec.corp.local"
        ],
        "Powerstate": ["poweredOn", "poweredOn", "poweredOn", "poweredOn"],
        "CPUs": [4, 16, 8, 4],
        "Memory": [16384, 65536, 32768, 16384],  # In MB
        "Total disk capacity MiB": [204800, 1048576, 512000, 102400],
        "In Use MiB": [85000, 620000, 240000, 45000],
        "Datacenter": ["DC-East", "DC-East", "DC-West", "DC-East"],
        "Cluster": ["Cluster-Web", "Cluster-DB", "Cluster-Data", "Cluster-Auth"],
        "Host": ["esxi-01.corp.local", "esxi-02.corp.local", "esxi-09.corp.local", "esxi-03.corp.local"]
    }
    df_rv = pd.DataFrame(rv_data)

    # 4. CMDB-CI-SERVER (Physical & Cloud fallback)
    cmdb_data = {
        "name": ["erp-app01", "web01", "db01", "auth01"],
        "fqdn": [
            "erp-app01.prod.corp.local",
            "web01.prod.corp.local",
            "db01.prod.corp.local",
            "auth01.sec.corp.local"
        ],
        "operational_status": ["Operational", "Operational", "Operational", "Operational"],
        "virtual": ["false", "true", "true", "true"],
        "cpu_core_count": [32, 4, 16, 4],
        "ram": ["128 GB", "16 GB", "64 GB", "16 GB"],
        "disk_space": [2048, 200, 1000, 100],  # In GB
        "os": ["Windows Server 2019", "Red Hat Enterprise Linux 8", "Windows Server 2022", "Windows Server 2022"],
        "manufacturer": ["Dell Inc.", "VMware, Inc.", "VMware, Inc.", "VMware, Inc."],
        "model_id": ["PowerEdge R740", "VMware Virtual Platform", "VMware Virtual Platform", "VMware Virtual Platform"]
    }
    df_cmdb = pd.DataFrame(cmdb_data)

    # 5. AXONIUS DEVICES
    axonius_data = {
        "Aggregated: Preferred Host Name (FQDN)": [
            "web01.prod.corp.local",
            "db01.prod.corp.local",
            "erp-app01.prod.corp.local",
            "spark-worker01.data.corp.local",
            "auth01.sec.corp.local"
        ],
        "Aggregated: Preferred Total CPU Cores": [4, 16, 32, 8, 4],
        "Aggregated: Preferred Total RAM (GB)": [16, 64, 128, 32, 16],
        "Aggregated: Preferred Total Disk Space (GB)": [200, 1024, 2048, 500, 100],
        "Aggregated: Preferred OS: Full String": [
            "Red Hat Enterprise Linux 8.8",
            "Microsoft Windows Server 2022 Standard",
            "Microsoft Windows Server 2019 Datacenter",
            "Ubuntu 22.04.3 LTS",
            "Microsoft Windows Server 2022 Standard"
        ]
    }
    df_axonius = pd.DataFrame(axonius_data)

    return {
        "ARM SERVICE NOW FILE.xlsx": df_arm,
        "BA-AS-A-SERVER.xlsx": df_ba,
        "RV_TOOLS.xlsx": df_rv,
        "CMDB-CI-SERVER.xlsx": df_cmdb,
        "AXONIUS DEVICES.xlsx": df_axonius
    }
