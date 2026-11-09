# Azure Database for PostgreSQL Flexible Server: A Practical Sizing, Tiering and Cost Guide (November 2026)

For almost every production app you should start on a General Purpose D-series v5 server (D2ds_v5 or D4ds_v5) with Premium SSD v2 storage and the built-in PgBouncer turned on. Use Burstable only for dev/test, where you can stop the server off-hours. Move to Memory Optimized (E-series) only when your working set no longer fits in RAM. Single Server is gone: Microsoft retired it on March 28, 2025, and instances that missed the deadline have been disabled. Flexible Server is the only deployment model you should be planning around.

## TL;DR

- **Tier choice:** Use Burstable (B-series) only for dev/test and demos. Microsoft says it's "not recommended for production" and it can't have zone-redundant HA, read replicas or reservations. General Purpose (D-series, 4 GiB per vCore) is the default for production. Memory Optimized (E-series, 6.75–9.5 GiB per vCore) is for working sets that are larger than RAM or for analytics-leaning queries.
- **Sizing:** Size memory to your hot working set, vCores to your peak CPU at 60–70% utilization, and IOPS to the *lower* of the disk limit and the VM limit. Premium SSD v2 includes 3,000 IOPS and 125 MB/s free on disks under 400 GiB, while Premium SSD at 256 GiB gives only 1,100 IOPS. Pool your connections rather than raising `max_connections`.
- **Cost:** You're billed for compute per vCore-hour, storage per GiB-month, and backup storage beyond 100% of provisioned storage. HA doubles both compute and storage. In Canada Central a D2ds_v5 costs about US$145/month pay-as-you-go, which is about 9–12% more than East US (third-party data). The levers that matter are stop/start for non-prod, 1- or 3-year reservations (up to 40% / 60% off compute), and avoiding geo-redundant backup or HA where you don't need them.

## Key Findings

### Single Server status
- Microsoft announced on March 31, 2023 that Single Server would be retired on **March 28, 2025**.
- In a May 5, 2025 Microsoft Q&A answer, a Microsoft External Staff moderator confirmed that "since Azure Database for PostgreSQL - Single Server was officially retired on March 28, 2025, instances that missed migration deadlines have been disabled." In the same thread (May 2025), Microsoft staff told the affected customer: "we have enabled the PostgreSQL single server for the next 30 days to migrate it to the Flexible Server, this is not extendable."
- If you find a Single Server reference in old docs, Terraform or Bicep, treat it as legacy. All new work targets Flexible Server.

### Compute tier comparison

| Tier | VM series | vCore options | Memory per vCore | Max IOPS (VM limit) | Max connections (default) | HA / replicas / reservations | Best for |
|---|---|---|---|---|---|---|---|
| **Burstable** | B-series (B1ms–B20ms); new Bsv2 "B2ats v2…B8as v2" sizes are listed on the pricing page | 1, 2, 4, 8, 12, 16, 20 | Variable (B1ms 2 GiB, B2s 4 GiB, B2ms+ 4 GiB per vCore) | 640 (B1ms) to 4,320 (B8ms+) | 50 (B1ms), 429 (B2s), 859 (B2ms), 1,718 (B4ms) | No HA (Microsoft: only General Purpose and Memory Optimized support HA); no read replicas; no reservations (not re-verified) | Dev/test, PoC, low-traffic side projects |
| **General Purpose** | Ddsv5/Dadsv5 (GA), Ddsv6/Dadsv6 (preview), plus older Ddsv4/Dsv3 | 2–96 (v5); up to 192 on v6 | 4 GiB | 3,750 (D2ds_v5) to 80,000 (D64+) | 859 (2 vCore), 1,718 (4), 3,437 (8), 5,000 (16+) | Full support | Most production web/API/SaaS OLTP |
| **Memory Optimized** | Edsv5/Eadsv5 (GA), Edsv6/Eadsv6 (preview), plus older | 2–96 (v5); up to 192 on v6 | 6.75–9.5 GiB (E2ds_v5 = 16 GiB, E4 = 32, E8 = 64) | 3,200 (E2ds_v5) to 80,000 | 1,718 (2 vCore), 3,437 (4), 5,000 (8+) | Full support | Large working sets, reporting/analytics queries, high concurrency |
| **Confidential (niche)** | Dcadsv5 / Ecadsv5 (AMD SEV-SNP) | 2–96 | 8–384 / 16–672 GiB total | 3,750–80,000 | Same formula | — | Regulated workloads needing in-use encryption |

Notes on the table:
- **Verified VM IOPS caps:** D2ds_v5 3,750; D4ds_v5 6,400; D8ds_v5 12,800; D16ds_v5 25,600; D32ds_v5 51,200; E2ds_v5 3,200; D64+/E64 up to 80,000. Other sizes were not verified.
- **IOPS and bandwidth are capped by the VM, not just the disk.** A D2ds_v5 can't push more than 3,750 IOPS or 85 MiB/s however big the disk is. A D4ds_v5 is capped at 6,400 IOPS and 145 MiB/s, and a D8ds_v5 at 12,800 IOPS and 290 MiB/s. The v6 SKUs raise these ceilings: D4ds_v6 reaches 8,333 IOPS and 248 MiB/s.
- **v6 is still in preview, with limits.** You can't scale between v6 and Burstable, and VNet integration isn't supported. Per the Learn region table, **Canada Central offers Intel v3/v4/v5 and AMD v5 only**, with no v6.
- **Canada Central supports both zone-redundant HA and geo-redundant backup. Canada East supports only same-zone HA.** For a Toronto-based app, Canada Central is the default region.

### When to use each tier

| Scenario | Recommendation | Why |
|---|---|---|
| Local-ish dev, CI databases, demos | B1ms/B2s, stopped off-hours | Cheapest at about US$14/month (B1ms, Canada Central). Microsoft calls Burstable "best suited for… proof-of-concept environments, small databases, and development builds." |
| Staging that mirrors prod | Same tier as prod but smaller, with no HA | Mirrors prod behaviour (no credit cliffs). Don't pay for a standby nobody fails over to. |
| Small production app (<~50 TPS, data <50 GB) | D2ds_v5, or D4ds_v5 for headroom | Predictable CPU and support eligibility. Burstable "does not qualify for 24/7 support, and root cause analysis (RCA) may not be provided." |
| Read-heavy app | GP primary plus 1–2 read replicas, or a bigger E-series primary | Replicas are asynchronous, readable and up to 5 per primary (30 with cascading). Each one is a fully billed server. |
| Memory-intensive / analytics-leaning | E-series (E4ds_v5 = 32 GiB, E8ds_v5 = 64 GiB) | Keeps large indexes and working sets cached, and gives room for larger `work_mem` sorts and hashes. |
| High-throughput OLTP | D8–D32ds_v5 (or v6 when GA) with Premium SSD v2 and provisioned IOPS | Higher VM IOPS ceilings (12,800–51,200 on v5). SSD v2 can reach 80,000 IOPS without oversizing capacity. |

**When burstable credits become a problem.**
- **How the baseline works.** A B-series VM earns credits below its baseline and spends them above it. Microsoft's B-series VM docs give the baselines: B1ms is 20% of one vCPU, B2s 40% and B2ms 60% of the VM. B4ms is about 22.5% per vCPU, which is roughly **0.9 of a vCore you can sustain indefinitely**.
- **What happens when credits run out.** The server is throttled to baseline CPU. Microsoft warns this "can cause severe performance degradation, connection timeouts, and delays or transient failures in management operations." It also warns that "the server might become unreachable."
- **Signals you've outgrown Burstable:**
  - CPU sits above the baseline for hours at a time.
  - The **CPU Credits Remaining** metric trends down day over day instead of refilling overnight.
  - Stop, scale or restart operations get slow. Microsoft notes that stopping a credit-exhausted server "can take longer than usual."
- **Cost per sustained vCore.** In East US, Datapace calculates about US$220 per sustained vCore per month on B4ms versus about US$65 on D4ds_v5. That makes Burstable the most expensive tier per vCore you can actually use.
- **Availability risk.** On Microsoft Q&A on Nov 6, 2026, volunteer moderator "TP" wrote that "unfortunately new deployments of PostgreSQL Flexible Server Burstable SKUs are blocked in some regions", in a thread about Sweden Central. TP gave the same answer that day about B1ms in West US 3, adding that "the underlying VM sizes... are being retired, and they are currently subject to growth restrictions and capacity limitations." This is unofficial and varies by region, but it's another reason not to build production on Burstable. Check `az postgres flexible-server list-skus --location canadacentral` before you commit.

### Storage

| | Premium SSD (v1) | Premium SSD v2 |
|---|---|---|
| Size | 32 GiB – 32 TiB, fixed tiers | 32 GiB – 64 TiB, in 1-GiB steps |
| IOPS | Tied to size: 32 GiB = 120 (bursts to 3,500), 128 GiB = 500, 256 GiB = 1,100, 512 GiB = 2,300, 1 TiB = 5,000, max 20,000 | 3,000 free under 400 GiB, 12,000 free at 400 GiB and above; add up to 80,000 (500 IOPS per GiB, so 80,000 needs at least 160 GiB); IOPS/throughput can be changed independently, limited to about 4 changes per 24 hours |
| Throughput | Tied to size, max 900 MB/s | 125 MB/s free under 400 GiB, 500 MB/s at 400 GiB and above; max 1,200 MB/s |
| Autogrow | GA | Public preview |
| Other | Host caching on disks under 4 TiB; "performance tier" can raise IOPS without growing the disk | No Burstable at creation; no long-term backups; no PG 13; lower latency |

Practical rules:
- **Default to Premium SSD v2 for new GP/MO servers.** Microsoft calls it "the best price for performance" for most general-purpose workloads. At 128–256 GiB it gives you 3,000 IOPS free, against 500–1,100 on Premium SSD. You can then tune IOPS and throughput up or down independently of size.
- **Storage only grows, never shrinks.** Over-provisioning is a permanent cost, so start modest.
- **The server goes read-only at 95% full, or when free space drops below 5 GiB.** Microsoft pages word this inconsistently ("or" vs "whichever is more"), so alert well before 80%.
- **How Premium SSD autogrow behaves:**
  - It triggers at 20% free (or 64 GiB, whichever is smaller) on disks under 1 TiB, and at 10% free (or 64 GiB) on larger disks.
  - It always *doubles* both size and cost.
  - It doesn't fire during high WAL usage.
  - It won't cross the 4,096 GiB boundary, which needs a manual, offline scale.
- **Effective IOPS = min(disk IOPS, VM IOPS limit).** A 2 TiB Premium SSD (7,500 IOPS) on a D2ds_v5 is still capped at 3,750.

### High availability and backups

**HA modes:**
- **Zone-redundant:** a synchronous standby in another availability zone. 99.99% SLA, and automatic failover in 60–120 seconds with zero data loss.
- **Same-zone:** 99.95% SLA, but no protection if the zone fails.
- **No HA:** 99.9% SLA.

**HA trade-offs:**
- The standby uses identical vCores and storage, so you pay for both twice.
- The standby isn't readable.
- It adds commit latency on writes.
- It doesn't protect you from your own mistakes, such as a dropped table, because those replicate to the standby.
- Zone-redundant HA isn't available on Burstable.
- Scale operations still cause a brief outage even with HA.
- **Read replicas are a different feature:** they're asynchronous and readable, can be cross-region, and can't have HA themselves.

**Backups:**
- Automated backups are kept for 7 days by default, configurable from 7 to 35. Long-term retention of up to 10 years goes through Azure Backup vaults.
- Backup storage redundancy: Microsoft's reliability page says backups are zone-redundant (ZRS) in zone-capable regions regardless of HA, but the backup concepts page says servers with no HA or same-zone HA default to locally redundant. **The docs conflict; confirm in the portal at creation.**
- Backup storage up to **100% of the primary's provisioned storage is free**, and HA doesn't increase that allowance.
- **Geo-redundant backup can only be chosen at server creation.** It doubles the stored footprint and is billed as ((2 × local backup size) − provisioned storage) × price.
- In Datapace's worked example, a 512 GiB server writing 40 GiB of backup data a day costs $0/month at 7 days local, $84 at 35 days local, and **$217 at 35 days geo-redundant**.
- Microsoft Learn's backup and restore guide says a point-in-time restore creates a *new* server "with the source server's configuration for the pricing tier, compute generation, number of virtual cores, storage size, backup retention period, and backup redundancy option." In a 2026 Microsoft Q&A thread ("$1000 charge for Azure Database for PostgreSQL Flexible Server Backup Storage"), a user wrote: "I recently ran a restore for a client and received a charge on my latest bill for nearly $1,000."

## Details

### Sizing method: from workload metrics to a SKU

1. **Memory (decide this first).**
   - Estimate your hot working set: the tables and indexes your queries touch in a typical hour.
   - Azure sets `shared_buffers` from the SKU. A Microsoft Q&A answer cites 2 GB on a 2-vCore GP and 4 GB on a 2-vCore MO. The OS page cache uses most of the rest.
   - Rule of thumb: pick a SKU whose total RAM is at least about 1.5× the working set.
   - Check that the buffer cache hit ratio (`pg_stat_database` blks_hit / (blks_hit + blks_read)) stays above about 99% for OLTP. If you need more than 4 GiB per vCore of RAM but not more CPU, move to E-series.
2. **vCores.**
   - Measure average CPU time per query or transaction with `pg_stat_statements` (total_exec_time / calls is an upper bound).
   - vCores needed ≈ peak QPS × CPU-seconds per query ÷ 0.65 target utilization. Round up to the next SKU, keeping at least 2 vCores for autovacuum and background work.
   - Use 60–70% as the target, not 100%. That leaves headroom for spikes, vacuum and failover catch-up.
3. **Storage size.**
   - Size = current data + indexes + 12 months of growth + about 20–30% for WAL, temp files and bloat. Remember the 95% read-only threshold.
   - On Premium SSD you may need to *oversize* the disk to get IOPS. On SSD v2 you buy IOPS separately.
4. **IOPS and throughput.**
   - If the working set fits in RAM, read IOPS stay low. Writes drive WAL and checkpoint IOPS.
   - Watch the IOPS and Disk IOPS Consumed Percentage metrics under peak load, and provision enough for peak plus about 30%.
   - Make sure the VM's IOPS cap is above that number.
5. **Connections.**
   - Azure's default `max_connections` is about 105 per GiB of RAM (25 per GiB at 2 GiB or less), capped at 5,000. Fifteen connections are reserved, so user connections = max − 15.
   - Total client connections = app instances × pool size + workers + admin tools.
   - **Gotcha:** `max_connections` doesn't change when you scale the SKU. A B1ms upgraded to B2s stays at 50 until you change the setting and restart.
   - Microsoft advises against raising `max_connections` above the default, because every connection, idle or not, uses memory.
6. **Pooling.**
   - Enable the built-in PgBouncer (`pgbouncer.enabled = true`, port **6432**, same hostname; default `pgbouncer.default_pool_size` = 50 per user/database pair, `pgbouncer.max_client_conn` default 5,000, `pgbouncer.pool_mode` default transaction).
   - Use transaction pooling mode for web, API and serverless workloads such as Azure Functions, Vercel/Next.js API routes or Lambda-style bursts.
   - In transaction mode, watch for session features that break: session-level prepared statements, `LISTEN/NOTIFY`, temp tables and advisory locks.
   - Keep app-side pools small, around 5–20 per instance.
7. **Scale up or scale out.**
   - **Scale up** when CPU or memory is saturated on writes, or when a single query is slow. Near-zero-downtime scaling (<30 s) is the default, but it falls back to a longer restart (Microsoft says roughly 2 to 10 minutes) if conditions aren't met: missing capacity or quota, unlogged tables, replicas, a VNet subnet without enough IPs, or scaling from/to a 1- or 2-vCore Burstable size.
   - **Scale out** to read replicas when reads dominate (above about 70–80% of load), your app can tolerate replication lag, and you can route reads separately.
   - Elastic clusters (Citus-based sharding) are the option for write scale-out beyond one node.

### Worked sizing example (Toronto SaaS app)

**Workload**
- B2B SaaS app running in Canada Central on 3 App Service instances, plus a background worker.
- Data: 60 GB today, growing about 4 GB/month.
- Hot working set about 9 GB (recent tenants' rows and the main indexes).
- Peak 400 QPS, 80% reads. `pg_stat_statements` shows an average of about 3 ms CPU per query.
- Each app instance uses a pool of 20; the worker uses 10.

**Calculation**
- **CPU:** 400 × 0.003 = 1.2 vCore-seconds per second. Divide by 0.65 to get about 1.85 vCores, then add vacuum and headroom: **4 vCores**.
- **Memory:** 9 GB × 1.5 ≈ 13.5 GB, so **16 GiB** is enough. That rules out D2 (8 GiB). E2ds_v5 (16 GiB, 2 vCores) has too little CPU.
- **SKU:** **D4ds_v5** (4 vCores, 16 GiB, VM cap 6,400 IOPS and 145 MiB/s, default max_connections 1,718).
- **Storage:** 60 + 48 (12 months of growth) = 108 GB, plus 30% ≈ 140 GB, so **160 GiB Premium SSD v2** with the free 3,000 IOPS and 125 MB/s. The equivalent Premium SSD (128 GiB at 500 IOPS, or 256 GiB at 1,100 IOPS) would be IOPS-starved.
- **Connections:** 3 × 20 + 10 = 70. That's well under the limit, so PgBouncer isn't strictly required. If you move the API to serverless, enable it.
- **HA:** zone-redundant, because Canada Central supports it.
- **Backups:** 7–14 days, locally/zone-redundant. Choose geo-redundancy at creation only if you need cross-region DR to Canada East.

**Estimated cost**

These are USD list prices. Compute figures are third-party (Bytebase) estimates for Canada Central. Storage uses the East US Premium SSD rate as a proxy for SSD v2, because SSD v2 per-GiB pricing wasn't retrievable. Verify everything in the Azure portal estimate or the pricing calculator.

| Line | Monthly |
|---|---|
| D4ds_v5 compute, Canada Central (~$0.099/vCore-hr × 4 × 730) | ~$290 |
| Zone-redundant HA standby compute | ~$290 |
| 160 GiB storage × 2 (primary + standby), ~$0.115/GiB proxy | ~$37 |
| Backup (inside free allowance at 7 days) | $0 |
| **Total, pay-as-you-go** | **~$615** |
| With 1-year reservation on 8 vCores (~40% off compute) | ~$385 |
| With 3-year reservation (~60% off compute) | ~$270 |

Re-check after 2–4 weeks in production. If p95 CPU stays under about 30% and memory under about 60%, D2ds_v5 plus a later scale-up is cheaper. The resize takes under 30 seconds in the near-zero-downtime case.

### Monitoring signals that mean it's time to resize

| Signal (Azure Monitor metric) | Resize-up trigger (suggested) | Resize-down / right-size signal | Action |
|---|---|---|---|
| `cpu_percent` | p95 above 75–80% for days | p95 below 25–30% for 2–4 weeks | Scale vCores; check `pg_stat_statements` for bad queries first |
| `cpu_credits_remaining` (Burstable) | Trending toward 0 or not refilling overnight | — | Larger B size, or move to GP |
| `memory_percent` plus cache hit ratio | Memory above 90% and hit ratio below 99% | Memory well under 50% on E-series | GP→MO (or bigger), or MO→GP |
| `iops`, `disk_iops_consumed_percentage`, `disk_queue_depth` | Above 80–90% consumed, or rising queue depth | Consistently below 20% | Add SSD v2 IOPS, raise Premium SSD performance tier, or bigger VM if the VM cap binds |
| `storage_percent`, `storage_free` | Above 80% (read-only at 95%) | — (can't shrink) | Enable autogrow (Premium SSD) or scale storage |
| `active_connections` vs `max_connections`, failed connections | Above 80% of max, or "too many clients" errors | — | PgBouncer first; scale RAM second |
| `physical_replication_delay_in_seconds` / read replica lag | Lag growing under load | — | Bigger replica, or reduce write bursts |
| `backup_storage_used` | Above provisioned storage | — | Shorten retention, reconsider geo-redundant backup |

These thresholds are pragmatic starting points, not Microsoft-published limits. Set metric alerts on them. Azure metrics have 1-minute granularity and 30 days of history. Azure Advisor also surfaces right-sizing recommendations for underused servers.

### How billing works and how to cut it

**How each part is billed**
- **Compute:** billed per vCore-hour, for every full hour the server exists. A server deleted after 5 minutes pays for a full hour. Scaling within an hour bills the higher size.
- **Storage:** billed per provisioned GiB-month whether or not it's used.
- **Premium SSD v2 extras:** IOPS above 3,000 (or 12,000) and throughput above 125 (or 500) MB/s are billed as extra units.
- **Backup:** billed per GiB-month above the free allowance. Geo-redundant backup is charged at twice the price.
- **HA:** the server is billed as 2× compute and 2× storage. The pricing FAQ example: a 4-vCore, 512 GiB HA server "will be billed for 8 vCores and 1,024 GiB of storage."
- **Read replicas:** each is billed as a full server.
- **Extended support:**
  - PostgreSQL 11–13 servers were auto-enrolled, with billing from September 1, 2026.
  - The rate is $0.0700/vCore-hour in East US, according to the Azure Retail Prices API as read by Datapace on Nov 7, 2026. That adds about $204/month on a 4-vCore server. ecorpit (Aug 25, 2026) reports $0.07–$0.161/vCore-hour across 56 regions.
  - Microsoft's pricing page says Year 3 "is charged at twice the Year 1 and Year 2 rate."
  - PostgreSQL 14 follows on February 1, 2027. Upgrade rather than pay.

**Ways to reduce cost, roughly in order of impact**
1. **Stop non-prod servers.** Compute billing stops immediately; storage still bills. Servers auto-start after **7 days**, so schedule a stop with an Automation runbook, GitHub Action or Logic App. Running weekdays only, 10 hours a day, cuts compute by about 70%.
2. **Reserve steady production compute.**
   - Microsoft's cost guide says reservations save "up to 40% for one-year and up to 60% for three-year."
   - The Flexible Server pricing-page FAQ instead quotes "savings up to 47 percent for 1-year, and up to 64 percent for 3-years". Microsoft Learn's reserved-capacity page says "you can save up to 65% on compute costs with reserved instances."
   - East US D-series list prices work out to exactly 40% and 60%.
   - Reservations cover compute only, not storage. They can't be applied to Burstable, but they apply flexibly across sizes within a tier and region and can be exchanged or refunded.
   - Right-size *before* you reserve.
3. **Don't over-engineer non-prod.** Leave HA, geo-redundant backup and 35-day retention off dev and staging. HA on a staging copy is a pure 2× cost.
4. **Prefer Premium SSD v2** so you don't buy capacity just to get IOPS. On Premium SSD, use the performance tier for temporary IOPS boosts instead of permanently doubling the disk.
5. **Scale down off-hours** for predictable daily curves, for example D8 by day and D4 by night, using scheduled `az postgres flexible-server update --sku-name`. Each resize causes a brief disconnect (under 30 seconds when near-zero-downtime applies), so only do this where your app retries cleanly.
6. **Consolidate small databases** onto one server. Microsoft's cost guidance recommends this, but billing is per server, so per-database chargeback becomes harder.

## Recommendations

- **Dev/test:** B1ms or B2s on Premium SSD v1, no HA, 7-day local backups, with an automated nightly stop. If Burstable is blocked in your region, use D2ds_v5 with stop/start.
- **First production deployment (Toronto):** D2ds_v5 or D4ds_v5 in **Canada Central**, Premium SSD v2 at 128–256 GiB, zone-redundant HA, 7–14 day backups, and PgBouncer enabled if you run serverless or many app instances. Set alerts on CPU, memory, IOPS consumed, storage and connections from day one.
- **After 30–60 days of stable metrics:** right-size, then buy a 1-year reservation covering both primary and standby vCores. Move to 3-year once the architecture is settled.
- **Growth path:** tune queries and indexes, then add PgBouncer, then scale up within GP, then move to E-series if memory-bound, then add read replicas for read scale. Consider elastic clusters only for genuine write scale-out.
- **Hygiene:**
  - After every SKU change, re-check `max_connections`.
  - Before creating a server, decide on geo-redundant backup, because you can't change it later.
  - Keep PostgreSQL on a version in standard support to avoid extended-support fees.

## Verification log (checked November 9, 2026 against Microsoft Learn)

| Claim | Result |
|---|---|
| SSD v2 free 3,000 IOPS / 125 MB/s under 400 GiB; 12,000 / 500 MB/s at 400 GiB+; up to 80,000 IOPS | Confirmed (PostgreSQL SSD v2 page). Generic managed-disk docs differ (2,000 MB/s max); PostgreSQL page applies. |
| VM caps D2 3,750, D4 6,400, D16 25,600, D32 51,200 | Confirmed (compute page, benchmark page). D8 12,800 and E-series caps other than E2 not independently confirmed. |
| max_connections 50 / 429 / 859 / 1,718 / 3,437 / 5,000; 15 reserved; unchanged by SKU scale | Confirmed (limits page, Q&A). |
| HA SLA 99.99% zone-redundant, 99.95% same-zone, 99.9% none; backups 7 to 35 days | Confirmed. |
| Read-only at 95% / under 5 GiB; storage can't shrink; autogrow thresholds, doubling, 4,096 GiB boundary; SSD v2 autogrow preview | Confirmed; read-only wording inconsistent in Microsoft pages. |
| PgBouncer port 6432, default pool 50 | Confirmed; also max_client_conn 5,000 and transaction mode default. |
| Read replicas up to 5, 30 with cascading; asynchronous; none on Burstable | Confirmed. |
| Burstable same-zone HA | **Wrong. Corrected:** Burstable has no HA. |
| Backups always ZRS in Canada Central | **Conflicting docs.** Corrected to say confirm at creation. |
| Near-zero-downtime scaling under 30 s | Partly: not for 1 to 2 vCore Burstable; fallback restart roughly 2 to 10 minutes. |
| Reservations "up to 40% / 60%" | Matches the cost guide; other Microsoft pages quote higher maximums. Burstable ineligibility not re-verified. |
| Prices, Datapace/Bytebase figures, Burstable regional block | Third-party or unofficial; not verifiable here. Check the pricing calculator. |

## Caveats

- **Prices change, and the official Canada Central figures couldn't be retrieved.** Microsoft's pricing page loads prices by script, so the official Canada Central rates (and CAD) weren't available to this research.
  - Canada Central compute figures (B1ms ≈ US$14/month, B2ms ≈ US$108, B4ms ≈ US$216, D2ds_v5 ≈ US$145 pay-as-you-go, $87 1-year, $58 3-year) come from Bytebase's rounded, "indicative" tracker. They're consistent with Spare Cores' Canada Central rate of US$0.198/hour for D2ds_v5, and US$0.396/hour with HA.
  - East US rates ($0.089/vCore-hour for D-series v5, $0.115/GiB-month for storage, $0.095/GB-month for backup) come from Datapace reading the Azure Retail Prices API on November 7, 2026.
  - To get exact CAD figures, query the Retail Prices API with `currencyCode='CAD'` and `armRegionName eq 'canadacentral'`, or use the portal's cost estimate.
- **Preview features:** v6 SKUs and SSD v2 autogrow are in preview and may change. The new Bsv2-based Burstable SKUs appear on the pricing page, but the Learn compute docs don't list them yet.
- **Unofficial claim:** the Burstable regional deployment block comes from volunteer moderator "TP" on Microsoft Q&A (Nov 6, 2026), not an official Microsoft announcement.
- **Heuristics:** the sizing ratios (1.5× working set, 65% CPU target) and alert thresholds are engineering rules of thumb. Validate them against load tests on your own workload.