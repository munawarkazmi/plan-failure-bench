import os
import sys

sys.path.insert(0, os.getcwd())

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from plan_failure_bench.instructions import load_seeds
from plan_failure_bench.loader import load_environment
from plan_failure_bench.metrics import observed_verdict
from plan_failure_bench.rescore import rescore_records
from plan_failure_bench.runner import load_records

seeds = load_seeds("instructions/seeds_house_01.json")
envs = {"house_01": load_environment("environments/house_01.json")}
office_seeds = load_seeds("instructions/seeds_office_01.json")
office_envs = {"office_01": load_environment("environments/office_01.json")}

RUNS = [
    ("Llama 3.3 70B, plain", "results/groq_llama70b_plain.jsonl"),
    ("Llama 3.3 70B, obfuscated (v1 tokens)", "results/groq_llama70b_obfuscated.jsonl"),
    ("Qwen 2.5 7B, plain", "results/local_qwen_plain.jsonl"),
    ("Qwen 2.5 7B, obfuscated (v2 tokens)", "results/local_qwen_obfuscated_v2.jsonl"),
    ("Gemini 3.1 Flash Lite, plain", "results/gemini_flash_lite_plain.jsonl"),
    ("Gemini 3.1 Flash Lite, obfuscated (v2 tokens)", "results/gemini_flash_lite_obfuscated.jsonl"),
]

OFFICE_RUNS = [
    ("Qwen 2.5 7B, plain", "results/local_qwen_office_plain.jsonl"),
    ("Qwen 2.5 7B, obfuscated (v2 tokens)", "results/local_qwen_office_obfuscated.jsonl"),
    ("Gemini 3.1 Flash Lite, plain", "results/gemini_flash_lite_office_plain.jsonl"),
    ("Gemini 3.1 Flash Lite, obfuscated (v2 tokens)", "results/gemini_flash_lite_office_obfuscated.jsonl"),
]

LABELS = [
    "valid",
    "unreachable_goal",
    "missing_capability",
    "ambiguous_referent",
    "precondition_trap",
    "sequencing_trap",
    "constraint_trap",
]

VERDICT_ORDER = [
    "malformed",
    "hallucinated_entity",
    "unavailable_action",
    "precondition_violation",
    "goal_not_achieved",
    "constraint_violation",
    "valid",
    "terminal_infeasible",
    "terminal_clarify",
]

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
MUTED = "#52514e"
RAMP = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
cmap = LinearSegmentedColormap.from_list("seqblue", RAMP)


def build_figure(runs, run_seeds, run_envs, rows, cols, suptitle, out_path):
    matrices = {}
    all_verdicts = set()
    for title, path in runs:
        records = rescore_records(load_records(path), run_seeds, run_envs, policy="lenient")
        counts = {}
        for r in records:
            key = (r["label"], observed_verdict(r))
            counts[key] = counts.get(key, 0) + 1
            all_verdicts.add(observed_verdict(r))
        matrices[title] = counts

    verdicts = [v for v in VERDICT_ORDER if v in all_verdicts]
    vmax = max(max(m.values()) for m in matrices.values())

    fig, axes = plt.subplots(rows, cols, figsize=(11.5, 4.0 * rows), facecolor=SURFACE)
    for ax, (title, _) in zip(axes.flat, runs):
        counts = matrices[title]
        grid = [[counts.get((label, v), 0) for v in verdicts] for label in LABELS]
        ax.imshow(grid, cmap=cmap, vmin=0, vmax=vmax, aspect="auto")
        ax.set_facecolor(SURFACE)
        ax.set_title(title, fontsize=11, color=TEXT, pad=8)
        ax.set_xticks(range(len(verdicts)))
        ax.set_xticklabels([v.replace("_", "\n") for v in verdicts], fontsize=7, color=MUTED)
        ax.set_yticks(range(len(LABELS)))
        ax.set_yticklabels(LABELS, fontsize=8, color=MUTED)
        ax.tick_params(length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        for i, label in enumerate(LABELS):
            for j, v in enumerate(verdicts):
                n = counts.get((label, v), 0)
                if n:
                    colour = "#ffffff" if n / vmax > 0.55 else TEXT
                    ax.text(j, i, str(n), ha="center", va="center", fontsize=9, color=colour)

    fig.suptitle(suptitle, fontsize=13, color=TEXT)
    fig.text(
        0.5,
        0.015,
        "Rows: what the instruction planted. Columns: what the checker observed. Counts, not rates.",
        ha="center",
        fontsize=9,
        color=MUTED,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    os.makedirs("docs/img", exist_ok=True)
    fig.savefig(out_path, dpi=160, facecolor=SURFACE)
    print("wrote", out_path)


build_figure(
    RUNS,
    seeds,
    envs,
    3,
    2,
    "Planted trap versus observed verdict, 30 seeds per run, lenient extraction",
    "docs/img/confusion_matrices.png",
)
build_figure(
    OFFICE_RUNS,
    office_seeds,
    office_envs,
    2,
    2,
    "office_01: planted trap versus observed verdict, 30 seeds per run, lenient extraction",
    "docs/img/confusion_matrices_office.png",
)
