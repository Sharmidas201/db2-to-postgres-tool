Here is the structured research data extracted from the Azure Database for PostgreSQL – Flexible Server Pricing page, formatted so you can directly feed it into Antigravity (or any automated pricing and sizing engine).

1. Cost & Architectural Model Breakdown

Component	Billing Mechanism	Sizing & Cost Impact
Compute	Hourly rate (billed monthly, base 730 hrs)	Determined by tier: Burstable, General Purpose (1:4 vCPU:RAM), or Memory Optimized (1:8 vCPU:RAM).
Commitment Discounts	Term agreements	• Pay-As-You-Go (PAYG): Full price.
• 1-Year Savings Plan: ~20% discount.
• 1-Year Reserved Instance (RI): ~40% discount.
• 3-Year Reserved Instance (RI): ~60% discount.
High Availability (HA)	Zone-redundant or Same-zone standby	Doubles the compute instance cost (2× Compute) and duplicates the provisioned storage.
Storage	Provisioned GiB per month	Standard rate ~$0.115–$0.125/GiB/month. Auto-growth can be enabled.
IOPS	Baseline included + Additional provisioned	• Included: Up to 3,000 IOPS free for disks \le 400 GiB.
• Additional Provisioned IOPS: ~$0.090 per IOPS/month.
• Provisioned Throughput: ~$0.600 per MB/s.
Backup Storage	Consumed GiB per month	Backup storage equal to 100% of provisioned database storage is free; retention beyond that or additional snapshots cost ~$0.095/GiB/month.

2. Compute Tiers & SKU Reference

A. General Purpose (D-Series v5/v6) — 1:4 Core-to-RAM Ratio

Ideal for low-to-medium transaction volumes and read-heavy workloads.

SKU Name	vCores	Memory (GiB)	PAYG ($/mo)*	1-Yr Savings Plan (~20%)	1-Yr Reserved (~40%)	3-Yr Reserved (~60%)
Standard_D2ds_v6	2	8	$163.52	$130.82	$98.17	$65.39
Standard_D4ds_v6	4	16	$327.04	$261.63	$196.34	$130.79
Standard_D8ds_v6	8	32	$654.08	$523.26	$392.68	$261.57
Standard_D16ds_v6	16	64	$1,308.16	$1,046.53	$785.36	$523.15
Standard_D32ds_v6	32	128	$2,616.32	$2,093.06	$1,570.73	$1,046.30
Standard_D48ds_v6	48	192	$3,924.48	$3,139.58	$2,356.09	$1,569.44
Standard_D64ds_v6	64	256	$5,232.64	$4,186.11	$3,141.45	$2,092.59
Standard_D96ds_v6	96	384	$7,848.96	$6,279.17	$4,712.18	$3,138.88

(AMD variants like Dadsv5 / Dsv6 are available at ~20% lower baseline rates).

B. Memory Optimized (E-Series v5/v6) — 1:8 Core-to-RAM Ratio

Required standard when migrating on-premise IBM Db2 due to high bufferpool allocations and PostgreSQL connection worker caching.

SKU Name	vCores	Memory (GiB)	Best Suited For (Db2 Context)
Standard_E2ds_v5	2	16	Small reporting datamart / dev instances
Standard_E4ds_v5	4	32	Small OLTP systems (\le 32 GB on-prem RAM)
Standard_E8ds_v5	8	64	Standard production Db2 OLTP (32–64 GB on-prem RAM)
Standard_E16ds_v5	16	128	High-concurrency transaction databases (64–128 GB RAM)
Standard_E32ds_v5	32	256	Enterprise core transactional systems (128–256 GB RAM)
Standard_E48ds_v5	48	384	Very large database (VLDB) workloads
Standard_E64ds_v5	64	512	Enterprise-scale migrations

3. Antigravity Input Configuration (JSON Payload)

Pass this structured definition directly into Antigravity to define sizing thresholds, hardware translation logic, and pricing multipliers:

{
  "service": "Azure Database for PostgreSQL Flexible Server",
  "pricing_currency": "USD",
  "region_reference": "Canada Central / East US",
  "sizing_rules_from_onprem": {
    "source_engine": "IBM Db2",
    "target_engine": "PostgreSQL",
    "compute_sizing_strategy": {
      "default_tier_if_ram_gt_32gb": "Memory_Optimized_E_Series",
      "default_tier_if_ram_lte_32gb": "General_Purpose_D_Series",
      "cpu_core_ratio": 1.0,
      "memory_headroom_factor": 1.25
    },
    "storage_sizing_strategy": {
      "mvcc_vacuum_overhead_factor": 1.30,
      "include_os_disk": false,
      "default_baseline_iops": 3000,
      "enable_autogrow": true
    }
  },
  "pricing_multipliers": {
    "commitment_discounts": {
      "pay_as_you_go": 1.0,
      "1_year_savings_plan": 0.80,
      "1_year_reserved": 0.60,
      "3_year_reserved": 0.40
    },
    "high_availability": {
      "none_standalone": 1.0,
      "zone_redundant_ha": 2.0
    }
  },
  "storage_rates": {
    "provisioned_storage_per_gib_month": 0.115,
    "additional_iops_per_month": 0.090,
    "provisioned_throughput_per_mbps_month": 0.600,
    "excess_backup_storage_per_gib_month": 0.095
  },
  "sku_catalog": [
    {
      "tier": "General Purpose",
      "sku": "Standard_D2ds_v6",
      "vcpus": 2,
      "memory_gib": 8,
      "monthly_payg_usd": 163.52
    },
    {
      "tier": "General Purpose",
      "sku": "Standard_D4ds_v6",
      "vcpus": 4,
      "memory_gib": 16,
      "monthly_payg_usd": 327.04
    },
    {
      "tier": "General Purpose",
      "sku": "Standard_D8ds_v6",
      "vcpus": 8,
      "memory_gib": 32,
      "monthly_payg_usd": 654.08
    },
    {
      "tier": "General Purpose",
      "sku": "Standard_D16ds_v6",
      "vcpus": 16,
      "memory_gib": 64,
      "monthly_payg_usd": 1308.16
    },
    {
      "tier": "General Purpose",
      "sku": "Standard_D32ds_v6",
      "vcpus": 32,
      "memory_gib": 128,
      "monthly_payg_usd": 2616.32
    },
    {
      "tier": "Memory Optimized",
      "sku": "Standard_E4ds_v5",
      "vcpus": 4,
      "memory_gib": 32,
      "monthly_payg_usd": 352.00
    },
    {
      "tier": "Memory Optimized",
      "sku": "Standard_E8ds_v5",
      "vcpus": 8,
      "memory_gib": 64,
      "monthly_payg_usd": 704.00
    },
    {
      "tier": "Memory Optimized",
      "sku": "Standard_E16ds_v5",
      "vcpus": 16,
      "memory_gib": 128,
      "monthly_payg_usd": 1408.00
    },
    {
      "tier": "Memory Optimized",
      "sku": "Standard_E32ds_v5",
      "vcpus": 32,
      "memory_gib": 256,
      "monthly_payg_usd": 2816.00
    }
  ]
}


4. Antigravity Logic Mapping Rules

When building the calculation pipeline in Antigravity using your source schemas (CMDB-CI-SERVER and AXONIUS DEVICES):

1. Calculate Target Cores & RAM:
  ⚬ Read cpu_core_count and ram (in GB).
  ⚬ If on-premise ram > (cpu_core_count * 4), map to Memory Optimized (E-series) to prevent starving PostgreSQL's cache. Otherwise, map to General Purpose (D-series).
2. Calculate Target Storage:
   
   $$\text{Azure Provisioned Storage} = \text{CMDB disk\_space} \times 1.30 \text{ (Headroom for WAL and MVCC)}$$
3. Calculate Total Monthly Cost Formula:
   
   $$\text{Total Cost} = \left(\text{Compute Price} \times \text{HA Multiplier} \times \text{Commitment Discount}\right) + \left(\text{Storage GiB} \times 0.115 \times \text{HA Storage Factor}\right)$$