"""Run a seed suite against a model and record everything.

The runner is deliberately dumb: it assembles the fixed prompt, sends it,
runs the checker, and writes one self-contained JSONL record per seed.
All scoring judgements live in metrics.py; a record carries the raw
response, the checker's verdict, and the seed's expectations so results
files can be re-scored without re-running any model.

No format retries: at temperature zero a resend is a replay, and a retry
policy that only helps stochastic models would quietly bias the
comparison. Malformed responses are recorded as malformed.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .adapter import call_model, load_model_configs
from .checker import CheckResult, check_response
from .dsl import ClarifyResponse, InfeasibleResponse
from .instructions import Seed, load_seeds
from .loader import load_environment
from .obfuscation import load_obfuscation
from .prompts import build_prompt, load_template, prompt_sha256
from .schema import Environment, Goal


def _terminal_payload(result: CheckResult):
    if isinstance(result.terminal, InfeasibleResponse):
        return {"type": "infeasible", "reason": result.terminal.reason}
    if isinstance(result.terminal, ClarifyResponse):
        return {"type": "clarify", "candidates": sorted(result.terminal.candidates)}
    return None


def check_seed(env: Environment, seed: Seed, response_text: str) -> dict:
    """Checker outputs for one response, as a plain JSON-serialisable dict."""
    if seed.alternatives:
        per_alternative = {
            alt.binding: check_response(env, alt.goal, response_text) for alt in seed.alternatives
        }
        results = list(per_alternative.values())
        verdicts = {r.verdict for r in results}
        primary = results[0]
        return {
            "verdict": verdicts.pop() if len(verdicts) == 1 else None,
            "detail": primary.detail,
            "step_index": primary.step_index,
            "goal_satisfied": None,
            "goal_total": None,
            "invariant_breached": any(r.invariant_breached for r in results),
            "terminal": _terminal_payload(primary),
            "per_alternative": {b: r.verdict for b, r in per_alternative.items()},
            "goalless": False,
        }
    goal = seed.goal if seed.goal is not None else Goal(())
    result = check_response(env, goal, response_text)
    return {
        "verdict": result.verdict,
        "detail": result.detail,
        "step_index": result.step_index,
        "goal_satisfied": result.goal_satisfied,
        "goal_total": result.goal_total,
        "invariant_breached": result.invariant_breached,
        "terminal": _terminal_payload(result),
        "per_alternative": None,
        "goalless": seed.goal is None,
    }


def run_suite(
    seeds: tuple[Seed, ...],
    environments: dict[str, Environment],
    template: str,
    call_fn,
    model_name: str,
    condition: str = "plain",
    out_path: str | Path | None = None,
    obfuscations: dict | None = None,
) -> list[dict]:
    """call_fn(prompt, seed) -> raw response text. Injectable for tests.

    With obfuscations (env name to Obfuscation), the model sees the
    obfuscated prompt and its raw response is inverted back to canonical
    vocabulary before checking. The record keeps the raw response as the
    model produced it, plus the canonical form the checker judged.
    """
    records = []
    for seed in seeds:
        env = environments[seed.environment]
        prompt = build_prompt(template, env, seed.instruction)
        obf = obfuscations.get(seed.environment) if obfuscations else None
        if obf is not None:
            prompt = obf.apply(prompt)
        response_text = call_fn(prompt, seed)
        canonical_text = obf.invert(response_text) if obf is not None else response_text
        record = {
            "seed_id": seed.id,
            "label": seed.label,
            "environment": seed.environment,
            "condition": condition,
            "model": model_name,
            "prompt_sha256": prompt_sha256(prompt),
            "expected_terminal": list(seed.expected_terminal) if seed.expected_terminal else None,
            "clarify_candidates": list(seed.clarify_candidates) or None,
            "response": response_text,
            "response_canonical": canonical_text if obf is not None else None,
            "obfuscation_version": obf.version if obf is not None else None,
            "timestamp": time.time(),
        }
        record.update(check_seed(env, seed, canonical_text))
        records.append(record)
    if out_path is not None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
    return records


def load_records(path: str | Path) -> list[dict]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the seed suite against one model.")
    parser.add_argument("--config", required=True, help="path to a model config JSON file")
    parser.add_argument("--model", required=True, help="name of the config entry to use")
    parser.add_argument("--seeds", default="instructions/seeds_house_01.json")
    parser.add_argument("--environments-dir", default="environments")
    parser.add_argument("--prompt", default="prompts/task_prompt.txt")
    parser.add_argument("--condition", default="plain")
    parser.add_argument("--out", default=None, help="defaults to results/<model>_<condition>.jsonl")
    args = parser.parse_args()

    configs = load_model_configs(args.config)
    if args.model not in configs:
        raise SystemExit(f"no model named {args.model!r} in {args.config}; have {sorted(configs)}")
    config = configs[args.model]

    seeds = load_seeds(args.seeds)
    environments = {
        name: load_environment(Path(args.environments_dir) / f"{name}.json")
        for name in sorted({s.environment for s in seeds})
    }
    template = load_template(args.prompt)
    out_path = args.out or f"results/{config.name}_{args.condition}.jsonl"

    obfuscations = None
    if args.condition == "obfuscated":
        obfuscations = {
            name: load_obfuscation(env, args.environments_dir) for name, env in environments.items()
        }

    def call_fn(prompt: str, seed: Seed) -> str:
        response = call_model(config, prompt)
        print(f"{seed.id}: {response.latency_s:.1f}s")
        return response.text

    records = run_suite(
        seeds, environments, template, call_fn, config.name, args.condition, out_path, obfuscations
    )
    print(f"wrote {len(records)} records to {out_path}")


if __name__ == "__main__":
    main()
