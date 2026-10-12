"""Check that manifest.schema.json and the validator in evidence_passport.py agree.

Uses only the standard library: walks every object in the schema, then checks
that the code rejects a missing required field and an unknown extra field at
the same place, and that enums and patterns match the code's constants.
"""
from __future__ import annotations

import copy
import json
import re
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import evidence_passport as ep  # noqa: E402
from test_evidence_passport import EvidencePassportTests  # noqa: E402

SCHEMA = json.loads((ROOT / "manifest.schema.json").read_text(encoding="utf-8"))


def _objects(node: Any, path: tuple[Any, ...] = ()) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
    """Return (instance path, schema node) for every object in the schema tree."""
    found: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    if node.get("type") == "object" or "properties" in node:
        found.append((path, node))
        for key, child in node.get("properties", {}).items():
            found.extend(_objects(child, path + (key,)))
    if node.get("type") == "array" and isinstance(node.get("items"), dict):
        found.extend(_objects(node["items"], path + (0,)))
    return found


class SchemaConsistencyTests(unittest.TestCase):
    setUp = EvidencePassportTests.setUp
    tearDown = EvidencePassportTests.tearDown
    write_manifest = EvidencePassportTests.write_manifest

    def _rejects(self, data: dict[str, Any]) -> bool:
        self.manifest_path.write_text(json.dumps(data), encoding="utf-8")
        try:
            ep.load_and_validate(self.manifest_path)
        except ep.ManifestError:
            return True
        return False

    @staticmethod
    def _at(data: Any, path: tuple[Any, ...]) -> Any:
        for key in path:
            data = data[key]
        return data

    def test_schema_covers_expected_objects(self) -> None:
        paths = {p for p, _ in _objects(SCHEMA)}
        for expected in [(), ("project",), ("dataset",), ("code",), ("protocol",),
                         ("results", 0), ("results", 0, "metrics", 0), ("artifacts", 0)]:
            self.assertIn(expected, paths)

    def test_required_fields_match(self) -> None:
        for path, node in _objects(SCHEMA):
            for field in node.get("required", []):
                with self.subTest(path=path, field=field):
                    data = copy.deepcopy(self.manifest)
                    del self._at(data, path)[field]
                    self.assertTrue(self._rejects(data), "schema requires it; code must too")

    def test_optional_fields_are_optional_in_code(self) -> None:
        for path, node in _objects(SCHEMA):
            optional = set(node.get("properties", {})) - set(node.get("required", []))
            for field in optional:
                with self.subTest(path=path, field=field):
                    data = copy.deepcopy(self.manifest)
                    self._at(data, path).pop(field, None)
                    self.assertFalse(self._rejects(data))

    def test_additional_properties_match(self) -> None:
        for path, node in _objects(SCHEMA):
            with self.subTest(path=path):
                self.assertIs(node.get("additionalProperties"), False, "schema should be closed")
                data = copy.deepcopy(self.manifest)
                self._at(data, path)["zz_unknown"] = 1
                self.assertTrue(self._rejects(data))

    def test_enums_match_code_constants(self) -> None:
        props = SCHEMA["properties"]
        self.assertEqual(set(props["evidence_class"]["enum"]), ep.EVIDENCE_CLASSES)
        self.assertEqual(set(props["result_label"]["enum"]), ep.RESULT_LABELS)

    def test_patterns_match_code_constants(self) -> None:
        self.assertEqual(SCHEMA["properties"]["run_id"]["pattern"], ep.RUN_ID.pattern)
        self.assertEqual(SCHEMA["$defs"]["sha256"]["pattern"], ep.HEX_256.pattern)

    def test_schema_version_matches(self) -> None:
        node = SCHEMA["properties"]["schema_version"]
        self.assertEqual(node.get("const", node.get("enum", [None])[0]), ep.MANIFEST_SCHEMA_VERSION)

    def test_path_pattern_rejects_what_code_rejects(self) -> None:
        pattern = re.compile(SCHEMA["properties"]["artifacts"]["items"]["properties"]["path"]["pattern"])
        for bad in ["/etc/hostname", "../x", "a/../x", "a\\b"]:
            with self.subTest(path=bad):
                self.assertIsNone(pattern.search(bad))
        self.assertIsNotNone(pattern.search("result.csv"))


if __name__ == "__main__":
    unittest.main()
