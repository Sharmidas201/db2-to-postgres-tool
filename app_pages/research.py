"""Research & guide page: bite-sized, interactive lessons built from azure_research.md.

Each lesson = a few lines + one thing to play with + a quick check. The full,
unabridged research stays available in the "Full reference" tab.
"""

import math
import re
from pathlib import Path

import streamlit as st

RESEARCH_FILE = Path(__file__).resolve().parents[1] / "azure_research.md"

LESSONS = [
    ("Start here", ":material/flag:"),
    ("Pick a tier", ":material/layers:"),
    ("Burstable trap", ":material/battery_alert:"),
    ("Storage", ":material/hard_drive:"),
    ("Connections", ":material/cable:"),
    ("HA and backups", ":material/shield:"),
    ("Size it yourself", ":material/calculate:"),
    ("Scale up or out", ":material/open_in_full:"),
    ("Watch and resize", ":material/monitoring:"),
    ("Cut the bill", ":material/savings:"),
    ("Launch checklist", ":material/checklist:"),
]
QUIZ_KEYS = {"Start here": ["start"], "Pick a tier": ["tier"], "Burstable trap": ["burst"], "Storage": ["storage", "storage2"], "Connections": ["conn"], "HA and backups": ["ha"], "Size it yourself": ["size"], "Scale up or out": ["scale"], "Watch and resize": ["watch"], "Cut the bill": ["cost"], "Launch checklist": ["checklist"]}
NAMES = [n for n, _ in LESSONS]
ICONS = dict(LESSONS)

# Compute pricing proxies from the research (Canada Central, USD, indicative).
D_VCORE_MONTH = 0.099 * 730
STORAGE_GIB_MONTH = 0.115

D_SKUS = [(2, 8), (4, 16), (8, 32), (16, 64), (32, 128)]  # (vCores, GiB RAM)
E_SKUS = [(2, 16), (4, 32), (8, 64)]


# Storage lesson data (Premium SSD v1 tiers, VM IOPS caps) from the research.
VMS = {"D2ds_v5": (2, 8, 3750), "D4ds_v5": (4, 16, 6400), "D8ds_v5": (8, 32, 12800)}  # vCPU, GiB RAM, IOPS cap
V1_TIERS = [(128, 500), (256, 1100), (512, 2300), (1024, 5000), (2048, 7500)]  # (GiB, IOPS)
DISK_SIZES = [128, 256, 400, 512, 1024, 2048]

# Default max_connections per server size, and PgBouncer's default pool.
CONN_SKUS = {
    "B1ms (2 GiB)": 50,
    "B2s (4 GiB)": 429,
    "D2ds_v5 (8 GiB)": 859,
    "D4ds_v5 (16 GiB)": 1718,
    "D8ds_v5 (32 GiB)": 3437,
}
PGBOUNCER_POOL = 50

# Monitoring lesson: metric -> (unit hint, scale-up trigger, right-size-down trigger or None, action)
METRICS = {
    "cpu_percent (p95 over days)": (75, 30, "Check `pg_stat_statements` for bad queries first, then add vCores."),
    "memory_percent": (90, 50, "If cache hit ratio is also under 99%, go bigger or General Purpose to Memory Optimized."),
    "disk_iops_consumed_percentage": (85, 20, "Add SSD v2 IOPS or raise the Premium SSD tier. If the VM cap binds, move to a bigger VM."),
    "storage_percent": (80, None, "Scale storage or enable autogrow. Read-only at 95%, and you can't shrink."),
    "active connections vs max": (80, None, "PgBouncer first, more RAM second."),
}

CHECKLIST = [
    "Region chosen (Canada Central supports zone-redundant HA and geo backup)",
    "General Purpose D2ds_v5 or D4ds_v5, not Burstable, for production",
    "Premium SSD v2 storage, sized for data + 12 months growth + 30%",
    "VM IOPS cap is above disk IOPS at peak (plus ~30%)",
    "PgBouncer on, app pools small (5 to 20 each)",
    "Zone-redundant HA for prod, none for dev/staging",
    "Backups 7 to 14 days, geo-redundancy decided at creation",
    "Alerts on CPU, memory, IOPS, storage and connections from day one",
    "Reservation only after 30 to 60 days of stable metrics",
]


L = "https://learn.microsoft.com/en-us/azure/postgresql/"  # Microsoft Learn base URL

SOURCES = {
    "Start here": [
        ("third-party", "Single Server retired March 28, 2025; unmigrated servers disabled (Microsoft Q&A staff answer, not re-checked here)", None),
    ],
    "Pick a tier": [
        ("confirmed", "Burstable has no HA and no read replicas; only General Purpose and Memory Optimized do", L + "high-availability/concepts-high-availability"),
        ("confirmed", "D2ds_v5 = 2 vCores / 8 GiB; D4ds_v5 = 4 / 16 (4 GiB per vCore)", L + "compute-storage/concepts-compute"),
        ("nuance", "E-series RAM per vCore (6.75 to 9.5 GiB) and the 24/7 support wording come from the research file, not re-checked", None),
    ],
    "Burstable trap": [
        ("confirmed", "Burstable suits low-cost dev and low-concurrency use; credits can run out and cause timeouts", L + "compute-storage/concepts-compute"),
        ("third-party", "B1ms/B2s/B2ms baselines (20/40/60%) are from Azure's B-series VM docs via the research file", None),
        ("third-party", "$220 vs $65 per sustained vCore is a Datapace estimate (East US), and the regional Burstable block is an unofficial forum answer", None),
    ],
    "Storage": [
        ("confirmed", "SSD v2: 3,000 IOPS / 125 MB/s free up to 399 GiB; 12,000 / 500 MB/s from 400 GiB; up to 80,000 IOPS; IOPS and throughput adjustable separately", L + "compute-storage/concepts-storage-premium-ssd-v2"),
        ("confirmed", "VM caps: D2ds_v5 3,750, D4ds_v5 6,400, D16ds_v5 25,600, D32ds_v5 51,200. Compute size limits what storage can deliver", L + "compute-storage/concepts-compute"),
        ("confirmed", "Storage can't shrink; read-only near 95% full or under 5 GiB free; autogrow doubles size and cost", L + "compute-storage/concepts-storage"),
        ("nuance", "Microsoft words the read-only rule inconsistently (\"or\" vs \"whichever is more\"). Alert early. SSD v2 autogrow was still preview", L + "configure-maintain/concepts-limits"),
        ("nuance", "Premium SSD v1 tier IOPS (500/1,100/2,300/5,000/7,500) come from the research file and Azure disk docs, not the PostgreSQL pages", None),
    ],
    "Connections": [
        ("confirmed", "Defaults: 50 (B1ms), 429 (B2s), 859 (2 vCore), 1,718 (4), 3,437 (8), 5,000 (16+). 15 reserved. Not changed by scaling the SKU", L + "configure-maintain/concepts-limits"),
        ("confirmed", "PgBouncer on port 6432, same hostname; pool size 50; transaction mode default; max_client_conn 5,000", L + "connectivity/concepts-pgbouncer"),
        ("nuance", "The 'database sees at most ~50' shortcut in the widget is simplified: it is 50 per user/database pair", None),
    ],
    "HA and backups": [
        ("confirmed", "SLA: zone-redundant 99.99%, same-zone 99.95%, no HA 99.9%", L + "high-availability/concepts-high-availability"),
        ("confirmed", "Backups 7 days default, up to 35", L + "backup-restore/concepts-backup-restore"),
        ("nuance", "Microsoft's own pages disagree on whether backups are zone-redundant or local when HA is off. Confirm in the portal", "https://learn.microsoft.com/en-us/azure/reliability/reliability-database-postgresql"),
        ("confirmed", "Burstable has no HA. Read replicas: up to 5, 30 with cascading (PostgreSQL 14+), asynchronous", L + "read-replica/concepts-read-replicas"),
        ("third-party", "The $217/month geo-backup example and the \"$1,000 restore\" anecdote are third-party/forum figures", None),
    ],
    "Size it yourself": [
        ("nuance", "The 65% CPU target and 1.5x working-set rule are engineering rules of thumb, not Microsoft limits. Load-test", None),
        ("third-party", "Prices use Bytebase/Datapace estimates and an East US storage proxy. Use the Azure calculator", None),
    ],
    "Scale up or out": [
        ("confirmed", "Near-zero-downtime scaling is skipped when scaling from/to 1 to 2 vCore Burstable, or with capacity limits, replicas, unlogged tables or too few subnet IPs. The fallback restart takes roughly 2 to 10 minutes", L + "scale/concepts-scaling-resources"),
        ("confirmed", "Up to 5 read replicas (30 with cascading, PG 14+), asynchronous, can be cross-region; none on Burstable", L + "read-replica/concepts-read-replicas"),
    ],
    "Watch and resize": [
        ("nuance", "All thresholds (75% CPU, 90% memory, 85% IOPS, 80% storage) are suggested starting points, not Microsoft limits", None),
    ],
    "Cut the bill": [
        ("confirmed", "Microsoft's cost guide: reservations save up to about 40% (1-year) and 60% (3-year)", L + "configure-maintain/how-to-cost-optimization"),
        ("nuance", "Other Microsoft pages quote higher maximums (47%/64%/65%). That Burstable can't be reserved was not re-verified", None),
        ("third-party", "Extended-support fees for PostgreSQL 11 to 13 (from Sept 1, 2026) are from third-party price readings. Verify on the pricing page", None),
    ],
    "Launch checklist": [],
}
STATUS = {
    "confirmed": ("Confirmed", "green", ":material/verified:"),
    "nuance": ("Nuance", "orange", ":material/info:"),
    "third-party": ("Unverified", "gray", ":material/help:"),
}


def sources_box(name: str) -> None:
    rows = SOURCES.get(name, [])
    if not rows:
        return
    n_ok = sum(1 for k, _, _ in rows if k == "confirmed")
    with st.expander(f"How sure are we? {n_ok} of {len(rows)} claims checked against Microsoft Learn", icon=":material/fact_check:"):
        for kind, claim, url in rows:
            label, color, icon = STATUS[kind]
            c1, c2 = st.columns([1, 5], vertical_alignment="center")
            c1.badge(label, icon=icon, color=color)
            c2.markdown(f"{claim}" + (f" ([source]({url}))" if url else ""))
        st.caption("Checked November 9, 2026. Prices and preview features change. Full log is at the end of the Full reference tab.")


def md(text: str) -> None:
    """Markdown with $ escaped so prices don't render as math."""
    st.markdown(text.replace("$", r"\$"))


def quiz(key: str, question: str, options: list[str], answer: int, why: str) -> None:
    """One-question self check. Marks the lesson done on a correct answer."""
    with st.container(border=True):
        st.caption("Quick check")
        pick = st.radio(question, options, index=None, key=f"quiz_{key}")
        if pick is None:
            return
        if options.index(pick) == answer:
            st.success(why, icon=":material/check_circle:")
            st.session_state.done.add(key)
        else:
            st.warning("Not quite. Re-read the lesson above and try again.", icon=":material/refresh:")


def iops_result(label: str, disk_iops: int, vm_cap: int, vm: str, how: str) -> None:
    """One disk type's outcome: what you get, who is the bottleneck, what to do."""
    got = min(disk_iops, vm_cap)
    with st.container(border=True):
        head, badge = st.columns([3, 2], vertical_alignment="center")
        head.markdown(f"**{label}**")
        if disk_iops > vm_cap:
            badge.badge("Server is the bottleneck", icon=":material/dns:", color="orange")
        elif disk_iops < vm_cap:
            badge.badge("Disk is the bottleneck", icon=":material/hard_drive:", color="blue")
        else:
            badge.badge("Perfectly matched", icon=":material/balance:", color="green")
        st.caption(how)
        c1, c2, c3 = st.columns(3)
        c1.metric("You get", f"{got:,}", help="IOPS actually delivered: the lower of the two limits.")
        c2.metric("Disk can give", f"{disk_iops:,}")
        c3.metric("Server allows", f"{vm_cap:,}")
        st.progress(got / max(disk_iops, vm_cap), text=f"Using {got / vm_cap * 100:.0f}% of the server's IOPS limit")
        if disk_iops > vm_cap:
            nxt = next((n for n, (_, _, cap) in VMS.items() if cap >= disk_iops), None)
            fix = f"Move to **{nxt}** to unlock it." if nxt else "Even the biggest VM here can't use it all."
            md(f"{disk_iops - vm_cap:,} disk IOPS are wasted on {vm}. {fix}")
        elif disk_iops < vm_cap:
            md(f"The server has {vm_cap - disk_iops:,} IOPS of spare room. Add disk IOPS to use it.")


def go_next() -> None:
    i = NAMES.index(st.session_state.lesson)
    if i + 1 < len(NAMES):
        st.session_state.lesson = NAMES[i + 1]
        st.session_state.cur = NAMES[i + 1]


def go_prev() -> None:
    i = NAMES.index(st.session_state.lesson)
    if i > 0:
        st.session_state.lesson = NAMES[i - 1]
        st.session_state.cur = NAMES[i - 1]


def pick_lesson() -> None:
    """Pills can be deselected; snap back to the current lesson if so."""
    if st.session_state.lesson is None:
        st.session_state.lesson = st.session_state.cur
    else:
        st.session_state.cur = st.session_state.lesson


# ---------------------------------------------------------------- lessons --

def lesson_start() -> None:
    with st.container(border=True):
        st.caption("New to this? Four words first")
        md(
            "- **Database server:** a computer that stores your app's data and answers questions about it.\n"
            "- **Managed (Azure Flexible Server):** Microsoft runs that computer for you: patches, backups, failover.\n"
            "- **vCore:** one CPU core. The more you have, the more queries run at once.\n"
            "- **RAM (memory):** the server's fast short-term workspace. Data in RAM is quick, data on disk is slower."
        )
    md(
        "**Goal:** pick a sane Azure Database for PostgreSQL setup in about 10 minutes.\n\n"
        "**The whole answer in one line:** start on **General Purpose D2ds_v5 or D4ds_v5**, "
        "**Premium SSD v2** storage, **PgBouncer** on. Everything else is a refinement."
    )
    st.info(
        "Single Server was retired on March 28, 2025. Flexible Server is the only option to plan around.",
        title="One fact to remember",
        icon=":material/info:",
    )
    quiz(
        "start",
        "You find a Terraform file that creates a 'Single Server'. What do you do?",
        ["Keep it, it still works", "Treat it as legacy and target Flexible Server", "Ask Microsoft for an extension"],
        1,
        "Right. Unmigrated Single Server instances were disabled after the deadline.",
    )


def lesson_tier() -> None:
    with st.container(border=True):
        st.caption("First, what is a tier?")
        md(
            "A tier is a **size family** for your server, like car classes:\n\n"
            "- **Burstable:** a scooter. Cheap, fine for light use, struggles under steady load.\n"
            "- **General Purpose:** a sedan. Balanced. The default for real apps.\n"
            "- **Memory Optimized:** a cargo van. Extra RAM for big datasets.\n\n"
            "**Working set** = the data your app touches regularly. If it fits in RAM, queries stay fast."
        )
    md("Pick the one that matches what you're doing:")
    scenario = st.selectbox(
        "What are you building?",
        [
            "Dev/test or demo",
            "Small production app",
            "Read-heavy app",
            "Big working set / analytics",
            "High-throughput OLTP",
        ],
    )
    advice = {
        "Dev/test or demo": ("B1ms or B2s, stopped off-hours", "About $14/month (B1ms). Cheapest, but not for production.", "Burstable"),
        "Small production app": ("D2ds_v5, or D4ds_v5 for headroom", "Predictable CPU and 24/7 support eligibility.", "General Purpose"),
        "Read-heavy app": ("General Purpose primary + 1-2 read replicas", "Replicas are async and each is billed as a full server.", "General Purpose"),
        "Big working set / analytics": ("E-series (E4ds_v5 = 32 GiB, E8ds_v5 = 64 GiB)", "Keeps big indexes cached, room for larger `work_mem`.", "Memory Optimized"),
        "High-throughput OLTP": ("D8 to D32ds_v5 + Premium SSD v2", "VM IOPS ceilings of 12,800 to 51,200; SSD v2 reaches 80,000 IOPS.", "General Purpose"),
    }[scenario]
    with st.container(border=True):
        st.badge(advice[2], icon=":material/layers:", color="blue")
        st.markdown(f"#### {advice[0]}")
        md(advice[1])
    with st.expander("Rule of thumb on memory per vCore"):
        st.table(
            {
                "Tier": ["Burstable", "General Purpose", "Memory Optimized"],
                "RAM per vCore": ["~4 GiB (B1ms 2 GiB)", "4 GiB", "6.75 to 9.5 GiB"],
                "Production?": ["No", "Yes (default)", "Yes, if memory-bound"],
            }
        )
    quiz(
        "tier",
        "Your working set is bigger than RAM but CPU is fine. Which tier?",
        ["Burstable", "General Purpose", "Memory Optimized"],
        2,
        "Yes. E-series gives more RAM per vCore without paying for CPU you don't need.",
    )


def lesson_burst() -> None:
    with st.container(border=True):
        st.caption("First, what are CPU credits?")
        md(
            "Think of a **phone data plan with rollover**. A Burstable VM has a **baseline**: the CPU share "
            "it may use all day (B2s = 40%).\n\n"
            "- Use **less** than baseline: you **earn credits** (saving up).\n"
            "- Use **more** than baseline: you **spend credits** (a burst).\n"
            "- Credits hit **0**: you're **throttled** back to baseline."
        )
    md("Why it matters: throttling means slow queries, timeouts, even an unreachable server. Try it:")
    c1, c2 = st.columns(2)
    size = c1.segmented_control("Size", ["B1ms", "B2s", "B2ms"], default="B2s", required=True, key="burst_size")
    load = c2.slider("Your average CPU use (% of the VM)", 0, 100, 55, key="burst_load")
    baseline = {"B1ms": 20, "B2s": 40, "B2ms": 60}[size]
    st.progress(min(load, 100) / 100, text=f"Load {load}% vs baseline {baseline}%")
    if load <= baseline:
        st.success("Credits refill. Fine for dev/test.", icon=":material/battery_full:")
    else:
        st.error(
            f"You burn credits {load - baseline} points faster than you earn them. "
            "Watch `cpu_credits_remaining`. When it hits 0 you get throttled.",
            icon=":material/battery_alert:",
        )
    md(
        "Cost reality (East US): about **$220** per *usable* vCore on B4ms vs about **$65** on D4ds_v5. "
        "Burstable is the priciest way to get sustained CPU."
    )
    quiz(
        "burst",
        "`cpu_credits_remaining` falls a little every day and never refills overnight. What now?",
        ["Ignore it", "Move to a larger B size or General Purpose", "Raise max_connections"],
        1,
        "Correct. A downward credit trend means you've outgrown Burstable.",
    )


def lesson_storage() -> None:
    with st.container(border=True):
        st.caption("First, what is IOPS?")
        md(
            "**IOPS = Input/Output Operations Per Second**: how many small reads and writes the disk "
            "handles each second.\n\n"
            "Think of a **checkout lane**: IOPS is how many customers it serves per second. "
            "Every query that misses RAM, every commit and every checkpoint is a customer. "
            "Too few IOPS = a queue = slow database.\n\n"
            "Two limits apply, and you get the **lower** of the two:\n\n"
            "- **Disk IOPS:** the speed limit of the **storage** (where data lives). "
            "Set by disk type and size. A 256 GiB Premium SSD gives 1,100.\n"
            "- **VM IOPS:** the speed limit of the **server** (the CPU/RAM machine). "
            "Set by the VM size, whatever disk you attach. A D2ds_v5 gives 3,750.\n\n"
            "**Water pipe picture:** the disk is the tank's outlet, the VM is the pipe to your house. "
            "Water flow = the narrowest part. A huge tank on a thin pipe still trickles. "
            "A fat pipe on a tiny outlet also trickles.\n\n"
            "**Example:** disk allows 7,500, VM allows 3,750 -> you get **3,750**. "
            "Paying for a bigger disk won't help, you need a bigger VM."
        )
    st.markdown("#### Try it: what speed do you really get?")
    md("Two choices, then read the result. **You get the lower of the two limits.**")

    with st.container(border=True):
        st.caption("STEP 1 · Pick the server (VM)")
        vm = st.segmented_control(
            "Server size",
            list(VMS),
            default="D2ds_v5",
            required=True,
            key="disk_vm",
            format_func=lambda n: f"{n} · {VMS[n][0]} vCPU · {VMS[n][1]} GiB RAM",
            label_visibility="collapsed",
        )
        vcpu, ram, vm_cap = VMS[vm]
        st.caption(f":material/dns: This server can move at most **{vm_cap:,} IOPS**, whatever disk you attach.")

    with st.container(border=True):
        st.caption("STEP 2 · Pick the disk")
        size = st.select_slider(
            "Disk size",
            DISK_SIZES,
            value=256,
            key="disk_size",
            format_func=lambda g: f"{g:,} GiB",
        )
        extra = st.slider(
            "Extra IOPS to buy (Premium SSD v2 only, on top of the free amount)",
            0,
            30000,
            0,
            step=1000,
            key="disk_extra",
            format="%d IOPS",
            help="v2 lets you buy IOPS separately from size. Premium SSD v1 cannot: its IOPS come only from disk size.",
        )

    billed = next(s for s, _ in V1_TIERS if size <= s)
    v1_disk = next(i for s, i in V1_TIERS if size <= s)
    v2_disk = min((3000 if size < 400 else 12000) + extra, 500 * size, 80000)  # 500 IOPS per GiB, max 80,000
    if billed != size:
        st.caption(f"Premium SSD v1 only comes in fixed sizes, so {size:,} GiB is billed as **{billed:,} GiB**.")

    st.markdown("##### STEP 3 · Read the result")
    for label, disk_iops, how in [
        ("Premium SSD (v1)", v1_disk, "IOPS come from disk size. To get more, you must buy a bigger disk."),
        ("Premium SSD v2", v2_disk, f"3,000 free (12,000 from 400 GiB), plus {extra:,} bought. Limit: 500 IOPS per GiB, max 80,000. Size and IOPS are set separately."),
    ]:
        iops_result(label, disk_iops, vm_cap, vm, how)

    st.caption("Rule: effective IOPS = min(disk IOPS, VM IOPS cap). Cost trap: paying for disk IOPS the VM can never use.")
    md(
        "**Three storage rules**\n"
        "- Default to **Premium SSD v2** for new servers: 3,000 IOPS free vs 500 to 1,100 on v1 at 128 to 256 GiB.\n"
        "- Storage **only grows**. Start modest.\n"
        "- Server goes **read-only at 95% full** (or under 5 GiB free). Alert at 80%.\n"
        "- v2 allows about **4 IOPS/throughput changes per 24 hours**. Plan changes, don't thrash.\n"
        "- **Autogrow doubles** disk size and cost each time, and doesn't fire during heavy WAL."
    )
    quiz(
        "storage",
        "A D2ds_v5 has a 2 TiB Premium SSD (7,500 IOPS) and disk IOPS are maxed out. Best first fix?",
        ["Buy an even bigger disk", "Move to a bigger VM (D4ds_v5 or D8ds_v5)", "Nothing, 7,500 is plenty"],
        1,
        "Right. The D2ds_v5 caps at 3,750, so the disk is already over-sized. Raise the VM limit.",
    )
    quiz(
        "storage2",
        "You over-provisioned storage by 2x. Can you shrink it?",
        ["Yes, from the portal", "No, storage never shrinks"],
        1,
        "Right. Over-provisioning is a permanent cost.",
    )


def lesson_conn() -> None:
    with st.container(border=True):
        st.caption("First, what is a connection?")
        md(
            "Every open line between your app and the database is a **connection**. Each one, even idle, "
            "uses server memory. There is a hard cap: **`max_connections`**.\n\n"
            "- **Connection pool:** your app keeps a few lines open and reuses them, instead of opening one per request.\n"
            "- **PgBouncer:** a built-in Azure switchboard (port **6432**). Many app connections in, few database connections out.\n"
            "- Azure reserves **15** connections for itself, so you can use `max_connections - 15`."
        )
    md("Count your app's connections and see if the server can take them.")
    sku = st.segmented_control(
        "Server",
        list(CONN_SKUS),
        default="D2ds_v5 (8 GiB)",
        required=True,
        key="conn_sku",
    )
    c1, c2, c3 = st.columns(3)
    inst = c1.number_input("App instances / pods", 1, 500, 3, key="conn_inst")
    pool = c2.slider("Pool size per instance", 1, 50, 20, key="conn_pool")
    extra = c3.number_input("Workers + admin tools", 0, 200, 10, key="conn_extra")
    pgb = st.toggle("Use built-in PgBouncer", value=False, key="conn_pgb")

    total = inst * pool + extra
    limit = CONN_SKUS[sku] - 15
    db_side = min(total, PGBOUNCER_POOL) if pgb else total
    pct = db_side / limit * 100
    m1, m2, m3 = st.columns(3)
    m1.metric("App asks for", f"{total:,}", f"{inst} x {pool} + {extra}", delta_color="off")
    m2.metric("Database sees", f"{db_side:,}", "via PgBouncer" if pgb else "direct", delta_color="off")
    m3.metric("Server allows", f"{limit:,}", "max minus 15 reserved", delta_color="off")
    st.progress(min(pct, 100) / 100, text=f"{pct:.0f}% of allowed connections used")
    if pct > 100:
        st.error("`too many clients` errors. Turn on PgBouncer or shrink the pools. Don't just raise max_connections.", icon=":material/error:")
    elif pct > 80:
        st.warning("Above 80%. One more instance or a deploy surge will hit the wall. Add PgBouncer.", icon=":material/warning:")
    else:
        st.success("Healthy headroom.", icon=":material/check_circle:")
    if pgb:
        st.caption(f"PgBouncer default pool: {PGBOUNCER_POOL} server connections per user/database pair. Use transaction mode for web/API/serverless. Session features like temp tables, LISTEN/NOTIFY and advisory locks break in that mode.")
    md("**Rule:** keep app-side pools small (5 to 20 per instance). Pool first, scale RAM second.")
    quiz(
        "conn",
        "You scale B1ms to B2s but `max_connections` still shows 50. Why?",
        ["Azure bug", "The setting doesn't change with the SKU. Update it and restart", "You need a reservation"],
        1,
        "Right. Re-check max_connections after every SKU change.",
    )


def lesson_ha() -> None:
    with st.container(border=True):
        st.caption("First, what is HA?")
        md(
            "**HA = High Availability.** Azure keeps a **second copy** of your server (the **standby**) "
            "ready. If the main server dies, the standby takes over automatically (**failover**).\n\n"
            "- **Availability zone:** a separate data center building in the same region, with its own power and network.\n"
            "- **SLA:** Microsoft's uptime promise. 99.9% = up to ~8.7 hours down per year. 99.99% = ~52 minutes.\n"
            "- **Backup:** a saved snapshot you can restore from. Different job from HA (see below)."
        )
    md("Pick an HA mode and see what it buys and costs.")
    mode = st.segmented_control("HA mode", ["None", "Same-zone", "Zone-redundant"], default="Zone-redundant", required=True, key="ha_mode")
    sla, mult, note = {
        "None": ("99.9%", 1, "Cheapest. Fine for dev/test and staging."),
        "Same-zone": ("99.95%", 2, "Standby in the same zone. No protection if the zone fails."),
        "Zone-redundant": ("99.99%", 2, "Standby in another zone. Failover in 60 to 120 s, no data loss."),
    }[mode]
    c1, c2 = st.columns(2)
    c1.metric("SLA", sla)
    c2.metric("Compute + storage bill", f"{mult}x")
    st.caption(note)
    st.warning(
        "HA does not protect against your own mistakes. A dropped table replicates to the standby. "
        "That's what backups are for.",
        icon=":material/warning:",
    )
    md(
        "**Backups in 4 lines**\n"
        "- 7 days by default, up to 35.\n"
        "- **Burstable has no HA at all.** Move to General Purpose for HA.\n"
        "- Microsoft's docs disagree on whether backups are zone-redundant or local without HA. Check at creation.\n"
        "- **Read replicas** are a different tool: asynchronous, readable, up to 5 per primary (30 cascading), each billed as a full server.\n"
        "- Backup storage up to 100% of provisioned storage is free.\n"
        "- **Geo-redundant backup can only be chosen at server creation.** Decide up front.\n"
        "- A point-in-time restore makes a *new* server, and you pay for it."
    )
    quiz(
        "ha",
        "Someone runs DROP TABLE on a zone-redundant server. Are you safe?",
        ["Yes, the standby has it", "No, the drop replicated. Restore from backup"],
        1,
        "Correct. HA is about outages, backups are about mistakes.",
    )


def lesson_size() -> None:
    with st.container(border=True):
        st.caption("Inputs explained")
        md(
            "- **Queries per second (QPS):** how many questions your app asks the database each second at its busiest.\n"
            "- **CPU ms per query:** how long the CPU works on one query. Find it with `pg_stat_statements`.\n"
            "- **Hot working set:** the data and indexes you touch in a normal hour. Want it to fit in RAM.\n"
            "- **Headroom:** spare capacity so a spike doesn't crash you. We aim for ~65% CPU use, not 100%."
        )
    md("Plug in your numbers. Same method as the worked Toronto SaaS example.")
    c1, c2 = st.columns(2)
    qps = c1.number_input("Peak queries per second", 1, 100000, 400, step=50)
    ms = c2.number_input("Avg CPU ms per query", 0.1, 500.0, 3.0, step=0.5)
    c3, c4, c5 = st.columns(3)
    ws = c3.number_input("Hot working set (GB)", 1, 4000, 9)
    data = c4.number_input("Data today (GB)", 1, 60000, 60)
    growth = c5.number_input("Growth per month (GB)", 0, 5000, 4)
    ha = st.toggle("Zone-redundant HA", value=True)

    raw_cpu = qps * ms / 1000 / 0.65
    need_cpu = raw_cpu + 1  # headroom for vacuum/background work
    need_ram = ws * 1.5
    storage = math.ceil((data + growth * 12) * 1.3)

    pick = next(((f"D{v}ds_v5", v, r) for v, r in D_SKUS if v >= need_cpu and r >= need_ram), None)
    if pick is None:
        pick = next(((f"E{v}ds_v5", v, r) for v, r in E_SKUS if v >= need_cpu and r >= need_ram), None)

    with st.container(border=True):
        if pick is None:
            st.markdown("#### Beyond one small node")
            st.write("Look at larger SKUs, read replicas, or elastic clusters. Validate with load tests.")
        else:
            name, vcores, ram = pick
            st.markdown(f"#### {name}")
            st.caption(f"{vcores} vCores, {ram} GiB RAM")
            m1, m2, m3 = st.columns(3)
            m1.metric("CPU needed", f"{raw_cpu:.1f} vCores", f"+1 headroom = {need_cpu:.1f}", delta_color="off")
            m2.metric("RAM needed", f"{need_ram:.0f} GB", "1.5x working set", delta_color="off")
            m3.metric("Storage", f"{storage} GiB", "+12 mo growth, +30%", delta_color="off")
            if name.startswith("D"):
                factor = 2 if ha else 1
                total = vcores * D_VCORE_MONTH * factor + storage * STORAGE_GIB_MONTH * factor
                md(f"**Rough pay-as-you-go:** ~${total:,.0f}/month (compute + storage{', incl. HA standby' if ha else ''}). Verify in the Azure calculator.")
            else:
                st.caption("E-series price not in the research. Use the Azure pricing calculator.")
    st.caption("Heuristics (65% CPU target, 1.5x working set) are rules of thumb. Load-test your own workload.")
    st.session_state.done.add("size")


def lesson_scale() -> None:
    with st.container(border=True):
        st.caption("First, scale up vs scale out")
        md(
            "- **Scale up:** a bigger single server (more vCores/RAM). Simple. Fixes CPU/RAM limits and slow single queries.\n"
            "- **Scale out:** add **read replicas**: extra copies that serve reads. Fixes read load, not write load.\n"
            "- **Replication lag:** replicas are asynchronous, so they can be slightly behind the primary."
        )
    md("Pick your symptom to see the next move. Order of operations: tune queries, add PgBouncer, scale up, then replicas.")
    symptom = st.selectbox(
        "What are you seeing?",
        [
            "CPU high, mostly from writes",
            "One query is slow",
            "Reads are 70 to 80% of the load",
            "Cache hit ratio below 99%, CPU fine",
            "'too many clients' errors",
            "Need more write capacity than one server",
        ],
        key="scale_symptom",
    )
    move, why = {
        "CPU high, mostly from writes": ("Scale up (more vCores)", "Replicas don't help writes. Check `pg_stat_statements` for bad queries first."),
        "One query is slow": ("Fix the query/index, then scale up if needed", "More replicas won't speed one query. A bigger VM may."),
        "Reads are 70 to 80% of the load": ("Add 1 or 2 read replicas", "Your app must tolerate lag and route reads separately. Each replica is billed as a full server. Not available on Burstable."),
        "Cache hit ratio below 99%, CPU fine": ("Move to Memory Optimized (E-series)", "More RAM per vCore without paying for CPU you don't need."),
        "'too many clients' errors": ("Turn on PgBouncer", "Pool first, scale RAM second. Don't raise max_connections."),
        "Need more write capacity than one server": ("Look at elastic clusters (Citus-based sharding)", "Only for genuine write scale-out. Validate with a load test."),
    }[symptom]
    with st.container(border=True):
        st.markdown(f"#### {move}")
        md(why)
    with st.expander("When scale-up is NOT near-zero downtime", icon=":material/warning:"):
        md(
            "Scaling normally takes **under 30 seconds** of disconnect. Microsoft says it falls back to a plain "
            "restart (**roughly 2 to 10 minutes**) when:\n"
            "- you scale from or to a **1 or 2 vCore Burstable** size\n"
            "- the region lacks capacity or you hit a quota\n"
            "- the server has replicas or **unlogged tables**\n"
            "- a VNet subnet doesn't have enough free IPs\n\n"
            "Plan resizes for a quiet window and make sure your app retries connections."
        )
    quiz(
        "scale",
        "Reads are 80% of load, writes keep CPU at 40%. Best next step?",
        ["Bigger primary only", "Add a read replica and route reads to it", "Switch to Burstable"],
        1,
        "Yes. Reads can move to an async replica. Check your app tolerates replication lag.",
    )


def lesson_watch() -> None:
    with st.container(border=True):
        st.caption("First, what is right-sizing?")
        md(
            "Sizing is a first guess. **Right-sizing** is adjusting after you see real numbers. "
            "Azure Monitor records metrics every minute and keeps 30 days. "
            "Set alerts on the five below from day one.\n\n"
            "- **p95:** the value 95% of the time stays under. Ignores rare spikes, shows the real busy level.\n"
            "- **Scale up:** a bigger server. Often under 30 s, but can fall back to a 2 to 10 minute restart (see 'Scale up or out').\n"
            "- **Scale down (right-size):** you pay for idle capacity. Check after 2 to 4 weeks."
        )
    md("Pick a metric, set what you see, and read the advice.")
    name = st.selectbox("Metric", list(METRICS), key="watch_metric")
    up, down, action = METRICS[name]
    val = st.slider("What the metric shows (%)", 0, 100, 50, key=f"watch_val_{name}", format="%d%%")
    st.progress(val / 100, text=f"{val}%  (scale up above {up}%" + (f", right-size below {down}%)" if down else ")"))
    if val >= up:
        st.error(f"Time to scale up. {action}", icon=":material/trending_up:")
    elif down is not None and val <= down:
        st.info("Over-provisioned. If this holds for 2 to 4 weeks, go one size down.", icon=":material/trending_down:")
    else:
        st.success("In the healthy band. Keep watching.", icon=":material/check_circle:")
    st.caption("These thresholds are pragmatic starting points, not Microsoft limits. Azure Advisor also flags idle servers.")
    quiz(
        "watch",
        "p95 CPU has sat at 20% for three weeks on a D8ds_v5. What now?",
        ["Scale up for safety", "Right-size down to D4ds_v5", "Buy a 3-year reservation on D8"],
        1,
        "Yes. Right-size first, then reserve. A reservation on the wrong size locks in waste.",
    )


def lesson_checklist() -> None:
    md("Tick what you've covered. This is the whole course in nine lines.")
    checks = [st.checkbox(item, key=f"chk_{i}") for i, item in enumerate(CHECKLIST)]
    n = sum(checks)
    st.progress(n / len(CHECKLIST), text=f"{n} of {len(CHECKLIST)} ready")
    if n == len(CHECKLIST):
        st.success("Ready to deploy. Load-test once before you cut over.", icon=":material/rocket_launch:")
        st.session_state.done.add("checklist")


def lesson_cost() -> None:
    with st.container(border=True):
        st.caption("Pricing words")
        md(
            "- **Pay-as-you-go:** pay by the hour, cancel anytime. Most flexible, most expensive.\n"
            "- **Reservation:** promise to use a server for 1 or 3 years, get a big discount. "
            "Like a gym annual plan.\n"
            "- **Stop/start:** a stopped server stops billing for compute (storage still bills)."
        )
    md("Start from the example's **~$615/month** (D4ds_v5 + zone-redundant HA + 160 GiB). Toggle levers:")
    compute = 290
    standby = 290
    storage = 37
    levers = st.pills(
        "Levers",
        ["1-year reservation (-40%)", "3-year reservation (-60%)", "Drop HA (non-prod)"],
        selection_mode="multi",
        key="cost_levers",
    )
    levers = levers or []
    res = 0.6 if "3-year reservation (-60%)" in levers else 0.4 if "1-year reservation (-40%)" in levers else 0.0
    if "1-year reservation (-40%)" in levers and "3-year reservation (-60%)" in levers:
        st.caption("Reservations don't stack. The 3-year discount is used.")
    ha = "Drop HA (non-prod)" not in levers
    comp = (compute + (standby if ha else 0)) * (1 - res)
    stor = storage if ha else storage / 2
    total = comp + stor
    base = compute + standby + storage
    m1, m2 = st.columns(2)
    m1.metric("Monthly", f"${total:,.0f}", f"-${base - total:,.0f}" if total < base else "baseline", delta_color="normal" if total < base else "off")
    m2.metric("Saved", f"{(1 - total / base) * 100:.0f}%")
    md(
        "**Biggest levers, in order**\n"
        "1. Stop non-prod servers off-hours (about 70% less compute). Auto-restarts after 7 days.\n"
        "2. Reserve steady prod compute. **Right-size first.** Microsoft's cost guide says up to ~40% (1-year) and ~60% (3-year); other pages quote more.\n"
        "3. No HA or geo-backup on dev/staging.\n"
        "4. Premium SSD v2 so you don't buy capacity just for IOPS."
    )
    quiz(
        "cost",
        "When should you buy a reservation?",
        ["Day one, to lock the discount", "After 30 to 60 days of stable metrics and right-sizing"],
        1,
        "Yes. Reserving the wrong size just locks in waste.",
    )


RENDER = {
    "Start here": lesson_start,
    "Pick a tier": lesson_tier,
    "Burstable trap": lesson_burst,
    "Storage": lesson_storage,
    "Connections": lesson_conn,
    "HA and backups": lesson_ha,
    "Size it yourself": lesson_size,
    "Scale up or out": lesson_scale,
    "Watch and resize": lesson_watch,
    "Cut the bill": lesson_cost,
    "Launch checklist": lesson_checklist,
}


# ----------------------------------------------------------- full reference --

def escape_dollars(text: str) -> str:
    return text.replace("$", r"\$")


def render_reference() -> None:
    try:
        text = RESEARCH_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        st.error(f"Research file not found: {RESEARCH_FILE.name}")
        return
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    st.markdown(escape_dollars(parts[0]))
    for i in range(1, len(parts), 2):
        with st.expander(parts[i].strip(), expanded=False):
            st.markdown(escape_dollars(parts[i + 1]))


# --------------------------------------------------------------------- page --

if "done" not in st.session_state:
    st.session_state.done = set()
if "lesson" not in st.session_state:
    st.session_state.lesson = NAMES[0]
if "cur" not in st.session_state:
    st.session_state.cur = st.session_state.lesson


def lesson_done(name: str) -> bool:
    return any(k in st.session_state.done for k in QUIZ_KEYS[name])


with st.container(width=880):
    st.title("Learn: sizing PostgreSQL on Azure")
    learn_tab, ref_tab = st.tabs([":material/school: Guided lessons", ":material/menu_book: Full reference"])

    with learn_tab:
        total = len(NAMES)
        done_n = sum(lesson_done(n) for n in NAMES)
        st.progress(done_n / total, text=f"{done_n} of {total} lessons checked off")

        lesson = st.pills(
            "Lesson",
            NAMES,
            key="lesson",
            on_change=pick_lesson,
            format_func=lambda n: f"{':material/check_circle:' if lesson_done(n) else ICONS[n]} {n}",
            label_visibility="collapsed",
        )
        lesson = lesson or st.session_state.cur
        idx = NAMES.index(lesson)
        st.subheader(f"{idx + 1}. {lesson}")
        RENDER[lesson]()
        sources_box(lesson)

        prev_col, next_col = st.columns(2)
        if idx > 0:
            prev_col.button(f"Back: {NAMES[idx - 1]}", on_click=go_prev, icon=":material/arrow_back:")
        if idx + 1 < total:
            next_col.button(f"Next: {NAMES[idx + 1]}", on_click=go_next, icon=":material/arrow_forward:", type="primary")
        else:
            st.success("That's the whole path. The Full reference tab has every detail and source.", icon=":material/celebration:")

    with ref_tab:
        render_reference()
