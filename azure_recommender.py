"""
Azure Database for PostgreSQL - Flexible Server Sizing Recommender.
Translates on-premise hardware footprints (IBM Db2 or generic) to optimal Azure Flexible Server SKUs,
applying sizing headroom, MVCC/WAL overhead, and HA architecture recommendations.
Focuses strictly on architectural sizing and technical reasoning without speculative pricing.
"""

import math
from typing import Dict, Any, List, Optional


# Azure Flexible Server SKU Catalog
SKU_CATALOG = [
    # General Purpose (D-Series v6) - 1:4 Core-to-RAM Ratio
    {
        "tier": "General Purpose",
        "family": "D-Series v6",
        "sku": "Standard_D2ds_v6",
        "vcpus": 2,
        "memory_gib": 8,
    },
    {
        "tier": "General Purpose",
        "family": "D-Series v6",
        "sku": "Standard_D4ds_v6",
        "vcpus": 4,
        "memory_gib": 16,
    },
    {
        "tier": "General Purpose",
        "family": "D-Series v6",
        "sku": "Standard_D8ds_v6",
        "vcpus": 8,
        "memory_gib": 32,
    },
    {
        "tier": "General Purpose",
        "family": "D-Series v6",
        "sku": "Standard_D16ds_v6",
        "vcpus": 16,
        "memory_gib": 64,
    },
    {
        "tier": "General Purpose",
        "family": "D-Series v6",
        "sku": "Standard_D32ds_v6",
        "vcpus": 32,
        "memory_gib": 128,
    },
    {
        "tier": "General Purpose",
        "family": "D-Series v6",
        "sku": "Standard_D48ds_v6",
        "vcpus": 48,
        "memory_gib": 192,
    },
    {
        "tier": "General Purpose",
        "family": "D-Series v6",
        "sku": "Standard_D64ds_v6",
        "vcpus": 64,
        "memory_gib": 256,
    },
    {
        "tier": "General Purpose",
        "family": "D-Series v6",
        "sku": "Standard_D96ds_v6",
        "vcpus": 96,
        "memory_gib": 384,
    },
    # Memory Optimized (E-Series v5) - 1:8 Core-to-RAM Ratio
    {
        "tier": "Memory Optimized",
        "family": "E-Series v5",
        "sku": "Standard_E2ds_v5",
        "vcpus": 2,
        "memory_gib": 16,
    },
    {
        "tier": "Memory Optimized",
        "family": "E-Series v5",
        "sku": "Standard_E4ds_v5",
        "vcpus": 4,
        "memory_gib": 32,
    },
    {
        "tier": "Memory Optimized",
        "family": "E-Series v5",
        "sku": "Standard_E8ds_v5",
        "vcpus": 8,
        "memory_gib": 64,
    },
    {
        "tier": "Memory Optimized",
        "family": "E-Series v5",
        "sku": "Standard_E16ds_v5",
        "vcpus": 16,
        "memory_gib": 128,
    },
    {
        "tier": "Memory Optimized",
        "family": "E-Series v5",
        "sku": "Standard_E32ds_v5",
        "vcpus": 32,
        "memory_gib": 256,
    },
    {
        "tier": "Memory Optimized",
        "family": "E-Series v5",
        "sku": "Standard_E48ds_v5",
        "vcpus": 48,
        "memory_gib": 384,
    },
    {
        "tier": "Memory Optimized",
        "family": "E-Series v5",
        "sku": "Standard_E64ds_v5",
        "vcpus": 64,
        "memory_gib": 512,
    },
]

# Sizing translation constants
CPU_CORE_RATIO = 1.0
MEMORY_HEADROOM_FACTOR = 1.25
STORAGE_MVCC_OVERHEAD_FACTOR = 1.30
BASELINE_FREE_IOPS = 3000


def extract_domain_from_fqdn(fqdn: str) -> str:
    """Extracts domain suffix from an FQDN, or returns 'standalone' if no dots."""
    if not fqdn:
        return "Unknown"
    parts = fqdn.strip().split(".", 1)
    if len(parts) > 1 and parts[1]:
        return parts[1].lower()
    return "local"


def select_azure_sku(target_vcpus: int, target_ram_gib: float, preferred_tier: str) -> Dict[str, Any]:
    """
    Selects the best-fit SKU within the preferred tier that satisfies both
    target vCPUs and target RAM. Falls back to other tier if capacity exceeds current tier.
    """
    tier_skus = [s for s in SKU_CATALOG if s["tier"].lower() == preferred_tier.lower()]
    tier_skus.sort(key=lambda s: (s["vcpus"], s["memory_gib"]))

    # Look for matching SKU in chosen tier
    for sku in tier_skus:
        if sku["vcpus"] >= target_vcpus and sku["memory_gib"] >= target_ram_gib:
            return sku

    # If exceeding tier, check if the other tier has a larger SKU
    all_skus = sorted(SKU_CATALOG, key=lambda s: (s["vcpus"], s["memory_gib"]))
    for sku in all_skus:
        if sku["vcpus"] >= target_vcpus and sku["memory_gib"] >= target_ram_gib:
            return sku

    # Fallback to the largest SKU available
    return tier_skus[-1] if tier_skus else all_skus[-1]


def recommend_azure_postgresql(
    vcpus: float,
    ram_gb: float,
    disk_gb: float,
    source_engine: str = "IBM Db2",
    is_production: bool = True,
    ha_override: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Computes Azure Database for PostgreSQL Flexible Server architectural sizing recommendations.

    Parameters:
    - vcpus: total source vCPU cores
    - ram_gb: total source RAM in GB
    - disk_gb: total source allocated/in-use disk in GB
    - source_engine: source database engine (default 'IBM Db2')
    - is_production: boolean indicating production environment
    - ha_override: optional explicit HA enable/disable toggle
    """
    # 1. Determine High Availability recommendation
    if ha_override is not None:
        ha_enabled = ha_override
    else:
        ha_enabled = is_production

    # 2. Compute Target Sizing with Headroom
    # Azure min compute is 2 vCPUs
    target_vcpus = max(2, int(math.ceil(vcpus * CPU_CORE_RATIO))) if vcpus > 0 else 2
    target_ram_gib = round(max(8.0, ram_gb * MEMORY_HEADROOM_FACTOR), 1) if ram_gb > 0 else 8.0
    # Storage minimum 32 GiB in Azure Flexible Server
    target_storage_gib = max(32, int(math.ceil(disk_gb * STORAGE_MVCC_OVERHEAD_FACTOR))) if disk_gb > 0 else 32

    # 3. Determine Tier (Memory Optimized vs General Purpose)
    is_memory_heavy = (ram_gb > (vcpus * 4.0)) or (ram_gb > 32.0)
    if is_memory_heavy or "db2" in source_engine.lower():
        preferred_tier = "Memory Optimized"
        tier_reason = (
            f"On-premise RAM ({ram_gb:.1f} GB) to core ({vcpus:.0f} vCPUs) ratio is "
            f"{ram_gb/max(1, vcpus):.1f}:1 (> 4:1) or total memory exceeds 32 GB. "
            f"When migrating from {source_engine} to PostgreSQL, high bufferpool allocations and "
            "connection worker caching require the 1:8 core-to-RAM ratio to avoid cache starvation."
        )
    else:
        preferred_tier = "General Purpose"
        tier_reason = (
            f"On-premise RAM ({ram_gb:.1f} GB) to core ({vcpus:.0f} vCPUs) ratio fits the standard 1:4 "
            "General Purpose profile, suitable for standard transaction volumes with balanced CPU and memory."
        )

    # 4. Select SKU
    recommended_sku = select_azure_sku(target_vcpus, target_ram_gib, preferred_tier)

    # 5. Structured Architectural Reasoning
    reasoning = {
        "tier_selection": {
            "tier": recommended_sku["tier"],
            "family": recommended_sku["family"],
            "justification": tier_reason,
        },
        "compute_sizing": {
            "source_vcpus": vcpus,
            "target_vcpus": target_vcpus,
            "sku_vcpus": recommended_sku["vcpus"],
            "source_ram_gb": ram_gb,
            "target_ram_gib": target_ram_gib,
            "sku_ram_gib": recommended_sku["memory_gib"],
            "headroom_factor": f"{int((MEMORY_HEADROOM_FACTOR - 1.0) * 100)}%",
            "justification": (
                f"Provisioned {recommended_sku['sku']} provides {recommended_sku['vcpus']} vCPUs and "
                f"{recommended_sku['memory_gib']} GiB RAM. A {int((MEMORY_HEADROOM_FACTOR - 1.0) * 100)}% "
                f"memory buffer ({ram_gb:.1f} GB -> {target_ram_gib:.1f} GiB) protects against peak PostgreSQL "
                "connection overhead and query workspace allocation (work_mem/maintenance_work_mem)."
            ),
        },
        "storage_sizing": {
            "source_disk_gb": disk_gb,
            "target_storage_gib": target_storage_gib,
            "overhead_factor": f"{int((STORAGE_MVCC_OVERHEAD_FACTOR - 1.0) * 100)}%",
            "baseline_iops": BASELINE_FREE_IOPS,
            "justification": (
                f"Target storage is sized at {target_storage_gib:,} GiB incorporating a 30% safety buffer "
                f"({disk_gb:.1f} GB -> {target_storage_gib:,} GiB). PostgreSQL's Multi-Version Concurrency "
                "Control (MVCC) creates duplicate row versions on update; this 30% headroom accommodates "
                "dead tuple accumulation prior to autovacuum, WAL logs, and index reindexing without disk saturation."
            ),
        },
        "high_availability": {
            "enabled": ha_enabled,
            "mode": "Zone-Redundant High Availability" if ha_enabled else "Standalone (Single Zone)",
            "justification": (
                "Zone-Redundant HA provides an automatic standby instance in a separate availability zone "
                "with synchronous replication and automatic failover (<60s). Recommended for production environments."
                if ha_enabled
                else "Standalone configuration provides a single-instance deployment suitable for non-critical or development workloads."
            ),
        },
    }

    return {
        "recommended_sku": recommended_sku,
        "source_vcpus": vcpus,
        "source_ram_gb": ram_gb,
        "source_disk_gb": disk_gb,
        "target_vcpus": target_vcpus,
        "target_ram_gib": target_ram_gib,
        "target_storage_gib": target_storage_gib,
        "ha_enabled": ha_enabled,
        "preferred_tier": preferred_tier,
        "reasoning": reasoning,
    }


def generate_azure_markdown_report(
    app_info: Dict[str, Any],
    servers_df: Any,
    azure_rec: Dict[str, Any]
) -> str:
    """Generates a clean Markdown executive sizing brief for documentation or ticket attachment."""
    sku = azure_rec.get("recommended_sku", {})
    reasoning = azure_rec.get("reasoning", {})
    app_num = app_info.get("Application Number", "Unknown")
    app_name = app_info.get("Name", "Unknown")

    md = f"""# Azure Sizing Recommendation: {app_num} - {app_name}

## 1. Executive Summary & Target Cloud Architecture
* **Target Cloud Service:** Azure Database for PostgreSQL - Flexible Server
* **Recommended Target SKU:** `{sku.get('sku', '')}` ({sku.get('vcpus', 0)} vCPUs, {sku.get('memory_gib', 0)} GiB RAM)
* **Compute Tier:** **{sku.get('tier', '')}** ({sku.get('family', '')})
* **Target Provisioned Storage:** **{azure_rec.get('target_storage_gib', 0):,} GiB** (incorporates +30% MVCC/WAL headroom)
* **High Availability Mode:** **{reasoning.get('high_availability', {}).get('mode', '')}**
* **Included Baseline IOPS:** 3,000 IOPS

---

## 2. Workload & Sizing Context
* **Application Number:** {app_num}
* **Application Name:** {app_name}
* **Environment:** {app_info.get('Environment', 'N/A')}
* **Business Criticality:** {app_info.get('Business criticality', 'N/A')}
* **Application Owner:** {app_info.get('IT Application owner', 'N/A')}
* **Filtered Source Footprint:** {azure_rec.get('source_vcpus', 0):.0f} Cores | {azure_rec.get('source_ram_gb', 0):.1f} GB RAM | {azure_rec.get('source_disk_gb', 0):.1f} GB Disk

---

## 3. Architectural Reasoning & Justifications
### 1. Compute Tier Selection Rationale
{reasoning.get('tier_selection', {}).get('justification', '')}

### 2. Compute & Memory Headroom Rationale (+25%)
{reasoning.get('compute_sizing', {}).get('justification', '')}

### 3. Storage Sizing & MVCC Bloat Headroom (+30%)
{reasoning.get('storage_sizing', {}).get('justification', '')}

### 4. High Availability & Resilience Architecture
{reasoning.get('high_availability', {}).get('justification', '')}
"""
    return md
