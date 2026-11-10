import io
import unittest

import pandas as pd

from core.db2_assessment import (
    CSV_FIELDS,
    load_bundle,
    make_demo_bundle,
    make_template_bundle,
    validate_assessment,
)
from core.db2_rules import evaluate_column_rules, evaluate_object_rules, estimate_target_storage


class Db2AssessmentBundleTests(unittest.TestCase):
    def test_synthetic_bundle_loads_and_validates_end_to_end(self):
        manifest, frames, parse_errors = load_bundle(io.BytesIO(make_demo_bundle()))
        self.assertEqual(parse_errors, [])
        self.assertEqual(manifest["platform"], "Db2 LUW")

        result = validate_assessment(
            manifest["platform"],
            manifest["source_version"],
            manifest["extracted_at"],
            frames,
        )

        self.assertEqual(result["errors"], [])
        self.assertEqual(result["context"]["object_count"], 4)
        self.assertEqual(result["context"]["column_count"], 6)
        self.assertEqual(result["context"]["dependency_count"], 3)
        self.assertEqual(result["context"]["metric_count"], 3)
        self.assertEqual(result["context"]["preliminary_readiness"], "Review required")
        self.assertGreaterEqual(int((result["rule_results"]["Status"] == "Review required").sum()), 1)
        self.assertEqual(result["context"]["target_version"], "16")
        self.assertFalse(result["findings"]["Finding"].str.contains("endpoints absent").any())
        self.assertTrue((result["coverage"]["Status"] == "Ready").all())

    def test_template_bundle_contains_manifest_and_canonical_csvs(self):
        manifest, frames, errors = load_bundle(io.BytesIO(make_template_bundle()))
        self.assertEqual(errors, [])
        self.assertIn("platform", manifest)
        self.assertEqual(set(frames), set(CSV_FIELDS))
        for name, expected_fields in CSV_FIELDS.items():
            self.assertEqual(list(frames[name].columns), expected_fields)
            self.assertTrue(frames[name].empty)

    def test_each_platform_has_a_distinct_loadable_demo_bundle(self):
        expected_catalogs = {
            "Db2 LUW": "SYSCAT.TABLES",
            "Db2 for z/OS": "SYSIBM.SYSTABLES",
            "Db2 for i": "QSYS2.SYSTABLES",
        }
        for platform, expected_catalog in expected_catalogs.items():
            with self.subTest(platform=platform):
                manifest, frames, errors = load_bundle(io.BytesIO(make_demo_bundle(platform)))
                self.assertEqual(errors, [])
                self.assertEqual(manifest["platform"], platform)
                self.assertIn(expected_catalog, set(frames["objects"]["source_catalog"]))
                assessment = validate_assessment(platform, manifest["source_version"], manifest["extracted_at"], frames)
                self.assertEqual(assessment["errors"], [])
                self.assertGreater(assessment["context"]["column_count"], 0)
                self.assertGreater(assessment["context"]["dependency_count"], 0)

    def test_missing_required_headers_are_reported(self):
        result = validate_assessment(
            "Db2 for z/OS",
            "13",
            "2026-11-09",
            {"objects": pd.DataFrame({"name": ["T1"]})},
        )
        self.assertTrue(any("objects.csv is missing required columns" in error for error in result["errors"]))
        self.assertEqual(result["context"]["platform"], "Db2 for z/OS")

    def test_bundle_rejects_invalid_zip(self):
        manifest, frames, errors = load_bundle(io.BytesIO(b"not a zip"))
        self.assertEqual(manifest, {})
        self.assertEqual(frames, {})
        self.assertTrue(any("not a readable ZIP" in error for error in errors))

    def test_data_driven_type_mappings_use_catalog_dimensions(self):
        columns = pd.DataFrame([
            {"table_schema": "APP", "table_name": "T", "column_name": "NAME", "data_type": "VARCHAR", "length": "200"},
            {"table_schema": "APP", "table_name": "T", "column_name": "AMOUNT", "data_type": "DECIMAL", "precision": "31", "scale": "4"},
            {"table_schema": "APP", "table_name": "T", "column_name": "ODD", "data_type": "MY_CUSTOM_TYPE"},
        ])
        result = evaluate_column_rules(columns, target_version="16")
        self.assertEqual(result.iloc[0]["Status"], "Compatible")
        self.assertEqual(result.iloc[0]["Proposed target type"], "varchar(200)")
        self.assertEqual(result.iloc[1]["Status"], "Compatible")
        self.assertEqual(result.iloc[1]["Proposed target type"], "numeric")
        self.assertEqual(result.iloc[2]["Status"], "Insufficient evidence")

    def test_varchar_limit_comes_from_postgresql_capability_not_manager_policy(self):
        columns = pd.DataFrame([
            {"data_type": "VARCHAR", "length": "10485760"},
            {"data_type": "VARCHAR", "length": "10485761"},
        ])
        result = evaluate_column_rules(columns)
        self.assertEqual(list(result["Status"]), ["Compatible", "Potential incompatibility"])

    def test_storage_estimate_uses_database_metric_and_explicit_assumptions(self):
        metrics = pd.DataFrame([{
            "scope_type": "DATABASE", "metric_name": "allocated_size",
            "metric_value": str(100 * 1024**3), "unit": "bytes",
        }])
        result = estimate_target_storage(metrics, growth_percent=10, headroom_percent=20, target_storage_gib=100)
        self.assertAlmostEqual(result.iloc[0]["Source allocated GiB"], 100)
        self.assertAlmostEqual(result.iloc[0]["Estimated target GiB"], 132)
        self.assertEqual(result.iloc[0]["Status"], "Review required")

    def test_azure_flexible_server_tablespace_constraint_is_target_specific(self):
        objects = pd.DataFrame([{"object_type": "TABLESPACE", "schema_name": "", "object_name": "FAST_TS"}])
        result = evaluate_object_rules(objects, "Azure Database for PostgreSQL Flexible Server")
        self.assertEqual(result.iloc[0]["Status"], "Potential incompatibility")
        self.assertTrue(evaluate_object_rules(objects, "PostgreSQL (self-managed)").empty)


if __name__ == "__main__":
    unittest.main()
