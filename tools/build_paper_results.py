"""Generate the results tables, for the paper and the README, from the
committed run records.

Prose is written by hand; numbers are not. This tool derives every
results table directly from results/*.jsonl using the same rescoring and
metrics code as the rest of the repository, so neither the paper nor the
README can drift from the data. Model display names are never typed
here: each run's records carry the model alias, and the alias resolves
through configs/model_manifest.json, which records the exact API
checkpoint each alias called. Rerun after any completed run and commit
the regenerated files.

Run with --list to print the canonical fixed-prompt grid and its run
count without writing anything.

Outputs:
  paper/generated/run_summary.tex        one row per complete committed run
  paper/generated/hallucination_table.tex  hallucinated_entity counts per
                                            obfuscated run, the token
                                            confusability artefact record
  paper/generated/model_manifest.tex     model aliases and the exact API
                                            checkpoints they called
  README.md                              the markdown run table between the
                                            generated-results markers
"""

import json
import os
import sys

sys.path.insert(0, os.getcwd())

from plan_failure_bench.instructions import load_seeds
from plan_failure_bench.loader import load_environment
from plan_failure_bench.metrics import detection_report, observed_verdict
from plan_failure_bench.rescore import rescore_records
from plan_failure_bench.runner import load_records

SUITES = {
    "house_01": load_seeds("instructions/seeds_house_01.json"),
    "office_01": load_seeds("instructions/seeds_office_01.json"),
}
ENVS = {
    "house_01": {"house_01": load_environment("environments/house_01.json")},
    "office_01": {"office_01": load_environment("environments/office_01.json")},
}

with open("configs/model_manifest.json", encoding="utf-8") as f:
    MANIFEST = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

# Every complete committed run of the canonical fixed-prompt grid, in
# presentation order: (condition, results path, suite, note). The
# superseded qwen and llama v1-token runs stay in the table because the
# paper discusses the artefacts they produced; they are marked as
# superseded rather than hidden. Model names are not listed here; they
# come from the records themselves via configs/model_manifest.json.
RUNS = [
    ("plain", "results/groq_llama70b_plain.jsonl", "house_01", ""),
    ("obfuscated (v1)", "results/groq_llama70b_obfuscated.jsonl", "house_01", "superseded"),
    ("obfuscated (v2)", "results/groq_llama70b_obfuscated_v2.jsonl", "house_01", ""),
    ("plain", "results/local_qwen_plain.jsonl", "house_01", ""),
    ("obfuscated (v1)", "results/local_qwen_obfuscated.jsonl", "house_01", "superseded"),
    ("obfuscated (v2)", "results/local_qwen_obfuscated_v2.jsonl", "house_01", ""),
    ("plain", "results/gemini_flash_lite_plain.jsonl", "house_01", ""),
    ("obfuscated (v2)", "results/gemini_flash_lite_obfuscated.jsonl", "house_01", ""),
    ("plain", "results/gemini_flash_plain.jsonl", "house_01", ""),
    ("obfuscated (v2)", "results/gemini_flash_obfuscated.jsonl", "house_01", ""),
    ("plain", "results/groq_llama70b_office_plain.jsonl", "office_01", ""),
    ("obfuscated (v2)", "results/groq_llama70b_office_obfuscated.jsonl", "office_01", ""),
    ("plain", "results/local_qwen_office_plain.jsonl", "office_01", ""),
    ("obfuscated (v2)", "results/local_qwen_office_obfuscated.jsonl", "office_01", ""),
    ("plain", "results/gemini_flash_lite_office_plain.jsonl", "office_01", ""),
    ("obfuscated (v2)", "results/gemini_flash_lite_office_obfuscated.jsonl", "office_01", ""),
    ("plain", "results/gemini_flash_office_plain.jsonl", "office_01", ""),
    ("obfuscated (v2)", "results/gemini_flash_office_obfuscated.jsonl", "office_01", ""),
]


def resolve_model(raw, path):
    aliases = {r["model"] for r in raw}
    if len(aliases) != 1:
        raise SystemExit(f"{path}: records carry {len(aliases)} model aliases, expected one")
    alias = aliases.pop()
    if alias not in MANIFEST:
        raise SystemExit(f"{path}: model alias {alias!r} is not in configs/model_manifest.json")
    return alias


def run_stats(condition, path, suite_key):
    raw = load_records(path)
    if len(raw) != 30:
        raise SystemExit(f"{path}: expected 30 records, found {len(raw)}; partial runs do not enter the paper")
    alias = resolve_model(raw, path)
    strict_malformed = sum(1 for r in raw if r["verdict"] == "malformed")
    lenient = rescore_records(raw, SUITES[suite_key], ENVS[suite_key], policy="lenient")
    report = detection_report(lenient)
    detected = sum(s.detected for s in report.per_label.values())
    trap_total = sum(s.total for s in report.per_label.values())
    exact = sum(s.reason_correct for s in report.per_label.values())
    valid_solved = sum(1 for r in lenient if r["label"] == "valid" and observed_verdict(r) == "valid")
    valid_total = sum(1 for r in lenient if r["label"] == "valid")
    hallucinated = sum(1 for r in lenient if observed_verdict(r) == "hallucinated_entity")
    return {
        "alias": alias,
        "model": MANIFEST[alias]["display_name"],
        "env_tex": suite_key.replace("_", "\\_"),
        "condition": condition,
        "strict_malformed": strict_malformed,
        "detected": detected,
        "trap_total": trap_total,
        "exact": exact,
        "fp": report.false_positives,
        "feasible": report.feasible_total,
        "valid_solved": valid_solved,
        "valid_total": valid_total,
        "hallucinated": hallucinated,
    }


if "--list" in sys.argv:
    for condition, path, suite_key, note in RUNS:
        raw = load_records(path)
        alias = resolve_model(raw, path)
        shown_note = f"  [{note}]" if note else ""
        print(f"{alias:18} {MANIFEST[alias]['api_model']:32} {suite_key:10} {condition}{shown_note}  {path}")
    print(f"{len(RUNS)} complete runs in the canonical fixed-prompt grid")
    sys.exit(0)


stats = {path: run_stats(condition, path, suite) for condition, path, suite, _ in RUNS}

summary = [
    "% Generated by tools/build_paper_results.py from results/*.jsonl and",
    "% configs/model_manifest.json. Do not edit by hand; rerun the tool",
    "% after any completed run.",
    "\\begin{tabular}{llllrrrrr}",
    "\\toprule",
    "Model & Environment & Condition & Note & \\shortstack[l]{Format\\\\failures} & \\shortstack[l]{Traps\\\\detected} & \\shortstack[l]{Exact\\\\reasons} & \\shortstack[l]{False\\\\positives} & \\shortstack[l]{Valid\\\\solved} \\\\",
    "\\midrule",
]
for condition, path, _, note in RUNS:
    s = stats[path]
    summary.append(
        f"{s['model']} & {s['env_tex']} & {condition} & {note} & "
        f"{s['strict_malformed']}/30 & {s['detected']}/{s['trap_total']} & {s['exact']} & "
        f"{s['fp']}/{s['feasible']} & {s['valid_solved']}/{s['valid_total']} \\\\"
    )
summary += ["\\bottomrule", "\\end{tabular}"]

hallucination = [
    "% Generated by tools/build_paper_results.py from results/*.jsonl and",
    "% configs/model_manifest.json. Do not edit by hand; rerun the tool",
    "% after any completed run.",
    "\\begin{tabular}{lllr}",
    "\\toprule",
    "Model & Environment & Token scheme & Hallucinated entities \\\\",
    "\\midrule",
]
for condition, path, _, note in RUNS:
    if "obfuscated" not in condition:
        continue
    scheme = "v1" if "v1" in condition else "v2"
    s = stats[path]
    hallucination.append(f"{s['model']} & {s['env_tex']} & {scheme} & {s['hallucinated']} \\\\")
hallucination += ["\\bottomrule", "\\end{tabular}"]

manifest_rows = []
seen_aliases = []
for condition, path, _, note in RUNS:
    alias = stats[path]["alias"]
    if alias not in seen_aliases:
        seen_aliases.append(alias)
manifest_table = [
    "% Generated by tools/build_paper_results.py from",
    "% configs/model_manifest.json. Do not edit by hand.",
    "\\begin{tabular}{lll}",
    "\\toprule",
    "Model & Run alias in records & API checkpoint \\\\",
    "\\midrule",
]
for alias in seen_aliases:
    entry = MANIFEST[alias]
    alias_tex = alias.replace("_", "\\_")
    api_tex = entry["api_model"].replace("_", "\\_")
    manifest_table.append(f"{entry['display_name']} & \\texttt{{{alias_tex}}} & \\texttt{{{api_tex}}} \\\\")
manifest_table += ["\\bottomrule", "\\end{tabular}"]

os.makedirs("paper/generated", exist_ok=True)
for name, lines in (
    ("run_summary.tex", summary),
    ("hallucination_table.tex", hallucination),
    ("model_manifest.tex", manifest_table),
):
    with open(f"paper/generated/{name}", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote paper/generated/" + name)

BEGIN_MARK = "<!-- generated-results:begin -->"
END_MARK = "<!-- generated-results:end -->"

md = [
    BEGIN_MARK,
    "| At a glance | |",
    "|---|---|",
    f"| Instructions | {sum(len(v) for v in SUITES.values())}, each with a proof obligation |",
    "| Trap families | 6, plus valid seeds as false positive bait |",
    f"| Environments | {len(SUITES)}, structurally contrasting |",
    "| Conditions | 2: plain and semantically obfuscated |",
    f"| Models tested | {len(seen_aliases)} |",
    f"| Complete runs in the main fixed-prompt grid | {len(RUNS)}, every record committed |",
    "",
    "| Model | Environment | Condition | Format failures | Traps detected | Exact reasons | False positives | Valid solved |",
    "|---|---|---|---|---|---|---|---|",
]
for condition, path, suite_key, note in RUNS:
    s = stats[path]
    if note and condition.endswith(")"):
        shown = condition[:-1] + f", {note})"
    else:
        shown = condition + (f" ({note})" if note else "")
    md.append(
        f"| {s['model']} | {suite_key} | {shown} | "
        f"{s['strict_malformed']}/30 | {s['detected']}/{s['trap_total']} | {s['exact']} | "
        f"{s['fp']}/{s['feasible']} | {s['valid_solved']}/{s['valid_total']} |"
    )
md += [
    "",
    "Counts under lenient extraction; format failures are strict-policy",
    "malformed responses out of 30. Traps detected covers the 13 seeds per",
    "suite whose expected answer is a terminal and is never read without",
    "the paired false positives on the 17 feasible seeds. This table is",
    "generated by `tools/build_paper_results.py` from the committed",
    "records and is never edited by hand; model names resolve through",
    "[configs/model_manifest.json](configs/model_manifest.json), which",
    "records the exact API checkpoint behind each run alias.",
    END_MARK,
]

readme = open("README.md", encoding="utf-8").read()
begin = readme.find(BEGIN_MARK)
end = readme.find(END_MARK)
if begin == -1 or end == -1:
    raise SystemExit("README.md is missing the generated-results markers")
readme = readme[:begin] + "\n".join(md) + readme[end + len(END_MARK):]
with open("README.md", "w", encoding="utf-8") as f:
    f.write(readme)
print("wrote README.md run table")
