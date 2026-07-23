"""Tests for the PDDL compiler and plan translation."""

from pathlib import Path

import pytest

from plan_failure_bench.dsl import Step
from plan_failure_bench.loader import load_environment
from plan_failure_bench.pddl import compile_domain, compile_problem, translate_plan
from plan_failure_bench.schema import Goal, ItemIn, RobotAt

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV = load_environment(REPO_ROOT / "environments" / "house_01.json")


class TestDomain:
    def test_profile_filtering(self):
        domain = compile_domain(ENV)
        assert "(:action goto" in domain
        assert "(:action pick" in domain
        assert "(:action unlock" not in domain

    def test_deterministic(self):
        assert compile_domain(ENV) == compile_domain(ENV)


class TestProblem:
    def test_init_facts(self):
        problem = compile_problem(ENV, Goal((ItemIn("cup_red", "bedroom"),)))
        assert "(at-robot hallway)" in problem
        assert "(gripper-empty)" in problem
        assert "(door-locked d_living_store)" in problem
        assert "(connects d_kitchen_hall kitchen hallway)" in problem
        assert "(connects d_kitchen_hall hallway kitchen)" in problem
        assert "(item-in torch cellar)" in problem
        assert "(portable cup_red)" in problem
        assert "(portable tv)" not in problem
        assert "(:goal (and (item-in cup_red bedroom)))" in problem


class TestTranslation:
    def test_happy_path(self):
        steps = (
            Step("open", ("d_hall_bedroom",)),
            Step("goto", ("kitchen",)),
            Step("pick", ("cup_red",)),
            Step("goto", ("hallway",)),
            Step("goto", ("bedroom",)),
            Step("place", ("cup_red",)),
        )
        t = translate_plan(ENV, steps)
        assert t.failed_index is None
        assert t.names == (
            "(open d_hall_bedroom hallway bedroom)",
            "(goto hallway kitchen d_kitchen_hall)",
            "(pick cup_red kitchen)",
            "(goto kitchen hallway d_kitchen_hall)",
            "(goto hallway bedroom d_hall_bedroom)",
            "(place cup_red bedroom)",
        )

    @pytest.mark.parametrize(
        "steps, failed",
        [
            ((Step("goto", ("hallway",)),), 0),
            ((Step("goto", ("store_room",)),), 0),
            ((Step("goto", ("cup_red",)),), 0),
            ((Step("open", ("kitchen",)),), 0),
            ((Step("pick", ("d_kitchen_hall",)),), 0),
            ((Step("goto", ("kitchen",)), Step("goto", ("nursery",))), 1),
        ],
    )
    def test_untranslatable_steps(self, steps, failed):
        assert translate_plan(ENV, steps).failed_index == failed

    def test_tracking_is_optimistic(self):
        # goto through a closed door translates fine; judging it is the
        # validator's job, and tracking assumes the move happened.
        steps = (Step("goto", ("bedroom",)), Step("goto", ("hallway",)))
        t = translate_plan(ENV, steps)
        assert t.failed_index is None
        assert t.names[0] == "(goto hallway bedroom d_hall_bedroom)"
        assert t.names[1] == "(goto bedroom hallway d_hall_bedroom)"

    def test_goal_only_affects_goal_section(self):
        p1 = compile_problem(ENV, Goal((RobotAt("cellar"),)))
        p2 = compile_problem(ENV, Goal((RobotAt("bedroom"),)))
        assert p1.split("(:goal")[0] == p2.split("(:goal")[0]
