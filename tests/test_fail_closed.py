"""Fail-closed, HTML-escaping and label-warning tests for Evidence Passport.

Each case starts from the valid fixture in ``test_evidence_passport`` and
changes one thing. Rejections must raise ``ManifestError`` (exit code 2 from
the CLI) and write no report files.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import evidence_passport as ep  # noqa: E402
from test_evidence_passport import EvidencePassportTests  # noqa: E402

Mutation = Callable[[dict[str, Any], Path], None]


def _set(path: list[Any], value: Any) -> Mutation:
    def mutate(data: dict[str, Any], _root: Path) -> None:
        node: Any = data
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    return mutate


def _drop(key: str) -> Mutation:
    return lambda data, _root: data.pop(key)


def _symlink_outside(data: dict[str, Any], root: Path) -> None:
    outside = Path(tempfile.mkdtemp()) / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    os.symlink(outside, root / "link.txt")
    data["artifacts"][1]["path"] = "link.txt"
    data["artifacts"][1]["sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()


def _duplicate_artifact(data: dict[str, Any], _root: Path) -> None:
    data["artifacts"].append(copy.deepcopy(data["artifacts"][1]))


def _two_protocols(data: dict[str, Any], _root: Path) -> None:
    data["artifacts"][1]["role"] = "protocol"


def _duplicate_metric(data: dict[str, Any], _root: Path) -> None:
    metrics = data["results"][0]["metrics"]
    metrics.append(copy.deepcopy(metrics[0]))


# (name, mutation, fragment expected in the error message)
REJECTED: list[tuple[str, Mutation, str]] = [
    ("missing run_id", _drop("run_id"), "missing required field(s): run_id"),
    ("missing protocol", _drop("protocol"), "missing required field(s): protocol"),
    ("missing limitations", _drop("limitations"), "missing required field(s): limitations"),
    ("missing nested project.name", lambda d, _r: d["project"].pop("name"), "project is missing"),
    ("unknown top-level field", _set(["unexpected"], 1), "unknown field(s): unexpected"),
    ("unknown nested metric field", _set(["results", 0, "metrics", 0, "extra"], 1), "unknown field(s): extra"),
    ("schema_version 2", _set(["schema_version"], 2), "schema_version must be integer 1"),
    ("schema_version as string", _set(["schema_version"], "1"), "schema_version must be integer 1"),
    ("seed as string", _set(["seed"], "42"), "seed must be a non-negative integer"),
    ("seed as bool", _set(["seed"], True), "seed must be a non-negative integer"),
    ("seed negative", _set(["seed"], -1), "seed must be a non-negative integer"),
    ("metric value string", _set(["results", 0, "metrics", 0, "value"], "0.8"), "must be a finite number"),
    ("metric value bool", _set(["results", 0, "metrics", 0, "value"], True), "must be a finite number"),
    ("metric null without note", _set(["results", 0, "metrics", 0, "value"], None), "needs a note"),
    ("interval reversed", _set(["results", 0, "metrics", 0, "interval_95"], [0.9, 0.6]), "lower bound exceeds"),
    ("interval wrong length", _set(["results", 0, "metrics", 0, "interval_95"], [0.6]), "two-number array"),
    ("duplicate metric", _duplicate_metric, "duplicate metric"),
    ("empty results", _set(["results"], []), "results must be a non-empty array"),
    ("empty artifacts", _set(["artifacts"], []), "artifacts must be a non-empty array"),
    ("empty string field", _set(["interpretation"], "   "), "interpretation must be a non-empty string"),
    ("invalid evidence_class", _set(["evidence_class"], "measured"), "evidence_class must be"),
    ("invalid result_label", _set(["result_label"], "passed"), "result_label must be one of"),
    ("run_id with path separator", _set(["run_id"], "../evil"), "run_id may contain only"),
    ("run_id too long", _set(["run_id"], "a" * 102), "run_id may contain only"),
    ("javascript: project URL", _set(["project", "source_url"], "javascript:alert(1)"), "HTTP(S) URL"),
    ("ftp dataset URL", _set(["dataset", "source_url"], "ftp://example.invalid/x"), "HTTP(S) URL"),
    ("protocol sha not hex", _set(["protocol", "sha256"], "z" * 64), "64-character SHA-256"),
    ("protocol sha mismatch", _set(["protocol", "sha256"], "0" * 64), "protocol.sha256 must equal"),
    ("artifact sha mismatch", _set(["artifacts", 1, "sha256"], "f" * 64), "SHA-256 mismatch"),
    ("artifact absolute path", _set(["artifacts", 1, "path"], "/etc/hostname"), "safe relative path"),
    ("artifact traversal", _set(["artifacts", 1, "path"], "../result.csv"), "safe relative path"),
    ("artifact dot-dot inside path", _set(["artifacts", 1, "path"], "sub/../result.csv"), "safe relative path"),
    ("artifact backslash path", _set(["artifacts", 1, "path"], "sub\\result.csv"), "forward-slash"),
    ("artifact missing file", _set(["artifacts", 1, "path"], "missing.csv"), "does not point to a readable file"),
    ("artifact symlink outside", _symlink_outside, "resolves outside the manifest directory"),
    ("duplicate artifact", _duplicate_artifact, "listed more than once"),
    ("two protocol artifacts", _two_protocols, "exactly one artifact must have role 'protocol'"),
]

SCRIPT = "<script>alert(1)</script>"


class FailClosedTests(unittest.TestCase):
    setUp = EvidencePassportTests.setUp
    tearDown = EvidencePassportTests.tearDown
    write_manifest = EvidencePassportTests.write_manifest

    def _build(self, data: dict[str, Any]) -> tuple[int, str, str, Path]:
        self.manifest_path.write_text(json.dumps(data), encoding="utf-8")
        out_dir = self.root / "reports"
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = ep.main(["build", str(self.manifest_path), "--out-dir", str(out_dir)])
        return code, stdout.getvalue(), stderr.getvalue(), out_dir

    def test_rejected_cases_fail_closed(self) -> None:
        for name, mutate, fragment in REJECTED:
            with self.subTest(case=name):
                data = copy.deepcopy(self.manifest)
                mutate(data, self.root)
                self.manifest_path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ep.ManifestError) as caught:
                    ep.load_and_validate(self.manifest_path)
                self.assertIn(fragment, str(caught.exception))
                code, _out, err, out_dir = self._build(data)
                self.assertEqual(code, 2)
                self.assertTrue(err.startswith("ERROR: "))
                self.assertFalse(out_dir.exists() and any(out_dir.iterdir()), "no report may be written")

    def test_malformed_json_is_rejected(self) -> None:
        self.manifest_path.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(ep.ManifestError, "cannot read JSON"):
            ep.load_and_validate(self.manifest_path)

    def test_non_finite_json_tokens_are_rejected(self) -> None:
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token):
                text = json.dumps(self.manifest).replace('"value": 0.8', f'"value": {token}')
                self.manifest_path.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(ep.ManifestError, "non-finite JSON number"):
                    ep.load_and_validate(self.manifest_path)

    def test_overflowing_number_is_rejected(self) -> None:
        text = json.dumps(self.manifest).replace('"value": 0.8', '"value": 1e309')
        self.manifest_path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(ep.ManifestError, "must be finite"):
            ep.load_and_validate(self.manifest_path)

    def test_non_object_manifest_is_rejected(self) -> None:
        self.manifest_path.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(ep.ManifestError, "manifest must be an object"):
            ep.load_and_validate(self.manifest_path)

    def test_uppercase_digest_is_accepted_and_normalised(self) -> None:
        data = copy.deepcopy(self.manifest)
        data["artifacts"][1]["sha256"] = data["artifacts"][1]["sha256"].upper()
        data["protocol"]["sha256"] = data["protocol"]["sha256"].upper()
        data["artifacts"][0]["sha256"] = data["artifacts"][0]["sha256"].upper()
        self.manifest_path.write_text(json.dumps(data), encoding="utf-8")
        report = ep.load_and_validate(self.manifest_path)
        self.assertEqual(report["protocol"]["sha256"], report["protocol"]["sha256"].lower())
        self.assertTrue(all(f["expected_sha256"].islower() for f in report["integrity"]["files"]))

    def test_leading_dot_segment_is_normalised_not_rejected(self) -> None:
        data = copy.deepcopy(self.manifest)
        data["artifacts"][1]["path"] = "./result.csv"
        self.manifest_path.write_text(json.dumps(data), encoding="utf-8")
        report = ep.load_and_validate(self.manifest_path)
        self.assertEqual(report["integrity"]["files"][1]["path"], "result.csv")

    def test_symlink_inside_manifest_directory_is_accepted(self) -> None:
        os.symlink(self.results_path, self.root / "inside-link.csv")
        data = copy.deepcopy(self.manifest)
        data["artifacts"][1]["path"] = "inside-link.csv"
        self.manifest_path.write_text(json.dumps(data), encoding="utf-8")
        report = ep.load_and_validate(self.manifest_path)
        self.assertEqual(report["integrity"]["files"][1]["path"], "inside-link.csv")

    def test_html_escapes_every_free_text_field(self) -> None:
        data = copy.deepcopy(self.manifest)
        data["project"]["name"] = SCRIPT
        data["project"]["source_note"] = SCRIPT
        data["project"]["source_url"] = 'https://example.invalid/"><script>alert(1)</script>'
        data["dataset"]["description"] = SCRIPT
        data["interpretation"] = SCRIPT
        data["limitations"] = [SCRIPT]
        data["results"][0]["scope"] = SCRIPT
        data["results"][0]["method"] = SCRIPT
        data["results"][0]["metrics"][0]["name"] = SCRIPT
        data["results"][0]["metrics"][0]["note"] = SCRIPT
        data["artifacts"][1]["description"] = SCRIPT
        code, _out, _err, out_dir = self._build(data)
        self.assertEqual(code, 0)
        page = (out_dir / "test-run-1.html").read_text(encoding="utf-8")
        self.assertNotIn("<script", page.lower())
        self.assertIn("https://example.invalid/&quot;&gt;&lt;script&gt;", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)

    def test_no_warning_for_ordinary_labels(self) -> None:
        report = ep.load_and_validate(self.manifest_path)
        self.assertNotIn("warnings", report)
        self.assertNotIn("WARNING", ep.render_html(report))


class SyntheticCriterionMetWarningTests(unittest.TestCase):
    setUp = EvidencePassportTests.setUp
    tearDown = EvidencePassportTests.tearDown
    write_manifest = EvidencePassportTests.write_manifest

    def _run(self, command: str) -> tuple[int, str, str]:
        self.manifest["evidence_class"] = "synthetic"
        self.manifest["result_label"] = "criterion_met"
        self.write_manifest()
        argv = [command, str(self.manifest_path)]
        if command == "build":
            argv += ["--out-dir", str(self.root / "reports")]
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = ep.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_validate_prints_warning_but_succeeds(self) -> None:
        code, out, err = self._run("validate")
        self.assertEqual(code, 0)
        self.assertIn("VALID:", out)
        self.assertIn("WARNING:", err)
        self.assertIn("synthetic inputs only", err)

    def test_build_writes_warning_into_html_and_json(self) -> None:
        code, _out, err = self._run("build")
        self.assertEqual(code, 0)
        self.assertIn("WARNING:", err)
        page = (self.root / "reports" / "test-run-1.html").read_text(encoding="utf-8")
        self.assertIn('role="alert"><strong>WARNING</strong>', page)
        self.assertIn("synthetic inputs only", page)
        normalized = json.loads((self.root / "reports" / "test-run-1.normalized.json").read_text(encoding="utf-8"))
        self.assertEqual(normalized["warnings"], [ep.SYNTHETIC_CRITERION_MET_WARNING])

    def test_public_dataset_criterion_met_has_no_warning(self) -> None:
        self.manifest["result_label"] = "criterion_met"
        self.write_manifest()
        self.assertNotIn("warnings", ep.load_and_validate(self.manifest_path))


if __name__ == "__main__":
    unittest.main()
