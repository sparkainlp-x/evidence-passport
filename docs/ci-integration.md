# GitHub Actions integration

This guide shows one way to run Evidence Passport as a CI check. The release gate evaluates a local manifest, local artifact files, and a policy file; it does not independently verify the experiment or authenticate the policy author.

## Prerequisites

- Python 3.10 or newer.
- The manifest and every referenced artifact are available in the job workspace, with paths contained under the manifest directory.
- A project-owned policy file reviewed and version-controlled with the workflow.
- A reviewed Evidence Passport source revision. Pin the source checkout to a full commit SHA; do not execute an unreviewed moving branch in a release workflow.

## Example job

Replace `REPLACE_WITH_REVIEWED_40_HEX_COMMIT` with the full commit SHA reviewed by your team. Adjust the paths and Python version to match your repository. This workflow fails when validation or policy checks fail; it builds reports only after the gate passes.

```yaml
name: Evidence release gate

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  evidence-gate:
    runs-on: ubuntu-latest
    steps:
      - name: Check out project and evidence bundle
        uses: actions/checkout@v7

      - name: Check out reviewed Evidence Passport source
        uses: actions/checkout@v7
        with:
          repository: sparkainlp-x/evidence-passport
          ref: REPLACE_WITH_REVIEWED_40_HEX_COMMIT
          path: .tools/evidence-passport

      - name: Set up Python
        uses: actions/setup-python@v7
        with:
          python-version: "3.12"

      - name: Validate and apply release policy
        run: >-
          python .tools/evidence-passport/evidence_passport.py gate
          evaluation/manifest.json
          --policy .ci/evidence-policy.json

      - name: Build the reviewable passport
        run: >-
          python .tools/evidence-passport/evidence_passport.py build
          evaluation/manifest.json
          --out-dir build/evidence-passport
```

Keep policy and manifest changes in normal code review. Add an artifact-upload step only after reviewing the CI provider's access controls and retention; generated passports may reveal project, dataset, protocol, or result metadata.

## Exit behavior

- `0`: manifest and local artifact checks pass, and the policy accepts the declared evidence.
- `2`: invalid policy or manifest input (including local bundle-validation errors).
- `3`: the valid manifest does not satisfy the policy.

Any nonzero status fails the example job. Add a separate test job with deliberately invalid fixtures if you need to demonstrate that the configured policy rejects specific cases.

## Important boundaries

The gate checks declared data and local file consistency. A matching SHA-256 does not prove authorship, time of creation, source authenticity, or scientific correctness. A policy file is not a signed approval, and this integration does not add role-based approvals or tamper-evident logs. Configure branch protections, code-owner review, CI permissions, and artifact retention in your own environment as needed.
