"""Tests for the k-sampling consistency report.

Sample files are built with the same stub models the runner tests use,
so every aggregation claim is checked against records produced by the
real pipeline, not hand-written fixtures.
"""

import json
from pathlib import Path

import pytest

from plan_failure_bench.consistency import (
    consistency_report,
    render_consistency,
    validate_sample_files,
)
from plan_failure_bench.instructions import load_seeds, steps_to_text
from plan_failure_bench.loader import load_environment
from plan_failure_bench.prompts import load_template
from plan_failure_bench.runner import plan_resume, run_suite

REPO_ROOT = Path(__file__).resolve().parent.parent
SEEDS = load_seeds(REPO_ROOT / "instructions" / "seeds_house_01.json")
ENVS = {"house_01": load_environment(REPO_ROOT / "environments" / "house_01.json")}
TEMPLATE = load_template(REPO_ROOT / "prompts" / "task_prompt.txt")

K_TRAPS = 13  # seeds whose expected answer is a terminal
K_FEASIBLE = 17  # seeds whose expected answer is a plan


def oracle(prompt, seed):
    if seed.expected_terminal is None:
        return steps_to_text(seed.reference_plan)
    if seed.expected_terminal[0] == "infeasible":
        return json.dumps({"infeasible": {"reason": seed.expected_terminal[1]}})
    return json.dumps({"clarify": {"candidates": list(seed.clarify_candidates)}})


def refuser(prompt, seed):
    return json.dumps({"infeasible": {"reason": "unreachable"}})


def make_records(call_fn, model="m", temperature=0.7):
    return run_suite(SEEDS, ENVS, TEMPLATE, call_fn, model, "plain", temperature=temperature)


def by_id(report):
    return {s.seed_id: s for s in report.per_seed}


class TestValidation:
    def test_needs_at_least_two_files(self):
        with pytest.raises(ValueError, match="at least 2"):
            validate_sample_files([make_records(oracle)])

    def test_rejects_mixed_models(self):
        with pytest.raises(ValueError, match="one model"):
            validate_sample_files([make_records(oracle, model="a"), make_records(oracle, model="b")])

    def test_rejects_incomplete_sample(self):
        with pytest.raises(ValueError, match="same seed set"):
            validate_sample_files([make_records(oracle), make_records(oracle)[:-1]])

    def test_rejects_duplicate_seed_records(self):
        records = make_records(oracle)
        with pytest.raises(ValueError, match="duplicate"):
            validate_sample_files([records, records[:1] + records])

    def test_rejects_prompt_mismatch(self):
        a, b = make_records(oracle), make_records(oracle)
        b[0] = dict(b[0], prompt_sha256="0" * 64)
        with pytest.raises(ValueError, match="prompted differently"):
            validate_sample_files([a, b])


class TestPerfectAgreement:
    REPORT = consistency_report([make_records(oracle) for _ in range(3)], SEEDS, ENVS)

    def test_every_seed_stable(self):
        assert self.REPORT.k == 3
        assert self.REPORT.stable_count == len(SEEDS)
        assert self.REPORT.agreement_histogram == {3: len(SEEDS)}

    def test_traps_detected_in_every_sample_with_exact_reasons(self):
        traps = [s for s in self.REPORT.per_seed if s.detected_count is not None]
        assert len(traps) == K_TRAPS
        assert all(s.detected_count == 3 and s.exact_count == 3 for s in traps)

    def test_no_feasible_seed_refused(self):
        feasible = [s for s in self.REPORT.per_seed if s.refused_count is not None]
        assert len(feasible) == K_FEASIBLE
        assert all(s.refused_count == 0 for s in feasible)

    def test_temperature_recorded(self):
        assert self.REPORT.temperatures == (0.7,)

    def test_render_mentions_no_unstable_seeds(self):
        text = render_consistency(self.REPORT)
        assert "same verdict in every sample: 30/30" in text
        assert "none" in text


class TestMixedSamples:
    REPORT = consistency_report([make_records(oracle), make_records(refuser)], SEEDS, ENVS)

    def test_valid_seed_disagrees_and_counts_one_refusal(self):
        v1 = by_id(self.REPORT)["v1"]
        assert v1.verdicts == ("valid", "terminal_infeasible")
        assert v1.agreement == 1
        assert v1.refused_count == 1

    def test_unreachable_seed_agrees_with_exact_reason_twice(self):
        u1 = by_id(self.REPORT)["u1"]
        assert u1.agreement == 2
        assert u1.detected_count == 2
        assert u1.exact_count == 2

    def test_missing_capability_detected_twice_but_exact_once(self):
        # The refuser's terminal type is right, its reason is wrong.
        m1 = by_id(self.REPORT)["m1"]
        assert m1.detected_count == 2
        assert m1.exact_count == 1

    def test_ambiguous_seed_detected_only_by_the_oracle(self):
        a1 = by_id(self.REPORT)["a1"]
        assert a1.verdicts == ("terminal_clarify", "terminal_infeasible")
        assert a1.detected_count == 1
        assert a1.exact_count == 1

    def test_unstable_seeds_listed_in_render(self):
        text = render_consistency(self.REPORT)
        assert "v1 (valid): valid, terminal_infeasible" in text


class TestRunnerTemperaturePlumbing:
    def test_records_carry_the_sampling_temperature(self):
        records = make_records(oracle, temperature=0.7)
        assert all(r["temperature"] == 0.7 for r in records)

    def test_temperature_defaults_to_none(self):
        records = run_suite(SEEDS[:1], ENVS, TEMPLATE, oracle, "m", "plain")
        assert records[0]["temperature"] is None

    def test_resume_refuses_a_different_temperature(self, tmp_path):
        out = tmp_path / "k1.jsonl"
        run_suite(SEEDS[:2], ENVS, TEMPLATE, oracle, "m", "plain", out_path=out, temperature=0.7)
        remaining, append = plan_resume(SEEDS, out, "m", "plain", 0.7)
        assert append and len(remaining) == len(SEEDS) - 2
        with pytest.raises(ValueError, match="temperature"):
            plan_resume(SEEDS, out, "m", "plain", 0.0)

    def test_resume_tolerates_records_predating_the_field(self, tmp_path):
        out = tmp_path / "old.jsonl"
        run_suite(SEEDS[:2], ENVS, TEMPLATE, oracle, "m", "plain", out_path=out)
        raw = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
        for r in raw:
            del r["temperature"]
        out.write_text("".join(json.dumps(r) + "\n" for r in raw), encoding="utf-8")
        remaining, append = plan_resume(SEEDS, out, "m", "plain", 0.7)
        assert append and len(remaining) == len(SEEDS) - 2
