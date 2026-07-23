"""Offline re-scoring of results files under an alternative extraction policy.

Results records are self contained: they carry the raw response (and its
canonical form for obfuscated runs), so any extraction policy can be
evaluated after the fact without calling any model again.

Strict format compliance remains the primary, headline metric; a lenient
re-score is reported alongside it, never instead of it. The point is to
separate two questions the strict numbers conflate when a model wraps
correct JSON in prose: can it follow the format, and can it plan.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .extraction import extract_first_json_object
from .instructions import load_seeds
from .loader import load_environment
from .metrics import render_report
from .runner import check_seed, load_records

POLICIES = ("strict", "lenient")


def rescore_records(records: list[dict], seeds, environments, policy: str = "lenient") -> list[dict]:
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES}, got {policy!r}")
    seeds_by_id = {s.id: s for s in seeds}
    rescored = []
    for record in records:
        seed = seeds_by_id[record["seed_id"]]
        env = environments[record["environment"]]
        text = record.get("response_canonical") or record["response"]
        if policy == "lenient":
            extracted = extract_first_json_object(text)
            text = extracted if extracted is not None else text
        new = dict(record)
        new.update(check_seed(env, seed, text))
        new["extraction_policy"] = policy
        rescored.append(new)
    return rescored


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-score a results file under an extraction policy.")
    parser.add_argument("results", help="path to a results .jsonl file")
    parser.add_argument("--policy", default="lenient", choices=POLICIES)
    parser.add_argument("--seeds", default="instructions/seeds_house_01.json")
    parser.add_argument("--environments-dir", default="environments")
    parser.add_argument("--out", default=None, help="optionally write the re-scored records here")
    args = parser.parse_args()

    records = load_records(args.results)
    seeds = load_seeds(args.seeds)
    environments = {
        name: load_environment(Path(args.environments_dir) / f"{name}.json")
        for name in sorted({r["environment"] for r in records})
    }
    rescored = rescore_records(records, seeds, environments, args.policy)

    strict_malformed = sum(1 for r in records if r["verdict"] == "malformed")
    still_malformed = sum(1 for r in rescored if r["verdict"] == "malformed")
    print(f"policy: {args.policy}   source: {args.results}")
    print(
        f"strict malformed: {strict_malformed}/{len(records)}   "
        f"malformed under {args.policy}: {still_malformed}/{len(rescored)}"
    )
    print()
    print(render_report(rescored))

    if args.out is not None:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            for r in rescored:
                f.write(json.dumps(r) + "\n")
        print(f"wrote {len(rescored)} re-scored records to {out}")


if __name__ == "__main__":
    main()
