#!/usr/bin/env python3
"""Offline evidence-passport manifest validation and report rendering.

This module reports declared metrics as supplied. It does not generate data,
score signals, connect to networks, or infer provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

TOOL_VERSION = "0.1.0"
MANIFEST_SCHEMA_VERSION = 1
NORMALIZED_SCHEMA = "evidence-passport/normalized-report/1"
DISCLAIMER = (
    "SHA-256 matching proves only byte-for-byte consistency between a referenced "
    "file and the digest recorded in this bundle. It does not prove authorship, "
    "when a file or protocol existed, provenance authenticity, or measurement or "
    "method validity."
)
EVIDENCE_CLASSES = {"public_dataset", "synthetic"}
RESULT_LABELS = {
    "criterion_met",
    "criterion_not_met",
    "descriptive_only",
    "synthetic_example",
    "not_stated",
}
HEX_256 = re.compile(r"^[0-9a-fA-F]{64}$")
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}$")


class ManifestError(ValueError):
    """Raised when a manifest or one of its referenced artifacts is invalid."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> None:
    raise ManifestError(f"non-finite JSON number is not allowed: {token}")


def read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(
                handle,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_nonfinite,
            )
    except ManifestError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read JSON at {path}: {exc}") from exc


def _object(value: Any, where: str, required: set[str], allowed: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{where} must be an object")
    missing = required - value.keys()
    if missing:
        raise ManifestError(f"{where} is missing required field(s): {', '.join(sorted(missing))}")
    if allowed is not None:
        extra = value.keys() - allowed
        if extra:
            raise ManifestError(f"{where} has unknown field(s): {', '.join(sorted(extra))}")
    return value


def _text(value: Any, where: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{where} must be a non-empty string" + (" or null" if nullable else ""))
    return value.strip()


def _finite_number(value: Any, where: str, *, nullable: bool = False) -> int | float | None:
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ManifestError(f"{where} must be a finite number" + (" or null" if nullable else ""))
    if not math.isfinite(float(value)):
        raise ManifestError(f"{where} must be finite")
    return value


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ManifestError(f"cannot read artifact {path}: {exc}") from exc
    return digest.hexdigest()


def _safe_artifact_path(base: Path, raw_path: str, where: str) -> tuple[Path, str]:
    if "\\" in raw_path:
        raise ManifestError(f"{where} must use portable forward-slash relative paths")
    relative = PurePosixPath(raw_path)
    if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ManifestError(f"{where} must be a safe relative path inside the manifest directory")
    base_resolved = base.resolve()
    candidate = (base / Path(*relative.parts)).resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise ManifestError(f"{where} resolves outside the manifest directory") from exc
    if not candidate.is_file():
        raise ManifestError(f"{where} does not point to a readable file: {raw_path}")
    return candidate, relative.as_posix()


def validate_manifest_data(data: Any, manifest_path: Path) -> dict[str, Any]:
    """Validate fields and local artifact bytes; return normalized report data."""
    root = _object(
        data,
        "manifest",
        {
            "schema_version", "run_id", "project", "evidence_class", "dataset",
            "code", "seed", "protocol", "baselines", "results", "result_label",
            "interpretation", "limitations", "artifacts",
        },
        {
            "schema_version", "run_id", "project", "evidence_class", "dataset",
            "code", "seed", "protocol", "baselines", "results", "result_label",
            "interpretation", "limitations", "artifacts",
        },
    )
    if type(root["schema_version"]) is not int or root["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise ManifestError(f"schema_version must be integer {MANIFEST_SCHEMA_VERSION}")
    run_id = _text(root["run_id"], "run_id")
    if not RUN_ID.fullmatch(run_id):
        raise ManifestError("run_id may contain only letters, digits, dot, underscore, and hyphen; max 101 characters")

    project = _object(root["project"], "project", {"name", "version", "source_url", "source_note"}, {"name", "version", "source_url", "source_note"})
    project_out = {
        "name": _text(project["name"], "project.name"),
        "version": _text(project["version"], "project.version"),
        "source_url": _text(project["source_url"], "project.source_url", nullable=True),
        "source_note": _text(project["source_note"], "project.source_note"),
    }
    if project_out["source_url"] and not project_out["source_url"].startswith(("https://", "http://")):
        raise ManifestError("project.source_url must be an HTTP(S) URL or null")

    evidence_class = _text(root["evidence_class"], "evidence_class")
    if evidence_class not in EVIDENCE_CLASSES:
        raise ManifestError("evidence_class must be 'public_dataset' or 'synthetic'")
    result_label = _text(root["result_label"], "result_label")
    if result_label not in RESULT_LABELS:
        raise ManifestError(f"result_label must be one of: {', '.join(sorted(RESULT_LABELS))}")
    if evidence_class == "public_dataset" and result_label == "synthetic_example":
        raise ManifestError("a public_dataset manifest cannot use result_label 'synthetic_example'")

    dataset = _object(root["dataset"], "dataset", {"name", "kind", "description", "source_url"}, {"name", "kind", "description", "source_url"})
    dataset_out = {
        "name": _text(dataset["name"], "dataset.name"),
        "kind": _text(dataset["kind"], "dataset.kind"),
        "description": _text(dataset["description"], "dataset.description"),
        "source_url": _text(dataset["source_url"], "dataset.source_url", nullable=True),
    }
    if dataset_out["source_url"] and not dataset_out["source_url"].startswith(("https://", "http://")):
        raise ManifestError("dataset.source_url must be an HTTP(S) URL or null")

    code = _object(root["code"], "code", {"version", "commit"}, {"version", "commit"})
    code_out = {
        "version": _text(code["version"], "code.version"),
        "commit": _text(code["commit"], "code.commit", nullable=True),
    }
    seed = root["seed"]
    if seed is not None and (type(seed) is not int or seed < 0):
        raise ManifestError("seed must be a non-negative integer or null")

    protocol = _object(
        root["protocol"], "protocol",
        {"name", "version", "sha256", "locked_at", "lock_commit", "description"},
        {"name", "version", "sha256", "locked_at", "lock_commit", "description"},
    )
    protocol_hash = _text(protocol["sha256"], "protocol.sha256")
    if not HEX_256.fullmatch(protocol_hash):
        raise ManifestError("protocol.sha256 must be a 64-character SHA-256 hex digest")
    protocol_out = {
        "name": _text(protocol["name"], "protocol.name"),
        "version": _text(protocol["version"], "protocol.version"),
        "sha256": protocol_hash.lower(),
        "locked_at": _text(protocol["locked_at"], "protocol.locked_at"),
        "lock_commit": _text(protocol["lock_commit"], "protocol.lock_commit", nullable=True),
        "description": _text(protocol["description"], "protocol.description"),
    }

    baselines = root["baselines"]
    if not isinstance(baselines, list) or any(not isinstance(item, str) or not item.strip() for item in baselines):
        raise ManifestError("baselines must be an array of non-empty strings")
    if len({item.strip() for item in baselines}) != len(baselines):
        raise ManifestError("baselines must not contain duplicates")

    results = root["results"]
    if not isinstance(results, list) or not results:
        raise ManifestError("results must be a non-empty array")
    result_out: list[dict[str, Any]] = []
    seen_metrics: set[tuple[str, str, str]] = set()
    for index, row_value in enumerate(results):
        where = f"results[{index}]"
        row = _object(row_value, where, {"scope", "method", "metrics"}, {"scope", "method", "metrics"})
        scope = _text(row["scope"], f"{where}.scope")
        method = _text(row["method"], f"{where}.method")
        metrics = row["metrics"]
        if not isinstance(metrics, list) or not metrics:
            raise ManifestError(f"{where}.metrics must be a non-empty array")
        metric_out: list[dict[str, Any]] = []
        for mindex, metric_value in enumerate(metrics):
            mwhere = f"{where}.metrics[{mindex}]"
            metric = _object(metric_value, mwhere, {"name", "value", "unit"}, {"name", "value", "unit", "note", "interval_95"})
            name = _text(metric["name"], f"{mwhere}.name")
            unit = _text(metric["unit"], f"{mwhere}.unit")
            value = _finite_number(metric["value"], f"{mwhere}.value", nullable=True)
            note = _text(metric["note"], f"{mwhere}.note") if "note" in metric else ""
            if value is None and not note:
                raise ManifestError(f"{mwhere} needs a note when value is null")
            interval = metric.get("interval_95")
            if interval is not None:
                if not isinstance(interval, list) or len(interval) != 2:
                    raise ManifestError(f"{mwhere}.interval_95 must be a two-number array")
                low = _finite_number(interval[0], f"{mwhere}.interval_95[0]")
                high = _finite_number(interval[1], f"{mwhere}.interval_95[1]")
                if float(low) > float(high):
                    raise ManifestError(f"{mwhere}.interval_95 lower bound exceeds upper bound")
                interval = [low, high]
            unique_key = (scope, method, name)
            if unique_key in seen_metrics:
                raise ManifestError(f"duplicate metric for scope/method/name: {scope} / {method} / {name}")
            seen_metrics.add(unique_key)
            metric_out.append({"name": name, "value": value, "unit": unit, "note": note, "interval_95": interval})
        result_out.append({"scope": scope, "method": method, "metrics": metric_out})

    for field in ("limitations",):
        if not isinstance(root[field], list) or any(not isinstance(item, str) or not item.strip() for item in root[field]):
            raise ManifestError(f"{field} must be an array of non-empty strings")
    interpretation = _text(root["interpretation"], "interpretation")

    artifacts = root["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise ManifestError("artifacts must be a non-empty array")
    base = manifest_path.parent
    artifact_out: list[dict[str, Any]] = []
    artifact_paths: set[str] = set()
    protocol_artifacts: list[dict[str, Any]] = []
    for index, artifact_value in enumerate(artifacts):
        where = f"artifacts[{index}]"
        artifact = _object(artifact_value, where, {"path", "role", "description", "sha256"}, {"path", "role", "description", "sha256"})
        raw_path = _text(artifact["path"], f"{where}.path")
        role = _text(artifact["role"], f"{where}.role")
        description = _text(artifact["description"], f"{where}.description")
        expected = _text(artifact["sha256"], f"{where}.sha256")
        if not HEX_256.fullmatch(expected):
            raise ManifestError(f"{where}.sha256 must be a 64-character SHA-256 hex digest")
        resolved_path, relative_path = _safe_artifact_path(base, raw_path, f"{where}.path")
        if relative_path in artifact_paths:
            raise ManifestError(f"artifact path is listed more than once: {relative_path}")
        artifact_paths.add(relative_path)
        actual = _hash_file(resolved_path)
        expected = expected.lower()
        if expected != actual:
            raise ManifestError(
                f"SHA-256 mismatch for {relative_path}: expected {expected}, computed {actual}"
            )
        verified = {"path": relative_path, "role": role, "description": description, "expected_sha256": expected, "computed_sha256": actual, "match": True}
        artifact_out.append(verified)
        if role == "protocol":
            protocol_artifacts.append(verified)
    if len(protocol_artifacts) != 1:
        raise ManifestError("exactly one artifact must have role 'protocol'")
    if protocol_artifacts[0]["computed_sha256"] != protocol_out["sha256"]:
        raise ManifestError("protocol.sha256 must equal the verified SHA-256 of the artifact with role 'protocol'")

    return {
        "schema": NORMALIZED_SCHEMA,
        "tool_version": TOOL_VERSION,
        "run_id": run_id,
        "project": project_out,
        "evidence_class": evidence_class,
        "dataset": dataset_out,
        "code": code_out,
        "seed": seed,
        "protocol": protocol_out,
        "baselines": [item.strip() for item in baselines],
        "results": result_out,
        "result_label": result_label,
        "interpretation": interpretation,
        "limitations": [item.strip() for item in root["limitations"]],
        "integrity": {
            "algorithm": "SHA-256",
            "bundle_consistent": all(item["match"] for item in artifact_out),
            "files": artifact_out,
            "meaning": DISCLAIMER,
        },
        "notice": DISCLAIMER,
    }


def load_and_validate(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.expanduser().resolve()
    data = read_json(manifest_path)
    return validate_manifest_data(data, manifest_path)


def _display_number(value: int | float | None) -> str:
    if value is None:
        return "Not reported"
    if isinstance(value, int):
        return str(value)
    return format(value, ".8g")


def render_html(report: dict[str, Any]) -> str:
    e = html.escape
    label = "PUBLIC-DATASET RESULT" if report["evidence_class"] == "public_dataset" else "SYNTHETIC EXAMPLE"
    label_class = "public" if report["evidence_class"] == "public_dataset" else "synthetic"
    project = report["project"]
    dataset = report["dataset"]
    code = report["code"]
    protocol = report["protocol"]
    source = project["source_url"] or "Not supplied"
    dataset_source = dataset["source_url"] or "Not supplied"
    seed = str(report["seed"]) if report["seed"] is not None else "Not recorded"
    commit = code["commit"] or "Not recorded"
    lock_commit = protocol["lock_commit"] or "Not recorded"
    baseline_text = ", ".join(report["baselines"]) if report["baselines"] else "None recorded"

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in report["results"]:
        groups.setdefault(row["scope"], []).append(row)
    tables: list[str] = []
    for scope, rows in groups.items():
        body: list[str] = []
        for row in rows:
            for metric in row["metrics"]:
                value = _display_number(metric["value"])
                interval = metric["interval_95"]
                interval_text = f"[{_display_number(interval[0])}, {_display_number(interval[1])}]" if interval else "—"
                note = f"<br><small>{e(metric['note'])}</small>" if metric["note"] else ""
                body.append(
                    "<tr>"
                    f"<td>{e(row['method'])}</td><td>{e(metric['name'])}</td>"
                    f"<td>{e(value)}</td><td>{e(metric['unit'])}</td>"
                    f"<td>{e(interval_text)}</td><td>{note or '—'}</td></tr>"
                )
        tables.append(
            f"<section><h3>{e(scope)}</h3><div class=\"table-wrap\"><table>"
            "<thead><tr><th>Method</th><th>Metric</th><th>Value</th><th>Unit</th>"
            "<th>95% interval</th><th>Note</th></tr></thead><tbody>"
            + "".join(body) + "</tbody></table></div></section>"
        )

    artifact_items = "".join(
        f"<li><code>{e(item['path'])}</code> — {e(item['role'])}; SHA-256 <code>{e(item['computed_sha256'])}</code></li>"
        for item in report["integrity"]["files"]
    )
    limitations = "".join(f"<li>{e(item)}</li>" for item in report["limitations"])
    result_word = report["result_label"].replace("_", " ")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Evidence Passport — {e(project['name'])}</title>
<style>
:root {{ color-scheme: light; --ink:#172b3a; --muted:#526675; --line:#d5dfe5; --paper:#fff; --wash:#f3f7f9; --blue:#154d70; --amber:#8a4b00; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--wash); color:var(--ink); font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:28px 18px 52px; }} h1 {{ margin:.2em 0; font-size:clamp(1.8rem,4vw,2.6rem); line-height:1.15; }} h2 {{ margin-top:1.8rem; border-bottom:1px solid var(--line); padding-bottom:.35rem; }} h3 {{ margin:1.2rem 0 .5rem; }}
.badge {{ display:inline-block; padding:.25rem .65rem; border-radius:999px; font-weight:750; letter-spacing:.04em; font-size:.8rem; }} .public {{ color:#0e3a58; background:#dceef8; }} .synthetic {{ color:#6b3900; background:#fff0d6; }}
.card {{ background:var(--paper); border:1px solid var(--line); border-radius:12px; padding:18px; margin:14px 0; }} .callout {{ border-left:5px solid var(--blue); }} .warning {{ border-left-color:var(--amber); }}
.meta {{ display:grid; grid-template-columns:minmax(130px,220px) 1fr; gap:.4rem 1rem; }} .meta dt {{ color:var(--muted); font-weight:650; }} .meta dd {{ margin:0; overflow-wrap:anywhere; }}
.table-wrap {{ overflow-x:auto; }} table {{ border-collapse:collapse; width:100%; min-width:680px; background:white; }} th,td {{ border:1px solid var(--line); text-align:left; padding:.55rem .65rem; vertical-align:top; }} th {{ background:#eaf1f5; }} code {{ overflow-wrap:anywhere; }} small {{ color:var(--muted); }} .footer {{ color:var(--muted); font-size:.9rem; margin-top:2rem; }}
@media(max-width:600px) {{ main {{ padding:18px 12px 36px; }} .meta {{ grid-template-columns:1fr; gap:.1rem; }} .meta dd {{ margin-bottom:.55rem; }} }}
</style>
</head>
<body><main>
<header><span class="badge {label_class}">{label}</span><h1>{e(project['name'])}</h1><p>{e(dataset['name'])} · {e(result_word)}</p></header>
<div class="card callout {'warning' if report['result_label'] == 'criterion_not_met' else ''}"><strong>Interpretation</strong><p>{e(report['interpretation'])}</p></div>
<section><h2>Run record</h2><div class="card"><dl class="meta">
<dt>Project version</dt><dd>{e(project['version'])}</dd><dt>Code version</dt><dd>{e(code['version'])}</dd><dt>Code commit</dt><dd>{e(commit)}</dd>
<dt>Evidence class</dt><dd>{e(report['evidence_class'])}</dd><dt>Dataset type</dt><dd>{e(dataset['kind'])}</dd><dt>Dataset notes</dt><dd>{e(dataset['description'])}</dd>
<dt>Seed</dt><dd>{e(seed)}</dd><dt>Baselines</dt><dd>{e(baseline_text)}</dd><dt>Protocol</dt><dd>{e(protocol['name'])} · {e(protocol['version'])}</dd>
<dt>Protocol lock claim</dt><dd>{e(protocol['locked_at'])} <small>(source-stated; not independently time-verified)</small></dd>
<dt>Protocol SHA-256</dt><dd><code>{e(protocol['sha256'])}</code></dd><dt>Protocol lock commit</dt><dd>{e(lock_commit)}</dd>
<dt>Project source</dt><dd>{e(source)}</dd><dt>Dataset source</dt><dd>{e(dataset_source)}</dd><dt>Source note</dt><dd>{e(project['source_note'])}</dd>
</dl></div></section>
<section><h2>Reported metrics</h2><p>Values are copied from the declared run summary. This report does not calculate scores, rank methods, or combine metrics across scopes.</p>{''.join(tables)}</section>
<section><h2>Limitations</h2><ul>{limitations}</ul></section>
<section><h2>Artifact integrity</h2><div class="card"><p><strong>All referenced files match their manifest SHA-256 values.</strong> This confirms bundle consistency only; it does not establish authorship, timing, provenance authenticity, or measurement validity.</p><ul>{artifact_items}</ul><p>{e(DISCLAIMER)}</p></div></section>
<p class="footer">Generated by Evidence Passport {e(report['tool_version'])}. This is a static file; it loads no scripts, fonts, images, or services from the network.</p>
</main></body></html>
"""


def _write_report(out_dir: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{report['run_id']}.normalized.json"
    html_path = out_dir / f"{report['run_id']}.html"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    return html_path, json_path


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate an offline Evidence Passport run manifest and render static HTML plus normalized JSON."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="validate a manifest and local artifact hashes")
    validate.add_argument("manifest", type=Path)
    build = sub.add_parser("build", help="validate and write an offline HTML/JSON report pair")
    build.add_argument("manifest", type=Path)
    build.add_argument("--out-dir", type=Path, default=Path("reports"), help="report output directory (default: ./reports)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        report = load_and_validate(args.manifest)
        if args.command == "validate":
            print(f"VALID: {report['run_id']} — {report['project']['name']} ({report['evidence_class']})")
            print(f"Verified {len(report['integrity']['files'])} local artifact(s); bundle is internally consistent.")
            print("This check does not establish authorship, timing, provenance authenticity, or measurement validity.")
            return 0
        html_path, json_path = _write_report(args.out_dir, report)
        print(f"HTML: {html_path}")
        print(f"JSON: {json_path}")
        return 0
    except ManifestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: file operation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
