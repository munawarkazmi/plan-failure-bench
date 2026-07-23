"""Tests for response parsing: what is and is not malformed."""

import pytest

from plan_failure_bench.dsl import (
    ClarifyResponse,
    DslError,
    InfeasibleResponse,
    PlanResponse,
    Step,
    parse_response,
)


class TestPlans:
    def test_simple_plan(self):
        r = parse_response('{"plan": [{"action": "goto", "args": ["kitchen"]}]}')
        assert r == PlanResponse(steps=(Step("goto", ("kitchen",)),))

    def test_empty_plan_parses(self):
        assert parse_response('{"plan": []}') == PlanResponse(steps=())

    def test_fenced_json_accepted(self):
        text = '```json\n{"plan": [{"action": "pick", "args": ["cup_red"]}]}\n```'
        assert parse_response(text) == PlanResponse(steps=(Step("pick", ("cup_red",)),))

    def test_unknown_action_parses(self):
        # An invented action is a planning failure, not a format failure.
        r = parse_response('{"plan": [{"action": "wipe", "args": ["floor", "cloth"]}]}')
        assert r.steps[0].action == "wipe"


class TestTerminals:
    def test_infeasible(self):
        r = parse_response('{"infeasible": {"reason": "unreachable"}}')
        assert r == InfeasibleResponse(reason="unreachable")

    def test_clarify(self):
        r = parse_response('{"clarify": {"candidates": ["cup_red", "cup_blue"]}}')
        assert r == ClarifyResponse(candidates=("cup_red", "cup_blue"))

    @pytest.mark.parametrize(
        "text",
        [
            '{"infeasible": {"reason": "impossible"}}',
            '{"infeasible": {}}',
            '{"infeasible": {"reason": "unreachable", "note": "x"}}',
            '{"clarify": {"candidates": ["cup_red"]}}',
            '{"clarify": {"candidates": ["cup_red", "cup_red"]}}',
            '{"clarify": {"candidates": []}}',
            '{"clarify": {"candidates": "cup_red"}}',
        ],
    )
    def test_bad_terminals_malformed(self, text):
        with pytest.raises(DslError):
            parse_response(text)


class TestMalformed:
    @pytest.mark.parametrize(
        "text",
        [
            "I would go to the kitchen first.",
            "[]",
            "{}",
            '{"plan": [], "infeasible": {"reason": "unreachable"}}',
            '{"plans": []}',
            '{"plan": {"action": "goto", "args": ["kitchen"]}}',
            '{"plan": ["goto kitchen"]}',
            '{"plan": [{"action": "goto"}]}',
            '{"plan": [{"action": "goto", "args": ["kitchen"], "why": "start"}]}',
            '{"plan": [{"action": "goto", "args": []}]}',
            '{"plan": [{"action": "goto", "args": ["kitchen", "hallway"]}]}',
            '{"plan": [{"action": "goto", "args": [7]}]}',
            '{"plan": [{"action": "", "args": ["kitchen"]}]}',
            '```json\n{"plan": []',
        ],
    )
    def test_rejected(self, text):
        with pytest.raises(DslError):
            parse_response(text)

    def test_diagnosis_mentions_offending_step(self):
        with pytest.raises(DslError, match=r"plan\[1\]"):
            parse_response('{"plan": [{"action": "goto", "args": ["kitchen"]}, {"action": "pick", "args": []}]}')
