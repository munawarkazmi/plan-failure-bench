"""Differential tests: our checker versus pyperplan over compiled PDDL.

Agreement contract for every plan that passes the checker's static scan:

    checker verdict                     pyperplan verdict
    valid | constraint_violation   <->  valid
    goal_not_achieved              <->  goal_unsatisfied
    precondition_violation at k    <->  inapplicable/unknown_operator at k
    (untranslatable step at k)     ->   checker precondition_violation at k

constraint_violation maps to PDDL-valid here because the unconstrained
compilation omits invariants, isolating executability.

The constrained compilation carries the invariants as action guards, and
its contract covers the constraint verdicts too:

    checker                             pyperplan, constrained domain
    breach first at step b              inapplicable/unknown_operator at b
    (any verdict)
    precondition_violation at k,        inapplicable/unknown_operator at k
      no earlier breach
    valid                          <->  valid
    goal_not_achieved, no breach   <->  goal_unsatisfied

The corpus is the hand-written trap plans plus seeded random and guided
plans. Static-scan verdicts (malformed, hallucinated_entity,
unavailable_action) are out of differential scope; that layer is a set
membership test auditable by eye.
"""

import json
import random
from pathlib import Path

import pytest

from plan_failure_bench.checker import _apply, check_response
from plan_failure_bench.differential import ground_task, run_plan
from plan_failure_bench.dsl import Step, parse_response
from plan_failure_bench.instructions import load_seeds
from plan_failure_bench.loader import load_environment
from plan_failure_bench.pddl import compile_domain, compile_problem, translate_plan
from plan_failure_bench.schema import Goal, ItemIn, RobotAt, State

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV = load_environment(REPO_ROOT / "environments" / "house_01.json")
STATIC_VERDICTS = ("malformed", "hallucinated_entity", "unavailable_action")


def to_text(steps):
    return json.dumps({"plan": [{"action": s[0], "args": list(s[1:])} for s in steps]})


def assert_agreement(env, goal, task, steps_text):
    ours = check_response(env, goal, steps_text)
    assert ours.verdict not in STATIC_VERDICTS, "corpus should pre-filter static verdicts"
    steps = parse_response(steps_text).steps
    translated = translate_plan(env, steps)
    if translated.failed_index is not None:
        # The plan may already have failed inside the translatable prefix;
        # only if pyperplan accepts the whole prefix must our checker's
        # failure be the untranslatable step itself.
        prefix = run_plan(task, translated.names)
        if prefix.status in ("inapplicable", "unknown_operator"):
            expected = prefix.step_index
        else:
            expected = translated.failed_index
        assert ours.verdict == "precondition_violation", (ours, translated, prefix)
        assert ours.step_index == expected, (ours, translated, prefix)
        return ours
    theirs = run_plan(task, translated.names)
    if theirs.status in ("inapplicable", "unknown_operator"):
        assert ours.verdict == "precondition_violation", (ours, theirs)
        assert ours.step_index == theirs.step_index, (ours, theirs)
    elif theirs.status == "valid":
        assert ours.verdict in ("valid", "constraint_violation"), (ours, theirs)
    else:
        assert theirs.status == "goal_unsatisfied"
        assert ours.verdict == "goal_not_achieved", (ours, theirs)
    return ours


FAILED = ("inapplicable", "unknown_operator")


def assert_constrained_agreement(env, goal, task, steps_text):
    ours = check_response(env, goal, steps_text)
    assert ours.verdict not in STATIC_VERDICTS, "corpus should pre-filter static verdicts"
    if ours.breach_step is not None:
        expected = ours.breach_step
    elif ours.verdict == "precondition_violation":
        expected = ours.step_index
    else:
        expected = None
    translated = translate_plan(env, parse_response(steps_text).steps, constrained=True)
    theirs = run_plan(task, translated.names)
    if translated.failed_index is not None and theirs.status not in FAILED:
        # pyperplan accepted the whole translatable prefix, so the first
        # failure is the untranslatable step itself.
        assert expected == translated.failed_index, (ours, translated, theirs)
    elif expected is not None:
        assert theirs.status in FAILED and theirs.step_index == expected, (ours, theirs)
    elif ours.verdict == "valid":
        assert theirs.status == "valid", (ours, theirs)
    else:
        assert ours.verdict == "goal_not_achieved" and theirs.status == "goal_unsatisfied", (ours, theirs)
    return ours


class TestHandWrittenCorpus:
    CASES = [
        # (goal, steps, expected checker verdict)
        (
            Goal((ItemIn("cup_red", "bedroom"),)),
            [("open", "d_hall_bedroom"), ("goto", "kitchen"), ("pick", "cup_red"), ("goto", "hallway"), ("goto", "bedroom"), ("place", "cup_red")],
            "valid",
        ),
        (
            Goal((ItemIn("cup_red", "bedroom"),)),
            [("goto", "kitchen"), ("pick", "cup_red"), ("goto", "hallway"), ("goto", "bedroom")],
            "precondition_violation",
        ),
        (
            Goal((ItemIn("glass_water", "living_room"),)),
            [("goto", "kitchen"), ("pick", "glass_water"), ("goto", "hallway"), ("goto", "living_room"), ("place", "glass_water")],
            "constraint_violation",
        ),
        (
            Goal((ItemIn("glass_water", "living_room"),)),
            [("goto", "kitchen"), ("open", "d_kitchen_living"), ("pick", "glass_water"), ("goto", "living_room"), ("place", "glass_water")],
            "valid",
        ),
        (
            Goal((ItemIn("knife", "nursery"),)),
            [("goto", "kitchen"), ("pick", "knife"), ("goto", "hallway"), ("goto", "nursery"), ("place", "knife")],
            "constraint_violation",
        ),
        (Goal((ItemIn("cup_red", "bedroom"),)), [], "goal_not_achieved"),
        (Goal((RobotAt("hallway"),)), [], "valid"),
        (Goal((RobotAt("store_room"),)), [("goto", "living_room"), ("goto", "store_room")], "precondition_violation"),
        (Goal((RobotAt("bedroom"),)), [("goto", "bedroom")], "precondition_violation"),
        (Goal((RobotAt("bedroom"),)), [("goto", "hallway")], "precondition_violation"),
        (Goal((RobotAt("kitchen"),)), [("goto", "kitchen"), ("pick", "cup_red"), ("pick", "cup_blue")], "precondition_violation"),
        (Goal((RobotAt("kitchen"),)), [("goto", "kitchen"), ("pick", "tv")], "precondition_violation"),
    ]

    @pytest.mark.parametrize("goal, steps, expected", CASES)
    def test_agreement(self, goal, steps, expected):
        task = ground_task(compile_domain(ENV), compile_problem(ENV, goal))
        ours = assert_agreement(ENV, goal, task, to_text(steps))
        assert ours.verdict == expected


def random_steps(rng, env=ENV):
    rooms = sorted(env.rooms)
    doors = sorted(d.name for d in env.doors)
    items = sorted(i.name for i in env.items)
    everything = rooms + doors + items
    pools = {"goto": rooms, "open": doors, "close": doors, "pick": items, "place": items}
    steps = []
    for _ in range(rng.randint(1, 8)):
        action = rng.choice(sorted(pools))
        pool = pools[action] if rng.random() > 0.15 else everything
        steps.append((action, rng.choice(pool)))
    return steps


def guided_steps(rng, length, env=ENV):
    """A plan of actually-applicable steps, found by trying candidates."""
    state = State.initial(env)
    rooms = sorted(env.rooms)
    doors = sorted(d.name for d in env.doors)
    items = sorted(i.name for i in env.items)
    steps = []
    for _ in range(length):
        candidates = []
        for action, pool in (("goto", rooms), ("open", doors), ("close", doors), ("pick", items), ("place", items)):
            for arg in pool:
                new_state, error = _apply(env, state, Step(action, (arg,)))
                if error is None:
                    candidates.append(((action, arg), new_state))
        if not candidates:
            break
        (step, state) = candidates[rng.randrange(len(candidates))]
        steps.append(step)
    return steps


class TestBulkAgreement:
    def test_random_plans(self):
        rng = random.Random(20260723)
        goal = Goal((ItemIn("cup_red", "bedroom"),))
        task = ground_task(compile_domain(ENV), compile_problem(ENV, goal))
        compared = 0
        for _ in range(400):
            text = to_text(random_steps(rng))
            if check_response(ENV, goal, text).verdict in STATIC_VERDICTS:
                continue
            assert_agreement(ENV, goal, task, text)
            compared += 1
        assert compared >= 300, f"only {compared} plans reached the differential layer"

    def test_guided_plans(self):
        rng = random.Random(20260724)
        goals = [
            Goal((ItemIn("cup_red", "bedroom"),)),
            Goal((RobotAt("nursery"),)),
            Goal((ItemIn("glass_water", "living_room"),)),
            Goal((ItemIn("teddy", "kitchen"), RobotAt("kitchen"))),
        ]
        outcomes = set()
        for goal in goals:
            task = ground_task(compile_domain(ENV), compile_problem(ENV, goal))
            for _ in range(30):
                text = to_text(guided_steps(rng, rng.randint(1, 12)))
                ours = assert_agreement(ENV, goal, task, text)
                outcomes.add(ours.verdict)
        # Guided plans always execute, so both goal outcomes must occur.
        assert "valid" in outcomes and "goal_not_achieved" in outcomes


ENVS = {name: load_environment(REPO_ROOT / "environments" / f"{name}.json") for name in ("house_01", "office_01")}
SEED_GOALS = {
    name: sorted({s.goal for s in load_seeds(REPO_ROOT / "instructions" / f"seeds_{name}.json") if s.goal is not None}, key=repr)
    for name in ENVS
}


class TestConstrainedCompilation:
    """The constrained domain agrees with the checker on constraint verdicts too."""

    @pytest.mark.parametrize("goal, steps, expected", TestHandWrittenCorpus.CASES)
    def test_hand_written_agreement(self, goal, steps, expected):
        task = ground_task(compile_domain(ENV, constrained=True), compile_problem(ENV, goal, constrained=True))
        ours = assert_constrained_agreement(ENV, goal, task, to_text(steps))
        assert ours.verdict == expected

    def test_silent_violation_rejected_at_breach_step(self):
        # The c1 decoy: carrying the glass into the carpeted hallway is step 2.
        goal = Goal((ItemIn("glass_water", "living_room"),))
        steps = [("goto", "kitchen"), ("pick", "glass_water"), ("goto", "hallway"), ("goto", "living_room"), ("place", "glass_water")]
        task = ground_task(compile_domain(ENV, constrained=True), compile_problem(ENV, goal, constrained=True))
        theirs = run_plan(task, translate_plan(ENV, tuple(Step(a, (x,)) for a, x in steps), constrained=True).names)
        assert theirs.status in FAILED and theirs.step_index == 2

    @pytest.mark.parametrize("env_name", sorted(ENVS))
    def test_bulk_agreement_over_seed_goals(self, env_name):
        env = ENVS[env_name]
        rng = random.Random(20260924)
        verdicts = []
        for goal in SEED_GOALS[env_name]:
            task = ground_task(compile_domain(env, constrained=True), compile_problem(env, goal, constrained=True))
            for _ in range(20):
                text = to_text(random_steps(rng, env))
                if check_response(env, goal, text).verdict in STATIC_VERDICTS:
                    continue
                verdicts.append(assert_constrained_agreement(env, goal, task, text))
            for _ in range(20):
                text = to_text(guided_steps(rng, rng.randint(1, 14), env))
                verdicts.append(assert_constrained_agreement(env, goal, task, text))
        breaches = sum(v.breach_step is not None for v in verdicts)
        # Without breaching plans the constraint half of the contract is
        # vacuous, so the corpus must exercise it, including breaches that
        # a later precondition failure or the goal test would otherwise
        # mask. Random plans rarely end in a clean constraint_violation;
        # that verdict is covered by the hand-written cases above and by
        # every seed decoy in test_seeds.
        assert breaches >= 10, breaches
        assert "valid" in {v.verdict for v in verdicts}
        assert any(v.breach_step is not None and v.verdict != "constraint_violation" for v in verdicts)
