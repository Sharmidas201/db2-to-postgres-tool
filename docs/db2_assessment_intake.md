# Db2 to PostgreSQL assessment intake

## Purpose and scope

This first assessment milestone is offline. It consumes metadata exports supplied by a Db2 platform owner; it does not connect to Db2, store credentials, convert DDL, or claim PostgreSQL compatibility. It reports what evidence was supplied, validates its structure, and flags missing or inconsistent evidence for follow-up.

Supported source platform labels:

- Db2 LUW
- Db2 for z/OS
- Db2 for i

These products have different catalog layouts. Each owner should export from the catalog documentation for their platform and release, then map the result into the common CSV contract below. Preserve the original catalog/view name in `source_catalog` or `capture_method`.

## Artifact bundle

Download `db2_assessment_template.zip` from the Db2 assessment page. It contains `manifest.json`, four header-only CSV files, and a README. Upload the populated ZIP or the CSV files directly.

The manifest identifies the platform, source version or function level, source label, extraction date, and method. Do not put credentials or connection strings in the bundle.

### `objects.csv`

One row per catalog object.

Required: `object_type`, `schema_name`, `object_name`.

Optional: `catalog_name`, `specific_name`, `status`, `created_at`, `last_altered_at`, `source_catalog`.

Include tables, views, aliases, materialized query tables, indexes, constraints, routines, triggers, packages, sequences, user-defined types, and other relevant Db2 objects as the platform exposes them. Retain the source object type; do not collapse vendor-specific types during extraction.

### `columns.csv`

One row per table column.

Required: `table_schema`, `table_name`, `column_name`, `data_type`.

Optional: `table_catalog`, `ordinal_position`, `length`, `precision`, `scale`, `nullable`, `default_expression`, `generated_expression`.

DDL text is not required for this intake phase. Column metadata is needed to inventory data types and support later compatibility rules.

### `dependencies.csv`

One row per dependent-object to referenced-object edge.

Required: `dependent_type`, `dependent_schema`, `dependent_name`, `referenced_type`, `referenced_schema`, `referenced_name`.

Optional: `dependent_catalog`, `referenced_catalog`, `dependency_type`, `capture_method`.

Capture the provenance (`source_catalog`, `package metadata`, `application source`, etc.) where possible. Catalog rows do not guarantee full runtime dependency coverage; dynamic SQL, application-generated SQL, job schedulers, external services, and operational processes can require separate evidence.

### `metrics.csv`

One row per database, schema, or object metric.

Required: `scope_type`, `metric_name`, `metric_value`, `unit`.

Optional: `catalog_name`, `schema_name`, `object_name`, `observed_at`.

Examples include allocated bytes, used bytes, row count, peak CPU, memory, I/O rate, and observation window. Clearly distinguish bytes from pages, decimal units from binary units, and peak from average measurements.

## Platform catalog starting points

Use documentation matching the installed Db2 version and function level before asking an owner to run exports.

- **LUW:** IBM recommends application use of read-only `SYSCAT` views. The catalog roadmap includes object, table, routine, package, and dependency views such as `TABDEP`, `ROUTINEDEP`, `PACKAGEDEP`, and `TRIGDEP`. [IBM catalog view roadmap](https://www.ibm.com/docs/en/db2/12.1.x?topic=views-road-map-catalog)
- **z/OS:** start with `SYSIBM` catalog tables. Dependency exports can involve `SYSDEPENDENCIES`, `SYSVIEWDEP`, `SYSPACKDEP`, and other catalogs depending on object type and Db2 release/function level. [IBM SYSDEPENDENCIES](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-sysdependencies) · [IBM SYSPACKDEP](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=spaces-syspackdep)
- **IBM i:** start with `QSYS2` catalog views such as `SYSVIEWDEP`, `SYSROUTINEDEP`, `SYSTRIGDEP`, and `SYSCSTDEP`. [IBM Db2 for i catalog views](https://www.ibm.com/docs/en/i/7.4.0?topic=reference-db2-i-catalog-views) · [IBM SYSROUTINEDEP](https://www.ibm.com/docs/ssw_ibm_i_74/db2/rbafzcatsysrdep.htm)

PostgreSQL records object dependencies in `pg_depend`; this can inform a later target-side comparison and validation stage. [PostgreSQL pg_depend](https://www.postgresql.org/docs/current/catalog-pg-depend.html)

## Current report behavior

The page reports source context, object/column/dependency/metric counts, required-field validation, duplicate object identifiers, and dependency endpoints that do not match the supplied object inventory. Missing metadata is reported as a coverage finding, not silently interpreted as incompatibility. No overall compatibility percentage is generated.

## Later milestones

1. Add reviewed, versioned export queries or platform-specific mapping profiles for each supported Db2 release.
2. Add Db2-to-PostgreSQL compatibility rules with object-level evidence, severity, recommendation, and rule provenance.
3. Add application/runtime dependency sources and explicit coverage/completeness reporting.
4. When approved, add DDL/routine analysis and target-side validation against PostgreSQL catalogs.
5. Add workload sizing and migration complexity/effort estimates only after agreeing on the required performance evidence and scoring method.
