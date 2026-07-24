"""End to end pipeline tests with stub models. No network, no real model.

The oracle stub answers every seed correctly; the refuser answers
infeasible(unreachable) to everything; the clarifier answers clarify with
the two cups to everything. Together they pin down the full pipeline:
prompt assembly, checking, record writing, and the scoring contract.
"""

import json
from pathlib import Path

import pytest

from plan_failure_bench.instructions import load_seeds, steps_to_text
from plan_failure_bench.loader import load_environment
from plan_failure_bench.metrics import confusion_matrix, detection_report, render_report
from plan_failure_bench.prompts import load_template
from plan_failure_bench.runner import load_records, run_suite

REPO_ROOT = Path(__file__).resolve().parent.parent
SEEDS = load_seeds(REPO_ROOT / "instructions" / "seeds_house_01.json")
ENVS = {"house_01": load_environment(REPO_ROOT / "environments" / "house_01.json")}
TEMPLATE = load_template(REPO_ROOT / "prompts" / "task_prompt.txt")


def oracle(prompt, seed):
    if seed.expected_terminal is None:
        return steps_to_text(seed.reference_plan)
    if seed.expected_terminal[0] == "infeasible":
        return json.dumps({"infeasible": {"reason": seed.expected_terminal[1]}})
    return json.dumps({"clarify": {"candidates": list(seed.clarify_candidates)}})


def refuser(prompt, seed):
    return json.dumps({"infeasible": {"reason": "unreachable"}})


def clarifier(prompt, seed):
    return json.dumps({"clarify": {"candidates": ["cup_red", "cup_blue"]}})


class TestOracleRun:
    def run(self, tmp_path):
        out = tmp_path / "results.jsonl"
        return run_suite(SEEDS, ENVS, TEMPLATE, oracle, "oracle", out_path=out), out

    def test_everything_detected_no_false_positives(self, tmp_path):
        records, _ = self.run(tmp_path)
        report = detection_report(records)
        assert report.total == 30
        assert report.format_failures == 0
        assert report.false_positives == 0
        assert report.feasible_total == 17
        for label, stats in report.per_label.items():
            assert stats.detected == stats.total, label
            assert stats.reason_correct == stats.total, label
        assert {l: s.total for l, s in report.per_label.items()} == {
            "unreachable_goal": 4,
            "missing_capability": 3,
            "ambiguous_referent": 3,
            "constraint_trap": 3,
        }

    def test_feasible_seeds_all_valid(self, tmp_path):
        records, _ = self.run(tmp_path)
        for r in records:
            if r["expected_terminal"] is None:
                assert r["verdict"] == "valid", r["seed_id"]

    def test_records_round_trip_through_jsonl(self, tmp_path):
        records, out = self.run(tmp_path)
        reloaded = load_records(out)
        assert reloaded == json.loads(json.dumps(records))
        assert all("prompt_sha256" in r and len(r["prompt_sha256"]) == 64 for r in reloaded)

    def test_confusion_matrix_diagonal(self, tmp_path):
        records, _ = self.run(tmp_path)
        matrix = confusion_matrix(records)
        assert sum(matrix.values()) == 30
        assert matrix[("valid", "valid")] == 9
        assert matrix[("unreachable_goal", "terminal_infeasible")] == 4
        assert matrix[("ambiguous_referent", "terminal_clarify")] == 3


class TestRefuserRun:
    def test_detection_paired_with_false_positives(self):
        records = run_suite(SEEDS, ENVS, TEMPLATE, refuser, "refuser")
        report = detection_report(records)
        # Full marks on infeasible traps, zero on ambiguity, and the same
        # object carries the damning false positive count.
        assert report.per_label["unreachable_goal"].detected == 4
        assert report.per_label["unreachable_goal"].reason_correct == 4
        assert report.per_label["missing_capability"].detected == 3
        assert report.per_label["missing_capability"].reason_correct == 0
        assert report.per_label["constraint_trap"].detected == 3
        assert report.per_label["constraint_trap"].reason_correct == 0
        assert report.per_label["ambiguous_referent"].detected == 0
        assert report.false_positives == 17
        assert report.feasible_total == 17


class TestClarifierRun:
    def test_always_clarify_looks_bad_by_construction(self):
        records = run_suite(SEEDS, ENVS, TEMPLATE, clarifier, "clarifier")
        report = detection_report(records)
        assert report.per_label["ambiguous_referent"].detected == 3
        # Candidate exactness: right for the two cup seeds, wrong for books.
        assert report.per_label["ambiguous_referent"].reason_correct == 2
        assert report.per_label["unreachable_goal"].detected == 0
        assert report.false_positives == 17


class TestStreamingAndResume:
    def test_interrupted_run_keeps_completed_records(self, tmp_path):
        out = tmp_path / "partial.jsonl"

        def dies_after_ten(prompt, seed):
            if seed.id == SEEDS[10].id:
                raise RuntimeError("simulated rate limit death")
            return oracle(prompt, seed)

        with pytest.raises(RuntimeError):
            run_suite(SEEDS, ENVS, TEMPLATE, dies_after_ten, "m", out_path=out)
        assert len(load_records(out)) == 10

    def test_resume_completes_without_repeating(self, tmp_path):
        from plan_failure_bench.runner import plan_resume

        out = tmp_path / "partial.jsonl"
        run_suite(SEEDS[:10], ENVS, TEMPLATE, oracle, "m", out_path=out)

        remaining, append = plan_resume(SEEDS, out, "m", "plain")
        assert append is True
        assert len(remaining) == 20
        run_suite(remaining, ENVS, TEMPLATE, oracle, "m", out_path=out, append=append)

        records = load_records(out)
        assert len(records) == 30
        assert len({r["seed_id"] for r in records}) == 30

    def test_resume_refuses_mismatched_file(self, tmp_path):
        from plan_failure_bench.runner import plan_resume

        out = tmp_path / "other.jsonl"
        run_suite(SEEDS[:3], ENVS, TEMPLATE, oracle, "other_model", out_path=out)
        with pytest.raises(ValueError, match="refusing to resume"):
            plan_resume(SEEDS, out, "m", "plain")

    def test_missing_file_means_fresh_run(self, tmp_path):
        from plan_failure_bench.runner import plan_resume

        remaining, append = plan_resume(SEEDS, tmp_path / "absent.jsonl", "m", "plain")
        assert append is False
        assert len(remaining) == 30


class TestReportRendering:
    def test_render_contains_counts_not_percentages(self):
        records = run_suite(SEEDS, ENVS, TEMPLATE, refuser, "refuser")
        text = render_report(records)
        assert "4/4" in text
        assert "17/17" in text
        assert "%" not in text

    def test_mixed_runs_rejected(self):
        a = run_suite(SEEDS, ENVS, TEMPLATE, oracle, "oracle")
        b = run_suite(SEEDS, ENVS, TEMPLATE, refuser, "refuser")
        with pytest.raises(ValueError, match="one run at a time"):
            detection_report(a + b)
