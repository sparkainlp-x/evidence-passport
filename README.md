# Evidence Passport — offline MVP

[![CI](https://github.com/sparkainlp-x/evidence-passport/actions/workflows/ci.yml/badge.svg)](https://github.com/sparkainlp-x/evidence-passport/actions/workflows/ci.yml)
[![License: AGPL-3.0-only](https://img.shields.io/badge/License-AGPL--3.0--only-blue.svg)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23165143.svg)](https://doi.org/10.5281/zenodo.23165143)
[![Evidence: honest labels](https://img.shields.io/badge/evidence-criterion%20not%20met%20%7C%20SYNTHETIC-blue.svg)](#bundled-examples)


Evidence Passport turns one saved experiment-run manifest into a readable, static HTML record and a normalized JSON copy. It records declared project, dataset, code, protocol, seed, baseline, metric, limitation, and artifact details. It **does not generate data, score signals, or combine metrics**. Each report represents one manifest; different projects and dataset scopes stay separate.

The tool uses only Python’s standard library. It makes no network calls and starts no server. The bundled HTML has inline styling and no external assets or scripts.

## Run it

From this folder, using Python 3.10 or newer:

```bash
python3 evidence_passport.py validate examples/oes-resilience-smap-msl-public-v0.5.json
python3 evidence_passport.py build examples/oes-resilience-smap-msl-public-v0.5.json --out-dir reports
python3 -m unittest discover -s tests -v
```

`build` writes `<run_id>.html` and `<run_id>.normalized.json` into the chosen directory. To inspect all examples, repeat `validate` and `build` with each JSON manifest in `examples/`. No package installation is required.

## What the hashes do—and do not—show

The CLI computes SHA-256 for every local file named in a manifest and fails if one byte differs from its recorded digest. The HTML report and normalized JSON list the computed digests.

**A matching hash shows only that a referenced file is byte-for-byte consistent with the digest recorded in this bundle. It does not prove who created a file, when a protocol existed, where an artifact came from, whether its provenance is authentic, or whether a measurement or method is valid.** A copied source URL, a declared commit, or a self-reported lock time is descriptive metadata, not independent verification.

Paths are relative to the manifest and must resolve inside its directory. Manifests use schema version `1`; see [manifest.schema.json](manifest.schema.json) and the sample files.

## Bundled examples

- **OES-Resilience 0.5 / NASA SMAP and MSL:** [public-dataset example manifest](examples/oes-resilience-smap-msl-public-v0.5.json). The bundle includes the upstream protocol, results JSON, summary and comparison CSVs, run metadata, and upstream checksum list from the [public project report](https://github.com/sparkainlp-x/oes-resilience/tree/main/reports/smap_msl_results). The saved run metadata reports package version `0.4.0`; the public project describes the evaluation as v0.5.0. Its run metadata does not record an evaluated-code commit; the protocol lock commit is reported separately. The sample preserves the project's stated conclusion: **the preregistered success criterion was not met**. OES32 was significantly better than EWMA on SMAP only; it did not significantly differ from the other baselines. `maxabs` had a numerically higher pooled event F1 on both datasets, and CUSUM on MSL, but those differences were not significant. This is a bounded public-dataset result, not an operational-performance claim. No raw spacecraft data is included.
- **Multi-Quantum OES:** [synthetic example manifest](examples/multi-quantum-oes-synthetic-example.json), based on the saved synthetic replay report and example preregistration. Its inputs were generated locally by that project; the report says the saved replay had 80 frames and seed `20261002`.
- **Digital-to-Wave Testbench:** [synthetic example manifest](examples/digital-to-wave-v5-synthetic-example.json), based on the saved v5 timing-stress output, protocol note, and source file. The selected condition is an arbitrary software timing offset, not a physical or device measurement; the source states that the protocol was exploratory, not a formal preregistration.
- **Signal Test Commons:** [synthetic example manifest](examples/signal-test-commons-synthetic-example.json), based on its saved 80-frame, seed-7 challenge report and project README. Its source explicitly says synthetic results do not establish performance on physical instruments.

The three synthetic examples are labeled `synthetic` in their manifests and carry a visible synthetic-example banner in their reports. These numbers must not be read as results on public datasets. The OES SMAP and MSL scopes remain separate, and Evidence Passport does not pool their metrics.

These examples are evidence summaries only. The example manifests select and label values already present in saved files; the program does not rerun their experiments. No compatible public sample output was identified for the three synthetic examples in this local source bundle, so they are not presented as public-dataset results.

## Manifest fields

Each v1 manifest identifies one `run_id`; `project`, `dataset`, `code`, `protocol`, and `evidence_class`; an optional non-negative seed; baseline names; a list of results grouped by an explicit scope and method; an outcome label, plain-language interpretation and limitations; and a list of local artifacts with paths, roles, descriptions, and SHA-256 digests. One artifact must have the `protocol` role, and `protocol.sha256` must match it. Each metric has a name, numeric or null value, unit, and optional 95% interval and note. A null value requires a note explaining why it is not reported.

Supported evidence classes are `public_dataset` and `synthetic`. Result labels include `criterion_met`, `criterion_not_met`, `descriptive_only`, `synthetic_example`, and `not_stated`. The tool never infers a result label from the metric values.

## Boundaries

This is a local metadata-and-reporting MVP, not a validation authority, experiment runner, signal evaluator, data store, or provenance service. It makes no claims about safety, operations, device performance, authorship, or measurement validity. The native output formats differ; the bundled manifests are transparent, hand-mapped examples rather than automatic upstream adapters.

## Related tools

- [**quantum-claims-passport**](https://github.com/sparkainlp-x/quantum-claims-passport) ([report](https://sparkainlp-x.github.io/quantum-claims-passport/report.html)): a sibling, offline claims audit. Evidence Passport records *one run's declared evidence*; the Quantum Claims Evidence Passport classifies *public claims against their cited sources* (announcement/plan, computational model, animal behavioral result, hypothesis, unsupported inference) without combining them into a score. No DOI yet.

## License

GNU Affero General Public License v3.0 only (AGPL-3.0-only). See [LICENSE](LICENSE). Commercial licensing: [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md).

## Cite

See [CITATION.cff](CITATION.cff). Concept DOI (all versions): [10.5281/zenodo.23165143](https://doi.org/10.5281/zenodo.23165143). Version DOI for v0.1.0: [10.5281/zenodo.23165144](https://doi.org/10.5281/zenodo.23165144).

## Security

See [SECURITY.md](SECURITY.md).
