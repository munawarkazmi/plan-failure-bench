import os
import sys

sys.path.insert(0, os.getcwd())

from plan_failure_bench.instructions import load_seeds
from plan_failure_bench.loader import load_environment
from plan_failure_bench.metrics import observed_verdict
from plan_failure_bench.rescore import rescore_records
from plan_failure_bench.runner import load_records

seeds = load_seeds("instructions/seeds_house_01.json")
envs = {"house_01": load_environment("environments/house_01.json")}

RUNS = [
    ("Llama 70B, plain", "results/groq_llama70b_plain.jsonl"),
    ("Llama 70B, obfuscated (v1 tokens)", "results/groq_llama70b_obfuscated.jsonl"),
    ("Qwen 7B, plain", "results/local_qwen_plain.jsonl"),
    ("Qwen 7B, obfuscated (v2 tokens)", "results/local_qwen_obfuscated_v2.jsonl"),
    ("Gemini 3.1 Flash Lite, plain", "results/gemini_flash_lite_plain.jsonl"),
    ("Gemini 3.1 Flash Lite, obfuscated (v2 tokens)", "results/gemini_flash_lite_obfuscated.jsonl"),
]

by_run = {}
for name, path in RUNS:
    records = rescore_records(load_records(path), seeds, envs, policy="lenient")
    by_run[name] = {r["seed_id"]: r for r in records}


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
    "Generated from the committed results files. The Llama obfuscated run",
    "used v1 tokens (known confusability artefact, see results history);",
    "the Qwen and Gemini obfuscated runs used v2 distinct tokens.",
    "",
]

for seed in seeds:
    expected = "plan expected"
    if seed.expected_terminal is not None:
        expected = " ".join(str(x) for x in seed.expected_terminal) + " expected"
    lines.append(f"## {seed.id} ({seed.label}, {expected})")
    lines.append("")
    lines.append(f"**Instruction:** {seed.instruction}")
    lines.append("")
    lines.append(f"*Author note:* {seed.notes}")
    lines.append("")
    lines.append("| run | lenient verdict | note |")
    lines.append("|---|---|---|")
    for name, _ in RUNS:
        record = by_run[name][seed.id]
        lines.append(f"| {name} | {observed_verdict(record)} | {note(record)} |")
    lines.append("")

os.makedirs("docs", exist_ok=True)
with open("docs/seed_review.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("wrote docs/seed_review.md with", len(seeds), "seeds")
