from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import evidence_passport as ep  # noqa: E402


class EvidencePassportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manifest_path = self.root / "run.json"
        self.protocol_path = self.root / "protocol.txt"
        self.results_path = self.root / "result.csv"
        self.protocol_path.write_text("locked protocol v1\n", encoding="utf-8")
        self.results_path.write_text("metric,value\nrecall,0.8\n", encoding="utf-8")
        self.manifest = {
            "schema_version": 1,
            "run_id": "test-run-1",
            "project": {
                "name": "Example Lab Project",
                "version": "0.1",
                "source_url": None,
                "source_note": "Local test fixture; no repository URL asserted.",
            },
            "evidence_class": "public_dataset",
            "dataset": {
                "name": "Example public dataset",
                "kind": "public benchmark",
                "description": "A small test fixture.",
                "source_url": "https://example.invalid/data",
            },
            "code": {"version": "0.1", "commit": None},
            "seed": 42,
            "protocol": {
                "name": "Example protocol",
                "version": "1",
                "sha256": hashlib.sha256(self.protocol_path.read_bytes()).hexdigest(),
                "locked_at": "not independently verified",
                "lock_commit": None,
                "description": "A test protocol.",
            },
            "baselines": ["baseline-A"],
            "results": [
                {
                    "scope": "dataset-A",
                    "method": "candidate",
                    "metrics": [
                        {"name": "recall", "value": 0.8, "unit": "fraction", "interval_95": [0.6, 0.9]},
                    ],
                }
            ],
            "result_label": "descriptive_only",
            "interpretation": "The fixture reports the provided value without recalculation.",
            "limitations": ["Test-only fixture."],
            "artifacts": [
                {
                    "path": "protocol.txt",
                    "role": "protocol",
                    "description": "Protocol fixture.",
                    "sha256": hashlib.sha256(self.protocol_path.read_bytes()).hexdigest(),
                },
                {
                    "path": "result.csv",
                    "role": "results",
                    "description": "Results fixture.",
                    "sha256": hashlib.sha256(self.results_path.read_bytes()).hexdigest(),
                },
            ],
        }
        self.write_manifest()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_manifest(self) -> None:
        self.manifest_path.write_text(json.dumps(self.manifest, indent=2) + "\n", encoding="utf-8")

    def test_valid_manifest_preserves_project_and_public_result_labels(self) -> None:
        normalized = ep.load_and_validate(self.manifest_path)
        self.assertEqual(normalized["project"]["name"], "Example Lab Project")
        self.assertEqual(normalized["evidence_class"], "public_dataset")
        self.assertEqual(normalized["result_label"], "descriptive_only")
        self.assertTrue(normalized["integrity"]["bundle_consistent"])
        self.assertEqual(len(normalized["integrity"]["files"]), 2)

    def test_synthetic_label_is_kept_separate(self) -> None:
        self.manifest["evidence_class"] = "synthetic"
        self.manifest["result_label"] = "synthetic_example"
        self.write_manifest()
        normalized = ep.load_and_validate(self.manifest_path)
        self.assertEqual(normalized["evidence_class"], "synthetic")
        self.assertEqual(normalized["result_label"], "synthetic_example")
        self.assertIn("SYNTHETIC EXAMPLE", ep.render_html(normalized))

    def test_sha256_mismatch_fails_closed(self) -> None:
        self.results_path.write_text("metric,value\nrecall,0.9\n", encoding="utf-8")
        with self.assertRaisesRegex(ep.ManifestError, "SHA-256 mismatch for result.csv"):
            ep.load_and_validate(self.manifest_path)

    def test_invalid_evidence_class_is_rejected(self) -> None:
        self.manifest["evidence_class"] = "mixed"
        self.write_manifest()
        with self.assertRaisesRegex(ep.ManifestError, "evidence_class"):
            ep.load_and_validate(self.manifest_path)

    def test_public_dataset_cannot_be_labeled_synthetic_example(self) -> None:
        self.manifest["result_label"] = "synthetic_example"
        self.write_manifest()
        with self.assertRaisesRegex(ep.ManifestError, "cannot use result_label"):
            ep.load_and_validate(self.manifest_path)

    def test_path_traversal_is_rejected(self) -> None:
        self.manifest["artifacts"][1]["path"] = "../outside.txt"
        self.write_manifest()
        with self.assertRaisesRegex(ep.ManifestError, "safe relative path"):
            ep.load_and_validate(self.manifest_path)

    def test_protocol_hash_must_match_protocol_artifact(self) -> None:
        self.manifest["protocol"]["sha256"] = "0" * 64
        self.write_manifest()
        with self.assertRaisesRegex(ep.ManifestError, "protocol.sha256 must equal"):
            ep.load_and_validate(self.manifest_path)

    def test_build_writes_offline_html_and_normalized_json(self) -> None:
        output = self.root / "reports"
        result = ep.main(["build", str(self.manifest_path), "--out-dir", str(output)])
        self.assertEqual(result, 0)
        html_path = output / "test-run-1.html"
        json_path = output / "test-run-1.normalized.json"
        self.assertTrue(html_path.is_file())
        self.assertTrue(json_path.is_file())
        rendered = html_path.read_text(encoding="utf-8")
        normalized = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertIn("Example Lab Project", rendered)
        self.assertIn("SHA-256 matching proves only", rendered)
        self.assertIn("public_dataset", rendered)
        self.assertNotIn("<script", rendered.lower())
        self.assertNotIn("<img", rendered.lower())
        self.assertEqual(normalized["schema"], ep.NORMALIZED_SCHEMA)
        self.assertEqual(normalized["results"][0]["metrics"][0]["value"], 0.8)
        self.assertEqual(normalized["project"]["name"], "Example Lab Project")

    def test_duplicate_json_keys_are_rejected(self) -> None:
        self.manifest_path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        with self.assertRaisesRegex(ep.ManifestError, "duplicate JSON key"):
            ep.read_json(self.manifest_path)


if __name__ == "__main__":
    unittest.main()
