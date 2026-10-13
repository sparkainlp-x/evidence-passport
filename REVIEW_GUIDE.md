# Review guide

A short path for reviewers. Every command below runs offline with Python 3.10+ and the standard library only.

## 1. What this is

Evidence Passport records **declared** evidence. It checks that a run manifest is well formed and that the local files it lists match their SHA-256 digests, then renders static HTML and normalized JSON. It does not run experiments, re-score metrics, rank methods, or decide whether a result is valid.

## 2. Two-minute check

```bash
python3 -m unittest discover -s tests -v
for m in examples/*.json; do python3 evidence_passport.py validate "$m"; done
for m in examples/*.json; do python3 evidence_passport.py build "$m" --out-dir /tmp/ep; done
cmp /tmp/ep/oes-resilience-smap-msl-public-v0.5.html docs/oes-resilience-smap-msl-v0.5.html
for f in multi-quantum-oes digital-to-wave-v5 signal-test-commons; do
  cmp "/tmp/ep/$f-synthetic-example.html" "docs/$f-synthetic-example.html"
done
```

Expected: all tests pass, every example prints `VALID:`, and every `cmp` prints nothing (the rebuilt pages are byte-identical to `docs/`).

## 3. Fail-closed contract

A rejected manifest makes the CLI exit with code 2, print `ERROR: ...` on stderr, and write no report.

| Input | Covered by |
|---|---|
| Malformed JSON, top level not an object, duplicate keys | `test_fail_closed.py` (`test_malformed_json_is_rejected`, `test_non_object_manifest_is_rejected`), `test_evidence_passport.py` |
| Missing required field, unknown field (top level and nested) | `test_fail_closed.py` `REJECTED`; `test_schema_consistency.py` |
| Wrong types: string/bool seed, string/bool metric value, string `schema_version` | `REJECTED` |
| `NaN`, `Infinity`, numbers that overflow to infinity | `test_non_finite_json_tokens_are_rejected`, `test_overflowing_number_is_rejected` |
| Empty strings, empty `results` or `artifacts`, reversed or short 95% interval, null value without a note, duplicate metric | `REJECTED` |
| Unknown `evidence_class` or `result_label`; `run_id` with separators or over 101 characters | `REJECTED` |
| Non-HTTP(S) source URLs (for example `javascript:`) | `REJECTED` |
| Bad or mismatched digests (artifact or protocol) | `REJECTED` |
| Absolute paths, `..` segments, backslashes, missing files, symlinks resolving outside the manifest folder, duplicate artifacts, two protocol artifacts | `REJECTED` |

Accepted on purpose: upper-case hex digests (normalised to lower case), a leading `./` (normalised away) and symlinks that stay inside the manifest folder.

## 4. HTML safety

Every manifest string is passed through `html.escape` before it reaches the page; `test_html_escapes_every_free_text_field` injects `<script>` into each free-text field and checks that none survives. Source URLs are shown as escaped text, not links. The page loads no scripts, fonts, images or network resources.

## 5. What a matching hash shows

Only that each listed file is byte-for-byte the file the manifest describes. It does not show authorship, when a file or protocol existed, provenance, or that a measurement or method is valid.

## 6. Label rules

| `evidence_class` | `result_label` | Behaviour |
|---|---|---|
| `public_dataset` | `synthetic_example` | Rejected |
| `synthetic` | `criterion_met` | Accepted with a visible WARNING (stderr, HTML box, `warnings` in JSON) |
| any other pair | any allowed label | Accepted as declared |

The tool never infers a label from metric values.

## 7. Adding a manifest safely

1. Put the manifest and its artifacts in one folder; use relative forward-slash paths.
2. Record each artifact's digest with `sha256sum`; mark exactly one artifact `protocol` and copy its digest into `protocol.sha256`.
3. Use the label that the source project states; use `not_stated` if it states none.
4. Run `validate`, then `build`, and read the page before sharing it.
