"""Tests for lenient extraction and offline re-scoring.

The pinned property: a model that answers correctly but wraps its JSON in
prose scores all malformed under strict and identically to a clean oracle
under lenient. Prose wrapping mimics the observed Llama behaviour.
"""

import json
from pathlib import Path

import pytest

from plan_failure_bench.extraction import extract_first_json_object
from plan_failure_bench.instructions import load_seeds, steps_to_text
from plan_failure_bench.metrics import detection_report
from plan_failure_bench.loader import load_environment
from plan_failure_bench.prompts import load_template
from plan_failure_bench.rescore import rescore_records
from plan_failure_bench.runner import run_suite

REPO_ROOT = Path(__file__).resolve().parent.parent
SEEDS = load_seeds(REPO_ROOT / "instructions" / "seeds_house_01.json")
ENVS = {"house_01": load_environment(REPO_ROOT / "environments" / "house_01.json")}
TEMPLATE = load_template(REPO_ROOT / "prompts" / "task_prompt.txt")


class TestExtraction:
    def test_bare_json(self):
        assert extract_first_json_object('{"plan": []}') == '{"plan": []}'

    def test_prose_before_and_after(self):
        text = 'Sure! Here is my answer:\n{"plan": [{"action": "goto", "args": ["nursery"]}]}\nThis works because the door is open.'
        assert json.loads(extract_first_json_object(text))["plan"][0]["action"] == "goto"

    def test_fenced_json(self):
        text = '```json\n{"infeasible": {"reason": "unreachable"}}\n```'
        assert json.loads(extract_first_json_object(text)) == {"infeasible": {"reason": "unreachable"}}

    def test_braces_inside_strings(self):
        text = 'note {"clarify": {"candidates": ["curly}name", "cup_blue"]}} tail'
        assert json.loads(extract_first_json_object(text))["clarify"]["candidates"][0] == "curly}name"

    def test_non_response_objects_skipped(self):
        text = '{"note": "context"} and then {"plan": []}'
        assert json.loads(extract_first_json_object(text)) == {"plan": []}

    def test_unbalanced_json_is_none(self):
        assert extract_first_json_object('{"plan": [{"action": "goto", "args": ["x"]}]') is None

    def test_skips_unparseable_first_object(self):
        text = "{broken} then {\"plan\": []}"
        assert json.loads(extract_first_json_object(text)) == {"plan": []}

    def test_no_json_is_none(self):
        assert extract_first_json_object("I would go to the kitchen first.") is None


def chatty_oracle(prompt, seed):
    if seed.expected_terminal is None:
        core = steps_to_text(seed.reference_plan)
    elif seed.expected_terminal[0] == "infeasible":
        core = json.dumps({"infeasible": {"reason": seed.expected_terminal[1]}})
    else:
        core = json.dumps({"clarify": {"candidates": list(seed.clarify_candidates)}})
    return f"Sure! Here is my answer:\n{core}\nThis plan is valid because of reasons."


class TestRescore:
    def test_chatty_oracle_recovers_fully_under_lenient(self):
        records = run_suite(SEEDS, ENVS, TEMPLATE, chatty_oracle, "chatty")
        strict = detection_report(records)
        assert strict.format_failures == 30

        rescored = rescore_records(records, SEEDS, ENVS, policy="lenient")
        report = detection_report(rescored)
        assert report.format_failures == 0
        assert report.false_positives == 0
        assert all(s.detected == s.total for s in report.per_label.values())
        assert all(s.reason_correct == s.total for s in report.per_label.values())
        for r in rescored:
            if r["expected_terminal"] is None:
                assert r["verdict"] == "valid", r["seed_id"]
            assert r["extraction_policy"] == "lenient"

    def test_strict_policy_reproduces_runner_verdicts(self):
        records = run_suite(SEEDS, ENVS, TEMPLATE, chatty_oracle, "chatty")
        rescored = rescore_records(records, SEEDS, ENVS, policy="strict")
        assert [r["verdict"] for r in rescored] == [r["verdict"] for r in records]

    def test_genuinely_broken_json_stays_malformed(self):
        def broken(prompt, seed):
            return '{"plan": [{"action": "goto", "args": ["nursery"]}]'

        records = run_suite(SEEDS, ENVS, TEMPLATE, broken, "broken")
        rescored = rescore_records(records, SEEDS, ENVS, policy="lenient")
        assert all(r["verdict"] == "malformed" for r in rescored)

    def test_unknown_policy_rejected(self):
        with pytest.raises(ValueError, match="policy"):
            rescore_records([], SEEDS, ENVS, policy="generous")
