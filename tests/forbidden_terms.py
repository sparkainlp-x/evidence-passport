#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail if a banned overclaim term appears in repository text files.

Allowed phrases cover honest negative reporting (criterion not met), project
names that contain the word quantum (exact classical simulation, not a QPU),
and explicit medical/hardware non-claims. LICENSE and this file are excluded.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXCLUDE = {"LICENSE", "tests/forbidden_terms.py"}
APOS = "['’]"

ALLOWED = [
    # Honest negative SMAP/MSL reporting (criterion failed; EWMA-only contrast)
    r"significantly better than EWMA on SMAP only",
    r"better than EWMA on SMAP only",
    r"criterion was not met",
    r"criterion is not met",
    r"did not meet (?:its |the )?(?:pre-?stated |preregistered )?success criterion",
    r"success criterion was not met",
    r"no NASA[- ]beat claim",
    r"not an? (?:operational-performance|NASA) claim",
    # Project / path names and isolated toy-lab field (classical simulation; not a QPU)
    r"[Mm]ulti-[Qq]uantum OES",
    r"multi-quantum-oes",
    r"quantum_lab_path",
    # Sibling audit tool (classifies claims; makes none)
    r"quantum-claims-passport",
    r"Quantum Claims Evidence Passport",
    r"isolated toy simulation",
    r"exact classical simulation, not a QPU",
    r"not a QPU",
    # Explicit non-claims (medical / hardware / funding)
    r"no (?:operational, )?safety, hardware, medical",
    r"not a medical(?: device)?",
    r"medical device",  # only appears inside non-claim sentences we allow above / below
    r"blocks NASA-beat / clinical-claim / sponsorship overclaims",
    r"not (?:a )?hardware",
    r"pas un produit certifi[ée]",
    r"not a certified product",
    r"not a grant",
    r"pas une subvention",
]

BANNED = [
    r"quantique",
    r"quantum",
    r"\bQEC\b",
    r"conscien",
    r"gravit[ée]",
    r"gravity",
    r"m[ée]dic",
    r"\bsoins?\b",
    r"health ?care",
    r"fondation",
    r"foundation",
    r"ch[eè]que",
    r"\bcheck payable",
    r"subvention",
    r"\bgrant\b",
    r"\bbourse",
    r"financement",
    r"funding",
    r"produit certifi",
    r"certified product",
    # Ban NASA-beat / criterion-met overclaims
    r"criterion was met",
    r"criterion is met",
    r"(?:successfully )?(?:beat|outperform(?:ed)?|surpass(?:ed)?) (?:all )?(?:the )?(?:NASA|SMAP|MSL)",
    r"(bat|battu|surpass|d[ée]pass|beat|outperform|meilleur que|better than|sup[ée]rieur).{0,60}(NASA|SMAP|MSL)",
    r"(NASA|SMAP|MSL).{0,60}(battu|surpass|beaten|outperformed)",
]

allowed_re = [re.compile(p, re.I) for p in ALLOWED]
banned_re = [re.compile(p, re.I) for p in BANNED]

proc = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
files = proc.stdout.splitlines() if proc.returncode == 0 else []
if not files:  # not yet committed: scan the working tree
    files = [
        str(p.relative_to(ROOT))
        for p in ROOT.rglob("*")
        if p.is_file() and ".git" not in p.parts
    ]
hits = 0
for rel in sorted(files):
    if rel in EXCLUDE:
        continue
    p = ROOT / rel
    try:
        text = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        continue
    for n, line in enumerate(text.splitlines(), 1):
        cleaned = line
        for a in allowed_re:
            cleaned = a.sub(" ", cleaned)
        for b in banned_re:
            m = b.search(cleaned)
            if m:
                hits += 1
                print(f"{rel}:{n}: banned pattern {b.pattern!r} -> {m.group(0)!r}")
print(f"forbidden-terms scan: {hits} hit(s) in {len(files)} tracked file(s)")
sys.exit(1 if hits else 0)
