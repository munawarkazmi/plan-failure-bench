"""Re-derive the trap/feasible/valid partition from the committed seeds.

The results tables quote detection out of 13 traps against false
positives out of 17 feasible seeds, with 9 valid seeds inside the 17.
Those denominators are not authored anywhere; they follow from the
committed seed files: a seed is a detection trap exactly when its
expected answer is a terminal (infeasible or clarify), and feasible
otherwise. This script prints that derivation per suite so a reader can
check the partition against instructions/seeds_*.json without trusting
any prose.
"""

import os
import sys
from collections import Counter

sys.path.insert(0, os.getcwd())

from plan_failure_bench.instructions import load_seeds

SUITES = {
    "house_01": "instructions/seeds_house_01.json",
    "office_01": "instructions/seeds_office_01.json",
}

for suite, path in SUITES.items():
    seeds = load_seeds(path)
    traps = [s for s in seeds if s.expected_terminal is not None]
    feasible = [s for s in seeds if s.expected_terminal is None]
    trap_families = Counter(s.label for s in traps)
    feasible_families = Counter(s.label for s in feasible)
    print(f"{suite}  ({path}, {len(seeds)} seeds)")
    print(
        f"  detection traps (expected answer is a terminal): {len(traps)}  "
        f"[{', '.join(f'{k} {v}' for k, v in sorted(trap_families.items()))}]"
    )
    print(
        f"  feasible seeds (expected answer is a plan): {len(feasible)}  "
        f"[{', '.join(f'{k} {v}' for k, v in sorted(feasible_families.items()))}]"
    )
    print(f"  valid-labelled seeds inside the feasible set: {feasible_families.get('valid', 0)}")
    print()
