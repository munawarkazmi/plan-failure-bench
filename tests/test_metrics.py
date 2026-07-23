"""Unit tests for the scoring rules that runner integration cannot isolate."""

from plan_failure_bench.metrics import observed_verdict


def record(**overrides):
    base = {
        "seed_id": "x",
        "label": "valid",
        "model": "m",
        "condition": "plain",
        "verdict": "valid",
        "per_alternative": None,
        "goalless": False,
        "expected_terminal": None,
        "clarify_candidates": None,
        "terminal": None,
    }
    base.update(overrides)
    return base


class TestObservedVerdict:
    def test_plain_verdict_passes_through(self):
        assert observed_verdict(record(verdict="precondition_violation")) == "precondition_violation"

    def test_ambiguous_plan_valid_under_any_binding_is_unilateral_resolution(self):
        r = record(
            verdict=None,
            per_alternative={"cup_red": "valid", "cup_blue": "precondition_violation"},
        )
        assert observed_verdict(r) == "valid"

    def test_ambiguous_plan_invalid_everywhere_uses_first_binding(self):
        r = record(
            verdict=None,
            per_alternative={"cup_red": "goal_not_achieved", "cup_blue": "precondition_violation"},
        )
        assert observed_verdict(r) == "precondition_violation"

    def test_goalless_execution_is_not_success(self):
        r = record(verdict="valid", goalless=True, label="unreachable_goal")
        assert observed_verdict(r) == "goal_not_achieved"

    def test_goalless_terminal_untouched(self):
        r = record(verdict="terminal_infeasible", goalless=True)
        assert observed_verdict(r) == "terminal_infeasible"
