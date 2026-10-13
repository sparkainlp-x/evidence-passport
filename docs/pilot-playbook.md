# First external pilot playbook (template)

**Status:** planning template only. This file does not describe a signed partner, a running pilot, customer evidence, or measured product results. Replace every bracketed field and freeze the protocol before collecting pilot results.

## Product hypothesis

- **Candidate:** Evidence Passport, as an offline evidence-packaging and release-gate tool.
- **Bounded promise:** given one experiment-run manifest, its local artifacts, and an explicit policy, validate the declared fields and local SHA-256 consistency, produce a static HTML/JSON record, and return a failing exit status when the configured requirements are not met.
- **Out of scope:** independently validating an experiment, authenticating an author, proving when a protocol existed, granting access, signing an attestation, approving a release, or maintaining an immutable log.
- **Initial buyer hypothesis (untested):** a small AI evaluation or research-software team that repeatedly prepares evidence for internal review or release. The economic buyer, budget owner, and current workflow displaced are **unknown until interviews**.

## Alternatives to compare

Record which option the partner uses today and compare the same task, data, and acceptance criteria. Do not present Evidence Passport as a replacement for enterprise governance platforms.

| Alternative | Baseline question |
| --- | --- |
| Do nothing / ad hoc review | What evidence is skipped, and how often does review need follow-up? |
| Manual checklist and file inspection | How long does preparation and reviewer verification take? |
| Existing internal scripts or CI checks | Which required fields, artifacts, and integrity conditions do they already check? |
| Existing AI evaluation / governance platform | Does the partner already get the required export, audit trail, and release gate there? |

## Preregister before the first scored run

- **Partner and sponsor:** [organization, named sponsor, permission to name publicly: yes/no]
- **Economic buyer and budget source:** [role, budget, or “not identified”]
- **Users and workflow:** [roles, task, current steps, frequency, current elapsed/reviewer time]
- **Data and rights:** [public, synthetic, or specifically authorized; owner; retention; access boundaries]
- **Frozen versions:** [Evidence Passport commit, manifest schema, policy file hash, CI configuration, environment]
- **Evaluation set:** [manifest/artifact cases, number of valid and malformed cases, how cases were selected]
- **Baselines:** [manual process, internal script, or existing platform and exact comparison procedure]
- **Primary outcome and threshold:** [one measurable buyer-relevant outcome and numeric acceptance threshold]
- **Secondary outcomes and thresholds:** [metrics and thresholds]
- **Failure conditions:** [conditions that stop the pilot or count as a failed acceptance test]
- **Analysis and publication:** [analysis owner, permitted aggregate results, review window, attribution/publication rights]
- **Change control:** [how deviations are logged; any changed test, threshold, policy, or code version requires a dated protocol amendment before rerunning]

Do not fill thresholds after seeing results. Report unmet thresholds and negative results as-is. Separate technical test results from user feedback and commercial evidence.

## Suggested measures

Agree on definitions, data collection, and pass thresholds before the pilot. These are candidate measures, **not existing results or promised targets**.

| Measure | Suggested definition | Preregistered threshold |
| --- | --- | --- |
| Setup time | Elapsed staff time from a clean checkout to the first successful gate run | [set with partner] |
| Required evidence checked | Required fields/artifact conditions automatically checked ÷ all required conditions in the frozen policy | [set with partner] |
| Reviewer time | Minutes required to prepare and review the same evidence bundle, manual baseline vs. tool-assisted | [set with partner] |
| Malformed-bundle false acceptance | Invalid cases accepted by the gate ÷ frozen invalid cases; enumerate path escapes, hash mismatch, missing roles, and disallowed labels | [set with partner; define critical cases before run] |
| CI reliability | Successful expected gate outcomes ÷ repeated runs on the frozen runner and inputs | [set with partner] |
| Human usability | User-reported effort and completion of the agreed evidence-review task | [instrument and threshold] |

## Safety, privacy, and scope checks

- Use only synthetic, public, or explicitly authorized data. Do not place secrets, personal information, confidential source documents, or credentials in manifests or artifacts unless the partner has approved a reviewed data-handling plan.
- The tool is local and makes no network calls, but the surrounding CI service, logs, caches, uploaded artifacts, and repository permissions have their own access and retention policies. Review them separately; do not assume offline validation makes the workflow private.
- The policy is caller-supplied configuration. It is not an authenticated approval or signature. Anyone able to change the manifest, policy, or workflow may change what gets checked unless repository permissions and review controls are configured separately.
- Stop and record the event if an unauthorized file is included, a security boundary is crossed, the frozen protocol is not followed, or a critical invalid case passes. Do not silently tune policy or thresholds to make a run pass.
- Before external use, agree on source access, document authorization, threat model, incident contact, retention/deletion, human escalation, and any independent security review that is required.

## Decision after the pilot

Record one of: **continue**, **revise and preregister a new pilot**, or **stop**. Include the measured results, deviations, unmet criteria, reviewer time, buyer feedback, and limitations. A positive technical result is not itself evidence of willingness to pay; record a paid pilot, procurement step, renewal, or other commercial evidence separately and only when it actually occurs.
