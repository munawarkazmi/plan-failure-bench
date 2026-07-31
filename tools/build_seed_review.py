import json
import os
import sys

sys.path.insert(0, os.getcwd())

from plan_failure_bench.instructions import load_seeds
from plan_failure_bench.loader import load_environment
from plan_failure_bench.metrics import observed_verdict
from plan_failure_bench.rescore import rescore_records
from plan_failure_bench.runner import load_records

seeds = load_seeds("instructions/seeds_house_01.json")
office_seeds = load_seeds("instructions/seeds_office_01.json")
envs = {"house_01": load_environment("environments/house_01.json")}
office_envs = {"office_01": load_environment("environments/office_01.json")}

with open("configs/model_manifest.json", encoding="utf-8") as f:
    MANIFEST = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

# (condition label, results path); model display names come from the
# records' model alias via configs/model_manifest.json, never typed here.
RUNS = [
    ("plain", "results/groq_llama70b_plain.jsonl"),
    ("obfuscated (v2 tokens)", "results/groq_llama70b_obfuscated_v2.jsonl"),
    ("plain", "results/local_qwen_plain.jsonl"),
    ("obfuscated (v2 tokens)", "results/local_qwen_obfuscated_v2.jsonl"),
    ("plain", "results/gemini_flash_lite_plain.jsonl"),
    ("obfuscated (v2 tokens)", "results/gemini_flash_lite_obfuscated.jsonl"),
    ("plain", "results/gemini_flash_plain.jsonl"),
    ("obfuscated (v2 tokens)", "results/gemini_flash_obfuscated.jsonl"),
]

OFFICE_RUNS = [
    ("plain", "results/groq_llama70b_office_plain.jsonl"),
    ("obfuscated (v2 tokens)", "results/groq_llama70b_office_obfuscated.jsonl"),
    ("plain", "results/local_qwen_office_plain.jsonl"),
    ("obfuscated (v2 tokens)", "results/local_qwen_office_obfuscated.jsonl"),
    ("plain", "results/gemini_flash_lite_office_plain.jsonl"),
    ("obfuscated (v2 tokens)", "results/gemini_flash_lite_office_obfuscated.jsonl"),
    ("plain", "results/gemini_flash_office_plain.jsonl"),
    ("obfuscated (v2 tokens)", "results/gemini_flash_office_obfuscated.jsonl"),
]


def run_title(raw, condition, path):
    aliases = {r["model"] for r in raw}
    if len(aliases) != 1:
        raise SystemExit(f"{path}: records carry {len(aliases)} model aliases, expected one")
    alias = aliases.pop()
    if alias not in MANIFEST:
        raise SystemExit(f"{path}: model alias {alias!r} is not in configs/model_manifest.json")
    return f"{MANIFEST[alias]['display_name']}, {condition}"


def index_runs(runs, run_seeds, run_envs):
    by_run = {}
    for condition, path in runs:
        raw = load_records(path)
        name = run_title(raw, condition, path)
        records = rescore_records(raw, run_seeds, run_envs, policy="lenient")
        by_run[name] = {r["seed_id"]: r for r in records}
    return by_run


by_run = index_runs(RUNS, seeds, envs)
office_by_run = index_runs(OFFICE_RUNS, office_seeds, office_envs)


def note(record):
    verdict = observed_verdict(record)
    terminal = record.get("terminal")
    if terminal is not None:
        if terminal["type"] == "infeasible":
            return f"reason: {terminal['reason']}"
        return "candidates: " + ", ".join(terminal.get("candidates", []))
    detail = record.get("detail") or ""
    if verdict == "valid" or not detail:
        return ""
    return detail[:90]


lines = [
    "# Seed wording review sheet",
    "",
    "One section per seed: the instruction as models see it, the authoring",
    "rationale, and how each of the four Phase 1 runs answered under the",
    "lenient extraction policy. Purpose: judge the wording of each",
    "instruction against real model behaviour. Counts are single",
    "observations per cell; read them as anecdotes, not rates.",
    "",
    "Generated from the committed results files. Every obfuscated run",
    "shown here uses v2 distinct tokens; the superseded v1 runs remain",
    "in the repository history and in the paper's run table.",
    "",
]

def seed_heading(seed):
    expected = "plan expected"
    if seed.expected_terminal is not None:
        expected = " ".join(str(x) for x in seed.expected_terminal) + " expected"
    return f"## {seed.environment} {seed.id} ({seed.label}, {expected})"


for seed in seeds:
    lines.append(seed_heading(seed))
    lines.append("")
    lines.append(f"**Instruction:** {seed.instruction}")
    lines.append("")
    lines.append(f"*Author note:* {seed.notes}")
    lines.append("")
    lines.append("| run | lenient verdict | note |")
    lines.append("|---|---|---|")
    for name in by_run:
        record = by_run[name][seed.id]
        lines.append(f"| {name} | {observed_verdict(record)} | {note(record)} |")
    lines.append("")

lines.append("# office_01 seeds")
lines.append("")
lines.append(f"{len(office_by_run)} complete runs: all four models, each in both")
lines.append("conditions. Same reading rules as above: single")
lines.append("observations per cell, anecdotes rather than rates.")
lines.append("")
for seed in office_seeds:
    lines.append(seed_heading(seed))
    lines.append("")
    lines.append(f"**Instruction:** {seed.instruction}")
    lines.append("")
    lines.append(f"*Author note:* {seed.notes}")
    lines.append("")
    lines.append("| run | lenient verdict | note |")
    lines.append("|---|---|---|")
    for name in office_by_run:
        record = office_by_run[name][seed.id]
        lines.append(f"| {name} | {observed_verdict(record)} | {note(record)} |")
    lines.append("")

os.makedirs("docs", exist_ok=True)
with open("docs/seed_review.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("wrote docs/seed_review.md with", len(seeds) + len(office_seeds), "seeds")
