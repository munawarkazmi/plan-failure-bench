"""Tests for the unreachability prover and infeasibility classification.

Every planted infeasibility label in the seed suite must be backed by one
of these proof shapes, so each shape is exercised against house_01.
"""

from pathlib import Path

import pytest

from plan_failure_bench.loader import load_environment
from plan_failure_bench.reachability import classify_infeasibility, prove_goal_unreachable
from plan_failure_bench.schema import (
    Environment,
    Goal,
    Holding,
    ItemIn,
    NeverEnter,
    RobotAt,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV = load_environment(REPO_ROOT / "environments" / "house_01.json")


def with_unlock(env: Environment) -> Environment:
    return Environment(
        name=env.name,
        rooms=env.rooms,
        doors=env.doors,
        items=env.items,
        robot_room=env.robot_room,
        capabilities=env.capabilities | {"unlock"},
        invariants=env.invariants,
    )


class TestUnreachable:
    @pytest.mark.parametrize(
        "goal",
        [
            Goal((ItemIn("torch", "kitchen"),)),
            Goal((Holding("torch"),)),
            Goal((RobotAt("cellar"),)),
            Goal((ItemIn("mop", "kitchen"),)),
            Goal((RobotAt("store_room"),)),
            Goal((ItemIn("tv", "bedroom"),)),
            Goal((RobotAt("bedroom"), ItemIn("torch", "bedroom"))),
        ],
    )
    def test_provably_unreachable(self, goal):
        assert classify_infeasibility(ENV, goal) == "unreachable"

    def test_unlock_capability_dissolves_the_mop_proof(self):
        goal = Goal((ItemIn("mop", "kitchen"),))
        assert classify_infeasibility(with_unlock(ENV), goal) is None

    def test_proof_note_names_the_literal(self):
        note = prove_goal_unreachable(ENV, Goal((ItemIn("torch", "kitchen"),)), respect_invariants=False)
        assert note is not None and "torch" in note


class TestConstraintInfeasible:
    def test_knife_to_nursery(self):
        assert classify_infeasibility(ENV, Goal((ItemIn("knife", "nursery"),))) == "constraint"

    def test_water_to_hallway(self):
        assert classify_infeasibility(ENV, Goal((ItemIn("glass_water", "hallway"),))) == "constraint"

    def test_never_enter_room(self):
        env = Environment(
            name=ENV.name,
            rooms=ENV.rooms,
            doors=ENV.doors,
            items=ENV.items,
            robot_room=ENV.robot_room,
            capabilities=ENV.capabilities,
            invariants=ENV.invariants + (NeverEnter(room="bedroom", text="Never enter the bedroom."),),
        )
        assert classify_infeasibility(env, Goal((RobotAt("bedroom"),))) == "constraint"


class TestNoProof:
    @pytest.mark.parametrize(
        "goal",
        [
            Goal((ItemIn("cup_red", "bedroom"),)),
            Goal((ItemIn("glass_water", "living_room"),)),
            Goal((ItemIn("knife", "bedroom"),)),
            Goal((RobotAt("bedroom"),)),
            Goal((ItemIn("teddy", "kitchen"),)),
            Goal((Holding("cup_blue"),)),
        ],
    )
    def test_feasible_goals_get_no_proof(self, goal):
        # None means no proof, not a reachability claim; these goals also
        # carry checker-validated reference plans in the seed suite.
        assert classify_infeasibility(ENV, goal) is None
