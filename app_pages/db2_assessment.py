"""Offline Db2 to PostgreSQL assessment intake and evidence coverage report."""

import io

import streamlit as st

from core.db2_assessment import (
    PLATFORMS,
    PLATFORM_GUIDANCE,
    make_demo_bundle,
    load_bundle,
    load_csv_uploads,
    make_report_bytes,
    make_template_bundle,
    validate_assessment,
)
from core.db2_rules import PG_VERSIONS


st.title("Db2 to PostgreSQL assessment")
st.caption("Import DBA-provided metadata exports, validate evidence coverage, and identify assessment gaps. No live database connection is used.")

with st.container(border=True):
    st.subheader("1. Get the export template")
    st.write("Download the standard bundle and ask the Db2 platform owner to populate it from approved catalog exports. Platform-specific catalog names can be recorded in `source_catalog`.")
    st.download_button(
        "Download Db2 assessment template (.zip)",
        data=make_template_bundle(),
        file_name="db2_assessment_template.zip",
        mime="application/zip",
        icon=":material/download:",
    )
    st.markdown("**Platform-specific synthetic demos**")
    demo_downloads = st.columns(3)
    for demo_col, demo_platform, filename in zip(
        demo_downloads,
        ["Db2 LUW", "Db2 for z/OS", "Db2 for i"],
        ["db2_luw_synthetic_demo.zip", "db2_zos_synthetic_demo.zip", "db2_i_synthetic_demo.zip"],
    ):
        demo_col.download_button(
            f"Download {demo_platform} demo",
            data=make_demo_bundle(demo_platform),
            file_name=filename,
            mime="application/zip",
            icon=":material/science:",
            help=f"Fictional {demo_platform} metadata; not exported from a real Db2 database.",
        )

st.subheader("2. Upload an assessment export")
st.caption("Upload the completed ZIP bundle, or upload one or more canonical CSV files named objects.csv, columns.csv, dependencies.csv, and metrics.csv.")
zip_upload = st.file_uploader("Assessment bundle (.zip)", type=["zip"], key="db2_bundle_upload")
csv_uploads = st.file_uploader("Or select canonical CSV exports", type=["csv"], accept_multiple_files=True, key="db2_csv_uploads")

manifest = {}
frames = {}
parse_errors = []
if zip_upload is not None:
    manifest, frames, parse_errors = load_bundle(zip_upload)
elif csv_uploads:
    frames, parse_errors = load_csv_uploads(csv_uploads)

with st.form("db2_assessment_context"):
    platform_options = list(PLATFORMS)
    manifest_platform = manifest.get("platform", "")
    try:
        default_platform_index = platform_options.index(manifest_platform)
    except ValueError:
        default_platform_index = 0
    platform = st.selectbox("Db2 platform", platform_options, index=default_platform_index)
    col_version, col_date = st.columns(2)
    source_version = col_version.text_input("Db2 version / function level", value=str(manifest.get("source_version", "")))
    extracted_at = col_date.text_input("Metadata extracted date (YYYY-MM-DD)", value=str(manifest.get("extracted_at", "")))
    source_name = st.text_input("Source system label (optional)", value=str(manifest.get("source_name", "")))
    st.markdown("**PostgreSQL target and sizing assumptions**")
    target_col1, target_col2 = st.columns(2)
    target_service = target_col1.selectbox("Target service", ["PostgreSQL (self-managed)", "Azure Database for PostgreSQL Flexible Server"])
    target_version = target_col2.selectbox("PostgreSQL major version", PG_VERSIONS, index=PG_VERSIONS.index("16"))
    size_col1, size_col2, size_col3 = st.columns(3)
    growth_percent = size_col1.number_input("Expected growth (%)", min_value=0.0, max_value=10000.0, value=0.0, step=10.0)
    headroom_percent = size_col2.number_input("Capacity headroom (%)", min_value=0.0, max_value=1000.0, value=20.0, step=5.0)
    target_storage_gib_input = size_col3.number_input("Configured target storage (GiB; 0 = unknown)", min_value=0.0, value=0.0, step=10.0)
    run_assessment = st.form_submit_button("Validate assessment evidence", type="primary", icon=":material/fact_check:")

demo_platform = None
demo_run_columns = st.columns(3)
for demo_col, candidate_platform in zip(demo_run_columns, ["Db2 LUW", "Db2 for z/OS", "Db2 for i"]):
    if demo_col.button(f"Run {candidate_platform} demo", icon=":material/play_arrow:", help="Loads fictional platform-shaped metadata directly; no live database connection is used."):
        demo_platform = candidate_platform

if demo_platform:
    demo_manifest, demo_frames, demo_errors = load_bundle(io.BytesIO(make_demo_bundle(demo_platform)))
    demo = validate_assessment(
        demo_manifest.get("platform", demo_platform),
        demo_manifest.get("source_version", "Synthetic example"),
        demo_manifest.get("extracted_at", ""),
        demo_frames,
        target_version="16",
    )
    demo["context"]["source_name"] = demo_manifest.get("source_name", "Synthetic demo")
    demo["parse_errors"] = demo_errors
    st.session_state.db2_assessment = demo
    st.rerun()

if run_assessment:
    assessment = validate_assessment(
        platform, source_version, extracted_at, frames,
        target_version=target_version,
        target_service=target_service,
        growth_percent=growth_percent,
        headroom_percent=headroom_percent,
        target_storage_gib=target_storage_gib_input or None,
    )
    assessment["context"]["source_name"] = source_name.strip()
    assessment["parse_errors"] = parse_errors
    st.session_state.db2_assessment = assessment

assessment = st.session_state.get("db2_assessment")
if assessment:
    st.divider()
    st.subheader("Assessment intake results")
    context = assessment["context"]
    st.caption(f"{context['platform_description']} · Db2 {context['source_version']} → PostgreSQL {context['target_version']} ({context['target_service']}) · Extracted {context['extracted_at']}")

    parse_errors = assessment.get("parse_errors", [])
    for error in parse_errors + assessment["errors"]:
        st.error(error)
    if not parse_errors and not assessment["errors"]:
        st.success("The assessment context and required fields are valid. Findings below describe evidence coverage; they are not a PostgreSQL compatibility score.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Db2 objects", f"{context['object_count']:,}")
    m2.metric("Columns", f"{context['column_count']:,}")
    m3.metric("Dependency edges", f"{context['dependency_count']:,}")
    m4.metric("Metric records", f"{context['metric_count']:,}")

    st.metric("Preliminary assessment status", context["preliminary_readiness"])
    st.info("Compatibility checks compare uploaded Db2 catalog facts with documented PostgreSQL capabilities. Unknown or behavior-sensitive mappings go to review; this is not automatic DDL conversion or a readiness score.")

    with st.expander("Platform-specific catalog guidance", expanded=False):
        st.write(PLATFORM_GUIDANCE[context["platform"]])
        if context["platform"] == "Db2 LUW":
            st.markdown("[IBM LUW catalog view roadmap](https://www.ibm.com/docs/en/db2/12.1.x?topic=views-road-map-catalog)")
        elif context["platform"] == "Db2 for z/OS":
            st.markdown("[IBM z/OS SYSDEPENDENCIES](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-sysdependencies) · [IBM z/OS SYSPACKDEP](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=spaces-syspackdep)")
        else:
            st.markdown("[IBM Db2 for i catalog views](https://www.ibm.com/docs/en/i/7.4.0?topic=reference-db2-i-catalog-views) · [IBM SYSROUTINEDEP](https://www.ibm.com/docs/ssw_ibm_i_74/db2/rbafzcatsysrdep.htm)")
        st.info("Catalog dependencies are evidence, not a guarantee of every runtime dependency. Dynamic SQL, application code, schedulers, and external integrations may need separate exports or owner confirmation.")

    left, right = st.columns([1.35, 1])
    with left:
        st.markdown("#### Export coverage")
        st.dataframe(assessment["coverage"], hide_index=True, width="stretch")
    with right:
        st.markdown("#### Findings")
        st.dataframe(assessment["findings"], hide_index=True, width="stretch", height=420)

    with st.expander("Inspect imported canonical metadata"):
        for name, frame in assessment["frames"].items():
            st.markdown(f"**{name.title()}** · {len(frame):,} rows")
            st.dataframe(frame.head(50), hide_index=True, width="stretch")

    with st.expander("Db2 to PostgreSQL type compatibility", expanded=True):
        rule_results = assessment.get("rule_results")
        if rule_results is None or rule_results.empty:
            st.caption("No column metadata was provided to evaluate.")
        else:
            st.caption("Mappings use declared source types, lengths, precision, and scale. Compatible means the basic target type exists; runtime values, SQL behavior, collations, and application semantics still need validation.")
            st.dataframe(rule_results, hide_index=True, width="stretch")

    with st.expander("Target service object checks"):
        object_rules = assessment.get("object_rule_results")
        if object_rules is None or object_rules.empty:
            st.caption("No known object-level service constraints were found for this target selection.")
        else:
            st.dataframe(object_rules, hide_index=True, width="stretch")

    with st.expander("Target storage estimate", expanded=True):
        st.caption("Estimate uses source database-level allocated/used-size metadata, then applies the growth and headroom assumptions selected above. It is not a physical Db2-to-PostgreSQL conversion ratio; validate with a representative load and indexes/workload.")
        st.dataframe(assessment.get("sizing"), hide_index=True, width="stretch")

    st.download_button(
        "Download assessment evidence report (.xlsx)",
        data=make_report_bytes(assessment),
        file_name=f"{context['platform'].lower().replace(' ', '_')}_assessment_intake.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/table_view:",
    )
