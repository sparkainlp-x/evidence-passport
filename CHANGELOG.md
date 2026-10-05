# Changelog

All notable changes to this project. Bundled public-dataset example preserves the upstream finding that the SMAP/MSL success criterion was **not** met. Synthetic examples are labelled SYNTHETIC.

## Unreleased

## 0.1.0 — 2026-10-05

### Added
- `evidence_passport.py`: offline stdlib CLI (`validate`, `build`) that turns one experiment-run manifest into a static HTML evidence passport and normalized JSON.
- Manifest schema v1 (`manifest.schema.json`) with evidence classes `public_dataset` and `synthetic`, result labels including `criterion_not_met` and `synthetic_example`, and fail-closed SHA-256 checks.
- Bundled examples: OES-Resilience SMAP/MSL public-dataset passport (criterion **not** met) plus three SYNTHETIC examples (Multi-Quantum OES, Digital-to-Wave, Signal Test Commons).
- Unit tests and a forbidden-terms CI scan that blocks NASA-beat / clinical-claim / sponsorship overclaims while allowing honest negative reporting.
- `CITATION.cff`, `.zenodo.json`, AGPL-3.0-only `LICENSE`, `COMMERCIAL-LICENSE.md`, `SECURITY.md`.
- Zenodo deposit: concept DOI `10.5281/zenodo.23165143`, version DOI `10.5281/zenodo.23165144`.
