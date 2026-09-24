"""List committed responses that were cut off by the output token limit.

Records written before September 2026 do not store the provider's finish
reason, so truncation has to be recognised from the text. A response
counts as cut off when it is longer than 2000 characters and does not end
the way a finished answer ends: a closing brace, a closing code fence, or
sentence punctuation. The length floor keeps out short responses that end
in stray characters, which are malformed for other reasons. Every match is
printed with its ending so the rule can be checked by eye.

Run from the repository root:

    python tools/audit_truncation.py
"""

import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())

from plan_failure_bench.instructions import load_seeds
from plan_failure_bench.loader import load_environment
from plan_failure_bench.rescore import rescore_records

MIN_CHARS = 2000
FINISHED_ENDINGS = ("}", "```", ".", "!", "?")

environments = {name: load_environment(f"environments/{name}.json") for name in ("house_01", "office_01")}
seeds = {name: load_seeds(f"instructions/seeds_{name}.json") for name in environments}

total = 0
cut = []
for path in sorted(glob.glob("results/*.jsonl")):
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        total += 1
        text = (record["response"] or "").rstrip()
        if len(text) > MIN_CHARS and not text.endswith(FINISHED_ENDINGS):
            (lenient,) = rescore_records([record], seeds[record["environment"]], environments, "lenient")
            cut.append((os.path.basename(path), record, text, lenient["verdict"]))

for run, record, text, lenient in cut:
    print(f"{run}  seed {record['seed_id']}  {len(text)} chars  strict {record['verdict']}  lenient {lenient}")
    print(f"    ends: {text[-50:]!r}")
print(f"\n{len(cut)} of {total} committed responses were cut off at the output limit")
