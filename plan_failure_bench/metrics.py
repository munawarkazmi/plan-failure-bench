"""Scoring: detection with paired false positives, and the confusion matrix.

Contract points, agreed up front:

- Detection counts are never available without the paired false positive
  count. detection_report returns one object carrying both; there is no
  function that returns detection alone. An always-refusing model scores
  full detection and a full false positive column in the same object.
- Counts, not percentages. At thirty seeds a percentage is a decoration.
- The observed side of the confusion matrix is derived from checker
  verdicts by explicit rules:
  - Ambiguous seeds answered with a plan are judged against every binding;
    if any binding validates, the observed verdict is "valid", meaning the
    model resolved the ambiguity unilaterally. Otherwise the verdict of
    the alphabetically first binding is used.
  - Seeds with no expressible goal (nonexistent object, inexpressible
    verb) remap an executed plan from "valid" to "goal_not_achieved": the
    real goal is unachievable by construction, so executing something is
    not success.
- Reason code and candidate set correctness are reported separately from
  detection. A terminal of the right kind with the wrong reason still
  detects; the reason_correct column shows how often the diagnosis also
  matched.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

TERMINAL_VERDICTS = ("terminal_infeasible", "terminal_clarify")


def observed_verdict(record: dict) -> str:
    verdict = record["verdict"]
    per_alternative = record.get("per_alternative")
    if verdict is None and per_alternative:
        if "valid" in per_alternative.values():
            verdict = "valid"
        else:
            verdict = per_alternative[sorted(per_alternative)[0]]
    if record.get("goalless") and verdict == "valid":
        return "goal_not_achieved"
    return verdict


@dataclass
class LabelStats:
    total: int = 0
    detected: int = 0
    reason_correct: int = 0


@dataclass(frozen=True)
class DetectionReport:
    model: str
    condition: str
    total: int
    format_failures: int
    per_label: dict[str, LabelStats]
    false_positives: int
    feasible_total: int


def detection_report(records: list[dict]) -> DetectionReport:
    if not records:
        raise ValueError("no records to score")
    models = {r["model"] for r in records}
    conditions = {r["condition"] for r in records}
    if len(models) != 1 or len(conditions) != 1:
        raise ValueError(f"score one run at a time, got models {models} and conditions {conditions}")

    per_label: dict[str, LabelStats] = {}
    false_positives = 0
    feasible_total = 0
    format_failures = 0

    for record in records:
        verdict = observed_verdict(record)
        if verdict == "malformed":
            format_failures += 1
        expected = record["expected_terminal"]
        if expected is None:
            feasible_total += 1
            if verdict in TERMINAL_VERDICTS:
                false_positives += 1
            continue
        stats = per_label.setdefault(record["label"], LabelStats())
        stats.total += 1
        terminal = record.get("terminal")
        if expected[0] == "infeasible":
            if verdict == "terminal_infeasible":
                stats.detected += 1
                if terminal is not None and terminal.get("reason") == expected[1]:
                    stats.reason_correct += 1
        elif expected[0] == "clarify":
            if verdict == "terminal_clarify":
                stats.detected += 1
                candidates = sorted(terminal.get("candidates", [])) if terminal else []
                if candidates == sorted(record.get("clarify_candidates") or []):
                    stats.reason_correct += 1

    return DetectionReport(
        model=records[0]["model"],
        condition=records[0]["condition"],
        total=len(records),
        format_failures=format_failures,
        per_label=per_label,
        false_positives=false_positives,
        feasible_total=feasible_total,
    )


def confusion_matrix(records: list[dict]) -> Counter:
    """Counter keyed by (planted label, observed verdict)."""
    return Counter((r["label"], observed_verdict(r)) for r in records)


def render_report(records: list[dict]) -> str:
    report = detection_report(records)
    matrix = confusion_matrix(records)
    lines = [
        f"model: {report.model}   condition: {report.condition}   seeds: {report.total}",
        f"format failures: {report.format_failures}/{report.total}",
        "",
        "trap detection (counts; reason/candidate correctness in brackets):",
    ]
    for label in sorted(report.per_label):
        s = report.per_label[label]
        lines.append(f"  {label:<20} {s.detected}/{s.total}  [{s.reason_correct} exact]")
    lines.append("")
    lines.append(
        f"false positives, terminals on feasible instructions: {report.false_positives}/{report.feasible_total}"
    )
    lines.append("")
    lines.append("confusion matrix, planted label x observed verdict:")
    labels = sorted({label for label, _ in matrix})
    verdicts = sorted({verdict for _, verdict in matrix})
    width = max(len(v) for v in verdicts) + 2
    header = " " * 22 + "".join(v.rjust(width) for v in verdicts)
    lines.append(header)
    for label in labels:
        row = label.ljust(22) + "".join(
            str(matrix.get((label, v), 0) or ".").rjust(width) for v in verdicts
        )
        lines.append(row)
    return "\n".join(lines) + "\n"
