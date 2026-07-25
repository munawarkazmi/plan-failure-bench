"""Per-seed verdict consistency across k sampled runs.

The k-sampling protocol, agreed 2026-07-24: k independent decodes per
seed at temperature 0.7, each decode an ordinary run written to its own
results file, so every existing tool (rescore, metrics, figures) works
on each sample unchanged. This module aggregates the k files into one
report of how stable each seed's outcome is.

Design points, mirroring metrics.py:
- Counts, not percentages. Agreement is reported as "j of k", never as
  a rate.
- Detection stability is never reported without the paired refusal
  stability on feasible seeds: a model that refuses everything in every
  sample is perfectly consistent and perfectly wrong.
- Validation is strict: one model, one condition, identical seed sets,
  and identical prompt hashes per seed across files, so samples from
  different prompts or conditions cannot be aggregated by accident.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .instructions import load_seeds
from .loader import load_environment
from .metrics import TERMINAL_VERDICTS, observed_verdict
from .rescore import POLICIES, rescore_records
from .runner import load_records


@dataclass(frozen=True)
class SeedConsistency:
    seed_id: str
    label: str
    expected_terminal: tuple | None
    verdicts: tuple[str, ...]  # one lenient observed verdict per sample, in file order
    modal_verdict: str
    agreement: int  # how many samples produced the modal verdict
    detected_count: int | None  # terminal-expected seeds: samples with the right terminal type
    exact_count: int | None  # of those, samples whose reason or candidate set was exactly right
    refused_count: int | None  # feasible seeds: samples answered with any terminal

    @property
    def stable(self) -> bool:
        return self.agreement == len(self.verdicts)


@dataclass(frozen=True)
class ConsistencyReport:
    model: str
    condition: str
    k: int
    policy: str
    temperatures: tuple  # distinct recorded temperatures across all samples
    strict_malformed: tuple[int, ...]  # per file, before any re-scoring
    per_seed: tuple[SeedConsistency, ...]

    @property
    def stable_count(self) -> int:
        return sum(1 for s in self.per_seed if s.stable)

    @property
    def agreement_histogram(self) -> Counter:
        return Counter(s.agreement for s in self.per_seed)


def validate_sample_files(record_lists: list[list[dict]]) -> None:
    if len(record_lists) < 2:
        raise ValueError(f"consistency needs at least 2 sample files, got {len(record_lists)}")
    models = {r["model"] for records in record_lists for r in records}
    conditions = {r["condition"] for records in record_lists for r in records}
    if len(models) != 1 or len(conditions) != 1:
        raise ValueError(f"one model and condition at a time, got models {models} and conditions {conditions}")
    id_sets = []
    for i, records in enumerate(record_lists):
        ids = [r["seed_id"] for r in records]
        if len(set(ids)) != len(ids):
            raise ValueError(f"sample file {i} contains duplicate seed records")
        id_sets.append(set(ids))
    if any(ids != id_sets[0] for ids in id_sets[1:]):
        raise ValueError("sample files do not cover the same seed set; complete every sample first")
    hashes: dict[str, str] = {}
    for records in record_lists:
        for r in records:
            previous = hashes.setdefault(r["seed_id"], r["prompt_sha256"])
            if previous != r["prompt_sha256"]:
                raise ValueError(
                    f"seed {r['seed_id']!r} was prompted differently across sample files; "
                    "samples must come from one prompt and condition"
                )


def _modal(verdicts: tuple[str, ...]) -> tuple[str, int]:
    counts = Counter(verdicts)
    best = max(counts.items(), key=lambda item: (item[1], item[0]))
    return best[0], best[1]


def _seed_consistency(sample_records: list[dict]) -> SeedConsistency:
    first = sample_records[0]
    expected = tuple(first["expected_terminal"]) if first["expected_terminal"] else None
    verdicts = tuple(observed_verdict(r) for r in sample_records)
    modal_verdict, agreement = _modal(verdicts)

    detected_count = exact_count = refused_count = None
    if expected is None:
        refused_count = sum(1 for v in verdicts if v in TERMINAL_VERDICTS)
    elif expected[0] == "infeasible":
        detected_count = sum(1 for v in verdicts if v == "terminal_infeasible")
        exact_count = sum(
            1
            for r in sample_records
            if observed_verdict(r) == "terminal_infeasible"
            and (r.get("terminal") or {}).get("reason") == expected[1]
        )
    elif expected[0] == "clarify":
        detected_count = sum(1 for v in verdicts if v == "terminal_clarify")
        wanted = sorted(first.get("clarify_candidates") or [])
        exact_count = sum(
            1
            for r in sample_records
            if observed_verdict(r) == "terminal_clarify"
            and sorted((r.get("terminal") or {}).get("candidates", [])) == wanted
        )

    return SeedConsistency(
        seed_id=first["seed_id"],
        label=first["label"],
        expected_terminal=expected,
        verdicts=verdicts,
        modal_verdict=modal_verdict,
        agreement=agreement,
        detected_count=detected_count,
        exact_count=exact_count,
        refused_count=refused_count,
    )


def consistency_report(
    record_lists: list[list[dict]],
    seeds,
    environments,
    policy: str = "lenient",
) -> ConsistencyReport:
    validate_sample_files(record_lists)
    strict_malformed = tuple(sum(1 for r in records if r["verdict"] == "malformed") for records in record_lists)
    rescored = [rescore_records(records, seeds, environments, policy) for records in record_lists]
    by_id = [{r["seed_id"]: r for r in records} for records in rescored]
    seed_order = [r["seed_id"] for r in record_lists[0]]
    per_seed = tuple(_seed_consistency([sample[sid] for sample in by_id]) for sid in seed_order)
    return ConsistencyReport(
        model=record_lists[0][0]["model"],
        condition=record_lists[0][0]["condition"],
        k=len(record_lists),
        policy=policy,
        temperatures=tuple(sorted({r.get("temperature") for records in record_lists for r in records}, key=str)),
        strict_malformed=strict_malformed,
        per_seed=per_seed,
    )


def render_consistency(report: ConsistencyReport) -> str:
    k = report.k
    total = len(report.per_seed)
    traps = [s for s in report.per_seed if s.detected_count is not None]
    feasible = [s for s in report.per_seed if s.refused_count is not None]

    lines = [
        f"model: {report.model}   condition: {report.condition}   k: {k}   seeds: {total}   policy: {report.policy}",
        "temperatures recorded: " + ", ".join(str(t) for t in report.temperatures),
        "strict malformed per sample: " + ", ".join(f"{m}/{total}" for m in report.strict_malformed),
        "",
        f"seeds with the same verdict in every sample: {report.stable_count}/{total}",
        "agreement histogram (modal verdict count: seeds): "
        + "   ".join(f"{j}/{k}: {n}" for j, n in sorted(report.agreement_histogram.items(), reverse=True)),
        "",
        f"trap seeds detected in all {k} samples: "
        + f"{sum(1 for s in traps if s.detected_count == k)}/{len(traps)}"
        + f"   in some: {sum(1 for s in traps if 0 < s.detected_count < k)}"
        + f"   in none: {sum(1 for s in traps if s.detected_count == 0)}",
        f"feasible seeds refused in at least one sample: "
        + f"{sum(1 for s in feasible if s.refused_count > 0)}/{len(feasible)}"
        + f"   in every sample: {sum(1 for s in feasible if s.refused_count == k)}",
        "",
        "unstable seeds (verdicts in sample order):",
    ]
    unstable = [s for s in report.per_seed if not s.stable]
    if not unstable:
        lines.append("  none")
    for s in unstable:
        lines.append(f"  {s.seed_id} ({s.label}): " + ", ".join(s.verdicts))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate k sampled runs into a per-seed consistency report.")
    parser.add_argument("results", nargs="+", help="two or more results .jsonl files from the same experiment")
    parser.add_argument("--policy", default="lenient", choices=POLICIES)
    parser.add_argument("--seeds", default="instructions/seeds_house_01.json")
    parser.add_argument("--environments-dir", default="environments")
    args = parser.parse_args()

    record_lists = [load_records(path) for path in args.results]
    seeds = load_seeds(args.seeds)
    environments = {
        name: load_environment(Path(args.environments_dir) / f"{name}.json")
        for name in sorted({r["environment"] for records in record_lists for r in records})
    }
    report = consistency_report(record_lists, seeds, environments, args.policy)
    for path, malformed in zip(args.results, report.strict_malformed):
        print(f"sample: {path}   strict malformed: {malformed}/{len(report.per_seed)}")
    print()
    print(render_consistency(report))


if __name__ == "__main__":
    main()
