"""
Azure Database for PostgreSQL - Flexible Server Sizing Recommender.
Translates on-premise hardware footprints (IBM Db2 or generic) to Azure Flexible Server SKUs,
applying sizing headroom, MVCC/WAL overhead, and HA architecture recommendations.
Rules follow azure_research.md (Canada Central, v5 SKUs, General Purpose by default).
Focuses strictly on architectural sizing and technical reasoning without speculative pricing.
"""

import math
from typing import Dict, Any, List, Optional


# Azure Flexible Server SKU Catalog (Canada Central: v5 series; v6 is not offered there)
SKU_CATALOG = [
    # Burstable (B-series) - dev/test only. No zone-redundant HA, no read replicas, no reservations.
    {"tier": "Burstable", "family": "B-Series", "sku": "Standard_B1ms", "vcpus": 1, "memory_gib": 2},
    {"tier": "Burstable", "family": "B-Series", "sku": "Standard_B2s", "vcpus": 2, "memory_gib": 4},
    {"tier": "Burstable", "family": "B-Series", "sku": "Standard_B2ms", "vcpus": 2, "memory_gib": 8},
    {"tier": "Burstable", "family": "B-Series", "sku": "Standard_B4ms", "vcpus": 4, "memory_gib": 16},
    {"tier": "Burstable", "family": "B-Series", "sku": "Standard_B8ms", "vcpus": 8, "memory_gib": 32},
    {"tier": "Burstable", "family": "B-Series", "sku": "Standard_B12ms", "vcpus": 12, "memory_gib": 48},
    {"tier": "Burstable", "family": "B-Series", "sku": "Standard_B16ms", "vcpus": 16, "memory_gib": 64},
    {"tier": "Burstable", "family": "B-Series", "sku": "Standard_B20ms", "vcpus": 20, "memory_gib": 80},
    # General Purpose (D-Series v5) - 1:4 core-to-RAM ratio (default for production)
    {"tier": "General Purpose", "family": "D-Series v5", "sku": "Standard_D2ds_v5", "vcpus": 2, "memory_gib": 8},
    {"tier": "General Purpose", "family": "D-Series v5", "sku": "Standard_D4ds_v5", "vcpus": 4, "memory_gib": 16},
    {"tier": "General Purpose", "family": "D-Series v5", "sku": "Standard_D8ds_v5", "vcpus": 8, "memory_gib": 32},
    {"tier": "General Purpose", "family": "D-Series v5", "sku": "Standard_D16ds_v5", "vcpus": 16, "memory_gib": 64},
    {"tier": "General Purpose", "family": "D-Series v5", "sku": "Standard_D32ds_v5", "vcpus": 32, "memory_gib": 128},
    {"tier": "General Purpose", "family": "D-Series v5", "sku": "Standard_D48ds_v5", "vcpus": 48, "memory_gib": 192},
    {"tier": "General Purpose", "family": "D-Series v5", "sku": "Standard_D64ds_v5", "vcpus": 64, "memory_gib": 256},
    {"tier": "General Purpose", "family": "D-Series v5", "sku": "Standard_D96ds_v5", "vcpus": 96, "memory_gib": 384},
    # Memory Optimized (E-Series v5) - 1:8 core-to-RAM ratio (large working sets)
    {"tier": "Memory Optimized", "family": "E-Series v5", "sku": "Standard_E2ds_v5", "vcpus": 2, "memory_gib": 16},
    {"tier": "Memory Optimized", "family": "E-Series v5", "sku": "Standard_E4ds_v5", "vcpus": 4, "memory_gib": 32},
    {"tier": "Memory Optimized", "family": "E-Series v5", "sku": "Standard_E8ds_v5", "vcpus": 8, "memory_gib": 64},
    {"tier": "Memory Optimized", "family": "E-Series v5", "sku": "Standard_E16ds_v5", "vcpus": 16, "memory_gib": 128},
    {"tier": "Memory Optimized", "family": "E-Series v5", "sku": "Standard_E32ds_v5", "vcpus": 32, "memory_gib": 256},
    {"tier": "Memory Optimized", "family": "E-Series v5", "sku": "Standard_E48ds_v5", "vcpus": 48, "memory_gib": 384},
    {"tier": "Memory Optimized", "family": "E-Series v5", "sku": "Standard_E64ds_v5", "vcpus": 64, "memory_gib": 512},
]

# Sizing translation constants
CPU_CORE_RATIO = 1.0                # default: 1:1 source cores (used when no peak CPU is given)
MEMORY_HEADROOM_FACTOR = 1.25       # default: source RAM headroom (used when no working set is given)
WORKING_SET_RAM_FACTOR = 1.5        # hot working set -> RAM target
TARGET_CPU_UTILIZATION = 0.65       # size vCores so peak load sits at ~65%
MEMORY_RATIO_THRESHOLD = 4.0        # source RAM:vCPU above 4:1 -> Memory Optimized
STORAGE_MVCC_OVERHEAD_FACTOR = 1.30
BASELINE_FREE_IOPS = 3000           # Premium SSD v2 free IOPS under 400 GiB
LARGE_DISK_FREE_IOPS = 12000        # Premium SSD v2 free IOPS at 400 GiB and above
LARGE_DISK_GIB = 400

# VM-level IOPS ceilings (effective IOPS = min(disk, VM cap)). Only values found in azure_research.md or
# Microsoft docs are listed; SKUs missing here (Burstable, D48, E4 to E48) have no cap applied and are flagged.
VM_IOPS_CAP = {
    "Standard_D2ds_v5": 3750, "Standard_D4ds_v5": 6400, "Standard_D8ds_v5": 12800,
    "Standard_D16ds_v5": 25600, "Standard_D32ds_v5": 51200,
    "Standard_D64ds_v5": 80000, "Standard_D96ds_v5": 80000,
    "Standard_E2ds_v5": 3200, "Standard_E64ds_v5": 80000,
}
HA_FAILOVER_SECONDS = "60-120"


def extract_domain_from_fqdn(fqdn: str) -> str:
    """Extracts domain suffix from an FQDN, or returns 'standalone' if no dots."""
    if not fqdn:
        return "Unknown"
    parts = fqdn.strip().split(".", 1)
    if len(parts) > 1 and parts[1]:
        return parts[1].lower()
    return "local"


def fit_sku(target_vcpus: int, target_ram_gib: float, tier: str) -> Optional[Dict[str, Any]]:
    """Smallest SKU in `tier` meeting both targets, or None if the tier is too small."""
    skus = sorted((x for x in SKU_CATALOG if x["tier"].lower() == tier.lower()), key=lambda x: (x["vcpus"], x["memory_gib"]))
    return next((x for x in skus if x["vcpus"] >= target_vcpus and x["memory_gib"] >= target_ram_gib), None)


def pick_sku(target_vcpus: int, target_ram_gib: float, tier: str, allow_mo: bool = True) -> Dict[str, Any]:
    """Best-fit SKU, preferring Memory Optimized when it needs fewer vCPUs than General Purpose."""
    sku = select_azure_sku(target_vcpus, target_ram_gib, tier)
    if tier == "General Purpose" and allow_mo:
        mo, gp = fit_sku(target_vcpus, target_ram_gib, "Memory Optimized"), fit_sku(target_vcpus, target_ram_gib, "General Purpose")
        if mo and (gp is None or mo["vcpus"] < gp["vcpus"]):
            return mo
    return sku


def default_max_connections(memory_gib: float) -> int:
    """Azure default max_connections by RAM (research: ~107 per GiB, 25 per GiB at <=2 GiB, cap 5,000)."""
    known = {2: 50, 4: 429, 8: 859, 16: 1718, 32: 3437}
    return known.get(int(memory_gib), min(5000, int(memory_gib * 107.4)))


def free_storage_iops(storage_gib: int) -> int:
    """Premium SSD v2 free IOPS: 3,000 under 400 GiB, 12,000 at 400 GiB and above."""
    return LARGE_DISK_FREE_IOPS if storage_gib >= LARGE_DISK_GIB else BASELINE_FREE_IOPS


def select_azure_sku(target_vcpus: int, target_ram_gib: float, preferred_tier: str) -> Dict[str, Any]:
    """
    Selects the best-fit SKU within the preferred tier that satisfies both
    target vCPUs and target RAM. Falls back to other tiers if capacity exceeds the preferred tier.
    """
    tier_skus = [s for s in SKU_CATALOG if s["tier"].lower() == preferred_tier.lower()]
    tier_skus.sort(key=lambda s: (s["vcpus"], s["memory_gib"]))

    # Look for matching SKU in chosen tier
    for sku in tier_skus:
        if sku["vcpus"] >= target_vcpus and sku["memory_gib"] >= target_ram_gib:
            return sku

    # If exceeding tier, check the whole catalog (General Purpose first, then the rest)
    all_skus = sorted(SKU_CATALOG, key=lambda s: (s["tier"] == "Burstable", s["vcpus"], s["memory_gib"]))
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
    peak_cpu_pct: Optional[float] = None,
    working_set_gb: Optional[float] = None,
    force_memory_optimized: bool = False,
    memory_profile: str = "Auto",
    growth_gb_per_month: Optional[float] = None,
    peak_iops: Optional[float] = None,
    client_connections: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Computes Azure Database for PostgreSQL Flexible Server architectural sizing recommendations.

    Parameters:
    - vcpus: total source vCPU cores (allocated)
    - ram_gb: total source RAM in GB (allocated)
    - disk_gb: total source allocated/in-use disk in GB
    - source_engine: source database engine (informational; does not force a tier)
    - is_production: production workloads get General Purpose / Memory Optimized; non-prod gets Burstable
    - ha_override: optional explicit HA toggle (ignored for Burstable, which has no zone-redundant HA)
    - peak_cpu_pct: optional observed peak CPU utilization (0-100). If set, vCores = vcpus * peak / 65%
    - working_set_gb: optional hot working set. If set, RAM target = working set * 1.5
    - force_memory_optimized: force the Memory Optimized (E-series) tier for production
    - memory_profile: "Auto" (default), "General Purpose" (never switch to E-series) or "Memory Optimized"
    - growth_gb_per_month: expected data growth; storage is sized for 12 months of it
    - peak_iops: observed peak IOPS; provisioned at peak + 30% (VM may be bumped, extra SSD v2 IOPS bought)
    - client_connections: total app connections (instances x pool + extras); checked against max_connections
    """
    # 1. Tier selection (research: GP default; E-series only for large working sets; Burstable for non-prod)
    ratio = (ram_gb / vcpus) if vcpus > 0 else 0.0
    force_mo = force_memory_optimized or memory_profile == "Memory Optimized"
    lock_gp = memory_profile == "General Purpose"
    if not is_production:
        preferred_tier = "Burstable"
        tier_reason = (
            "Non-production workload: Burstable (B-series) is used for dev/test only. Burstable is not "
            "recommended for production, has no zone-redundant HA, no read replicas and no reservations. "
            "Stop the server off-hours to reduce cost."
        )
    elif force_mo or (ratio > MEMORY_RATIO_THRESHOLD and not lock_gp):
        preferred_tier = "Memory Optimized"
        reason_bits = []
        if ratio > MEMORY_RATIO_THRESHOLD:
            reason_bits.append(f"source RAM:vCPU ratio is {ratio:.1f}:1 (above {MEMORY_RATIO_THRESHOLD:.0f}:1)")
        if force_mo:
            reason_bits.append("Memory Optimized was selected manually")
        tier_reason = (
            "Memory Optimized (E-series, 1:8) is used because " + " and ".join(reason_bits) + ". "
            "A large working set needs more RAM for caching than General Purpose provides."
        )
    else:
        preferred_tier = "General Purpose"
        tier_reason = (
            f"General Purpose (D-series v5, 1:4) is the default for production. Source RAM:vCPU ratio is "
            f"{ratio:.1f}:1, so no memory-heavy profile is needed."
            + (" General Purpose was selected manually, so E-series is never substituted." if lock_gp else "")
        )

    # 2. vCPU target
    min_vcpus = 1 if preferred_tier == "Burstable" else 2
    if peak_cpu_pct and peak_cpu_pct > 0 and vcpus > 0:
        cpu_basis = f"peak CPU {peak_cpu_pct:.0f}% at {TARGET_CPU_UTILIZATION:.0%} target utilization"
        target_vcpus = max(min_vcpus, int(math.ceil(vcpus * (peak_cpu_pct / 100.0) / TARGET_CPU_UTILIZATION)))
    else:
        cpu_basis = f"allocated source cores ({CPU_CORE_RATIO:.0f}:1)"
        target_vcpus = max(min_vcpus, int(math.ceil(vcpus * CPU_CORE_RATIO))) if vcpus > 0 else min_vcpus

    # 3. RAM target
    min_ram = 2.0 if preferred_tier == "Burstable" else 8.0
    if working_set_gb and working_set_gb > 0:
        ram_basis = f"hot working set {working_set_gb:.1f} GB x {WORKING_SET_RAM_FACTOR}"
        target_ram_gib = round(max(min_ram, working_set_gb * WORKING_SET_RAM_FACTOR), 1)
        headroom_label = f"{WORKING_SET_RAM_FACTOR}x hot working set"
    else:
        ram_basis = f"source RAM x {MEMORY_HEADROOM_FACTOR}"
        target_ram_gib = round(max(min_ram, ram_gb * MEMORY_HEADROOM_FACTOR), 1) if ram_gb > 0 else min_ram
        headroom_label = f"{MEMORY_HEADROOM_FACTOR}x source RAM"

    # 4. Storage target (unchanged rule: +30% MVCC/WAL headroom, 32 GiB minimum)
    growth_12m = (growth_gb_per_month or 0.0) * 12
    sized_disk = disk_gb + growth_12m
    target_storage_gib = max(32, int(math.ceil(sized_disk * STORAGE_MVCC_OVERHEAD_FACTOR))) if sized_disk > 0 else 32

    # 5. HA: Burstable cannot use zone-redundant HA
    if preferred_tier == "Burstable":
        ha_enabled = False
    elif ha_override is not None:
        ha_enabled = ha_override
    else:
        ha_enabled = is_production

    # 5b. Default path only: if the 1.25x RAM headroom alone forces a bigger SKU (e.g. 64 GB x 1.25 = 80 GiB
    # jumps 64 -> 128 GiB), size to source RAM 1:1 instead and say so.
    headroom_note = ""
    if not (working_set_gb and working_set_gb > 0) and ram_gb > 0:
        with_headroom = pick_sku(target_vcpus, target_ram_gib, preferred_tier, not lock_gp)
        floor_ram = round(max(min_ram, ram_gb), 1)
        at_source = pick_sku(target_vcpus, floor_ram, preferred_tier, not lock_gp)
        if with_headroom["memory_gib"] > at_source["memory_gib"]:
            headroom_note = (
                f" The {MEMORY_HEADROOM_FACTOR}x headroom ({target_ram_gib:.0f} GiB) would have forced "
                f"{with_headroom['sku']} ({with_headroom['vcpus']} vCPUs, {with_headroom['memory_gib']} GiB), "
                f"so RAM is sized to source RAM 1:1 ({floor_ram:.0f} GiB) instead. PostgreSQL usually needs less "
                "RAM than Db2; confirm with the cache hit ratio and add a hot working set for a firmer number."
            )
            target_ram_gib = floor_ram
            headroom_label = "1.0x source RAM (headroom would jump a SKU)"
            ram_basis = "source RAM x 1.0"

    # 6. Select SKU
    recommended_sku = select_azure_sku(target_vcpus, target_ram_gib, preferred_tier)
    tier_note = ""
    if preferred_tier == "General Purpose" and not lock_gp:
        # Don't buy extra vCPUs just for RAM: if E-series reaches the targets with fewer vCPUs, use it.
        mo_sku = fit_sku(target_vcpus, target_ram_gib, "Memory Optimized")
        gp_sku = fit_sku(target_vcpus, target_ram_gib, "General Purpose")
        if mo_sku and (gp_sku is None or mo_sku["vcpus"] < gp_sku["vcpus"]):
            recommended_sku = mo_sku
            preferred_tier = "Memory Optimized"
            gp_txt = f"{gp_sku['sku']} ({gp_sku['vcpus']} vCPUs)" if gp_sku else "no General Purpose SKU"
            tier_note = (
                f" Switched to Memory Optimized: the RAM target ({target_ram_gib:.0f} GiB for {target_vcpus} vCPUs) "
                f"exceeds the 4 GiB per vCore of General Purpose, and {mo_sku['sku']} ({mo_sku['vcpus']} vCPUs) "
                f"meets it with fewer vCPUs than {gp_txt}."
            )
    elif recommended_sku["tier"] != preferred_tier:
        tier_note = (
            f" The workload exceeds the {preferred_tier} range, so {recommended_sku['tier']} is used instead."
        )
    fits = recommended_sku["vcpus"] >= target_vcpus and recommended_sku["memory_gib"] >= target_ram_gib
    capacity_warning = None if fits else (
        f"Needs {target_vcpus} vCPUs and {target_ram_gib:.0f} GiB RAM, more than the largest catalog SKU "
        f"({recommended_sku['sku']}: {recommended_sku['vcpus']} vCPUs, {recommended_sku['memory_gib']} GiB). "
        "Split the workload, use read replicas or an elastic cluster, and validate with a load test."
    )

    # IOPS: provision peak + 30%, then effective = min(disk, VM cap)
    iops_need = int(math.ceil(peak_iops * 1.3)) if peak_iops and peak_iops > 0 else None
    iops_bump = ""
    if iops_need and (VM_IOPS_CAP.get(recommended_sku["sku"]) or 10**9) < iops_need:
        bigger = sorted(
            (x for x in SKU_CATALOG if x["tier"] == recommended_sku["tier"]
             and x["vcpus"] >= recommended_sku["vcpus"] and x["memory_gib"] >= recommended_sku["memory_gib"]
             and VM_IOPS_CAP.get(x["sku"], 0) >= iops_need),
            key=lambda x: (x["vcpus"], x["memory_gib"]),
        )
        if bigger:
            old = recommended_sku
            recommended_sku = bigger[0]
            iops_bump = (
                f" Peak {peak_iops:,.0f} IOPS + 30% = {iops_need:,} exceeds {old['sku']}'s VM cap "
                f"({VM_IOPS_CAP.get(old['sku']):,}), so the SKU moved up to {recommended_sku['sku']}."
            )
    free_iops = free_storage_iops(target_storage_gib)
    extra_iops = 0
    if iops_need and iops_need > free_iops:
        extra_iops = max(0, min(iops_need, 80000, 500 * target_storage_gib) - free_iops)
    disk_iops = free_iops + extra_iops
    vm_iops_cap = VM_IOPS_CAP.get(recommended_sku["sku"])
    effective_iops = min(disk_iops, vm_iops_cap) if vm_iops_cap else disk_iops
    if vm_iops_cap and disk_iops > vm_iops_cap:
        iops_text = (
            f"Premium SSD v2 gives {disk_iops:,} IOPS at {target_storage_gib:,} GiB, but "
            f"{recommended_sku['sku']} is capped at {vm_iops_cap:,} IOPS, so effective IOPS are {effective_iops:,}. "
            "Check Disk IOPS Consumed % at peak; if it runs high, move to a larger VM."
        )
    elif vm_iops_cap:
        iops_text = f"Premium SSD v2 gives {disk_iops:,} IOPS, under the {vm_iops_cap:,} IOPS VM cap, so effective IOPS are {effective_iops:,}."
    else:
        iops_text = f"Premium SSD v2 gives {disk_iops:,} IOPS. The VM IOPS cap for {recommended_sku['sku']} is not in the research data; look it up in Microsoft's compute table, as effective IOPS can be lower."
    if extra_iops:
        iops_text += f" Peak {peak_iops:,.0f} IOPS + 30% = {iops_need:,}: buy about {extra_iops:,} extra IOPS on top of the {free_iops:,} free."
    iops_text += iops_bump
    if iops_need and effective_iops < iops_need:
        iops_text += f" Effective IOPS ({effective_iops:,}) are still below the {iops_need:,} needed; add a larger disk or VM."

    # Connections vs the SKU's default max_connections
    max_conn = default_max_connections(recommended_sku["memory_gib"])
    connections = None
    if client_connections and client_connections > 0:
        usable = max_conn - 15
        pct = client_connections / usable * 100
        if pct > 100:
            msg = f"{client_connections:,} client connections exceed the {usable:,} usable. Enable PgBouncer (port 6432) and shrink app pools; don't raise max_connections."
        elif pct > 80:
            msg = f"{pct:.0f}% of the {usable:,} usable connections. Above 80%: enable PgBouncer."
        else:
            msg = f"{pct:.0f}% of the {usable:,} usable connections. Healthy; PgBouncer is optional (recommended for serverless or many instances)."
        connections = {
            "clients": int(client_connections), "max_connections": max_conn, "usable": usable,
            "pct": pct, "pgbouncer_recommended": pct > 80, "message": msg,
        }

    # 7. Structured architectural reasoning
    if ha_enabled:
        ha_mode = "Zone-Redundant High Availability"
        ha_text = (
            f"Zone-redundant HA keeps a synchronous standby in another availability zone with automatic "
            f"failover in {HA_FAILOVER_SECONDS} seconds and no data loss. Standby is not readable and "
            "does not protect against logical errors such as a dropped table, which replicate to the standby. "
            "Billing is 2x compute and storage."
        )
    elif preferred_tier == "Burstable":
        ha_mode = "Standalone (Single Zone)"
        ha_text = "Burstable SKUs do not support zone-redundant HA. Dev/test runs as a single instance."
    else:
        ha_mode = "Standalone (Single Zone)"
        ha_text = "Standalone configuration: a single instance with no standby. Suitable for non-critical workloads."

    reasoning = {
        "tier_selection": {
            "tier": recommended_sku["tier"],
            "family": recommended_sku["family"],
            "justification": tier_reason + tier_note,
        },
        "compute_sizing": {
            "source_vcpus": vcpus,
            "target_vcpus": target_vcpus,
            "sku_vcpus": recommended_sku["vcpus"],
            "source_ram_gb": ram_gb,
            "target_ram_gib": target_ram_gib,
            "sku_ram_gib": recommended_sku["memory_gib"],
            "headroom_label": headroom_label,
            "justification": (
                f"Provisioned {recommended_sku['sku']} provides {recommended_sku['vcpus']} vCPUs and "
                f"{recommended_sku['memory_gib']} GiB RAM. vCPUs are sized from {cpu_basis}. "
                f"RAM is sized from {ram_basis} ({target_ram_gib:.1f} GiB). Memory is the main driver of "
                "PostgreSQL cache hit ratio, so keep the working set in RAM." + headroom_note
            ),
        },
        "storage_sizing": {
            "source_disk_gb": disk_gb,
            "target_storage_gib": target_storage_gib,
            "overhead_factor": f"{int((STORAGE_MVCC_OVERHEAD_FACTOR - 1.0) * 100)}%",
            "baseline_iops": disk_iops,
            "free_iops": free_iops,
            "vm_iops_cap": vm_iops_cap,
            "effective_iops": effective_iops,
            "iops_justification": iops_text,
            "justification": (
                f"Target storage is sized at {target_storage_gib:,} GiB incorporating a 30% safety buffer "
                f"({disk_gb:.1f} GB"
                + (f" + {growth_12m:.0f} GB of 12-month growth" if growth_12m else "")
                + f" -> {target_storage_gib:,} GiB). PostgreSQL's Multi-Version Concurrency "
                "Control (MVCC) creates duplicate row versions on update; this 30% headroom accommodates "
                "dead tuple accumulation prior to autovacuum, WAL logs, and index reindexing without disk saturation. "
                + iops_text
            ),
        },
        "high_availability": {
            "enabled": ha_enabled,
            "mode": ha_mode,
            "justification": ha_text,
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
        "capacity_warning": capacity_warning,
        "extra_iops_to_buy": extra_iops,
        "iops_needed": iops_need,
        "connections": connections,
        "effective_iops": effective_iops,
        "inputs": {
            "peak_cpu_pct": peak_cpu_pct or None,
            "working_set_gb": working_set_gb or None,
            "force_memory_optimized": force_mo,
            "memory_profile": memory_profile,
            "growth_gb_per_month": growth_gb_per_month or None,
            "peak_iops": peak_iops or None,
            "client_connections": client_connections or None,
            "is_production": is_production,
        },
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
    compute = reasoning.get("compute_sizing", {})
    app_num = app_info.get("Application Number", "Unknown")
    app_name = app_info.get("Name", "Unknown")
    warning = ""
    if azure_rec.get("capacity_warning"):
        warning += f"\n> **Capacity warning.** {azure_rec['capacity_warning']}\n"
    if sku.get("tier") == "Burstable":
        warning += "\n> **Dev/test only.** Burstable is not supported for production. Stop the server off-hours.\n"

    md = f"""# Azure Sizing Recommendation: {app_num} - {app_name}

## 1. Executive Summary & Target Cloud Architecture
* **Target Cloud Service:** Azure Database for PostgreSQL - Flexible Server
* **Recommended Target SKU:** `{sku.get('sku', '')}` ({sku.get('vcpus', 0)} vCPUs, {sku.get('memory_gib', 0)} GiB RAM)
* **Compute Tier:** **{sku.get('tier', '')}** ({sku.get('family', '')})
* **Target Provisioned Storage:** **{azure_rec.get('target_storage_gib', 0):,} GiB** (incorporates +30% MVCC/WAL headroom)
* **High Availability Mode:** **{reasoning.get('high_availability', {}).get('mode', '')}**
* **IOPS (Premium SSD v2 free tier, capped by VM):** {azure_rec.get('effective_iops', 0):,} IOPS
{warning}
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

### 2. Compute & Memory Sizing Rationale ({compute.get('headroom_label', '')})
{compute.get('justification', '')}

### 3. Storage Sizing & MVCC Bloat Headroom (+30%)
{reasoning.get('storage_sizing', {}).get('justification', '')}

### 4. High Availability & Resilience Architecture
{reasoning.get('high_availability', {}).get('justification', '')}
"""
    return md
