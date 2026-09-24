"""Compilation of environments, goals, and plans to PDDL (STRIPS plus typing).

Purpose: differential validation. Our checker's simulation semantics are
re-expressed as a PDDL domain, and plans are validated independently by a
third-party grounder and validator. If the checker and the PDDL route ever
disagree on executability or goal satisfaction, one of them is wrong and
the discrepancy is loud.

Two compilations exist. The unconstrained domain omits invariants, so
under it our {valid, constraint_violation} together correspond to
PDDL-valid and executability is tested in isolation. The constrained
domain compiles both invariant kinds into STRIPS preconditions, the
standard compilation of PDDL 3 `always` constraints over state atoms,
without leaving the STRIPS-plus-typing subset:

- never_enter(room): goto requires the static (permitted ?to).
- never_hold_in(property, room): holding an item in a room requires the
  static (may-carry ?i ?r). Only goto and pick can make that pair true
  (place empties the gripper; door actions move neither robot nor item),
  so pick requires it for the current room and a carrying goto requires
  it for the target. STRIPS has no disjunction, so goto splits into
  goto (gripper empty) and goto-carrying (holding ?i).

Under the constrained domain a plan is PDDL-valid exactly when our
checker says valid, and the first inapplicable step is our first breach
step whenever the plan breaches an invariant.

Both domains emit only the actions in the robot's capability profile, so
capability gaps hold in the compiled model too.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dsl import Step
from .schema import DoorIs, Environment, Goal, GoalLiteral, Holding, ItemIn, NeverEnter, NeverHoldIn, RobotAt, State

_ACTION_BLOCKS = {
    "goto": """  (:action goto
    :parameters (?from - room ?to - room ?d - door)
    :precondition (and (at-robot ?from) (connects ?d ?from ?to) (door-open ?d))
    :effect (and (at-robot ?to) (not (at-robot ?from))))""",
    "open": """  (:action open
    :parameters (?d - door ?r - room ?r2 - room)
    :precondition (and (at-robot ?r) (connects ?d ?r ?r2) (door-closed ?d) (gripper-empty))
    :effect (and (door-open ?d) (not (door-closed ?d))))""",
    "close": """  (:action close
    :parameters (?d - door ?r - room ?r2 - room)
    :precondition (and (at-robot ?r) (connects ?d ?r ?r2) (door-open ?d) (gripper-empty))
    :effect (and (door-closed ?d) (not (door-open ?d))))""",
    "unlock": """  (:action unlock
    :parameters (?d - door ?r - room ?r2 - room)
    :precondition (and (at-robot ?r) (connects ?d ?r ?r2) (door-locked ?d) (gripper-empty))
    :effect (and (door-closed ?d) (not (door-locked ?d))))""",
    "pick": """  (:action pick
    :parameters (?i - item ?r - room)
    :precondition (and (at-robot ?r) (item-in ?i ?r) (portable ?i) (gripper-empty))
    :effect (and (holding ?i) (not (item-in ?i ?r)) (not (gripper-empty))))""",
    "place": """  (:action place
    :parameters (?i - item ?r - room)
    :precondition (and (at-robot ?r) (holding ?i))
    :effect (and (item-in ?i ?r) (gripper-empty) (not (holding ?i))))""",
}


_CONSTRAINED_BLOCKS = {
    **_ACTION_BLOCKS,
    "goto": """  (:action goto
    :parameters (?from - room ?to - room ?d - door)
    :precondition (and (at-robot ?from) (connects ?d ?from ?to) (door-open ?d) (permitted ?to) (gripper-empty))
    :effect (and (at-robot ?to) (not (at-robot ?from))))
  (:action goto-carrying
    :parameters (?from - room ?to - room ?d - door ?i - item)
    :precondition (and (at-robot ?from) (connects ?d ?from ?to) (door-open ?d) (permitted ?to) (holding ?i) (may-carry ?i ?to))
    :effect (and (at-robot ?to) (not (at-robot ?from))))""",
    "pick": """  (:action pick
    :parameters (?i - item ?r - room)
    :precondition (and (at-robot ?r) (item-in ?i ?r) (portable ?i) (gripper-empty) (may-carry ?i ?r))
    :effect (and (holding ?i) (not (item-in ?i ?r)) (not (gripper-empty))))""",
}


def compile_domain(env: Environment, constrained: bool = False) -> str:
    blocks = _CONSTRAINED_BLOCKS if constrained else _ACTION_BLOCKS
    actions = "\n".join(blocks[a] for a in sorted(env.capabilities))
    extra = "\n    (permitted ?r - room)\n    (may-carry ?i - item ?r - room)" if constrained else ""
    return f"""(define (domain {env.name})
  (:requirements :strips :typing)
  (:types room door item)
  (:predicates
    (at-robot ?r - room)
    (item-in ?i - item ?r - room)
    (holding ?i - item)
    (gripper-empty)
    (door-open ?d - door)
    (door-closed ?d - door)
    (door-locked ?d - door)
    (connects ?d - door ?a - room ?b - room)
    (portable ?i - item){extra})
{actions}
)
"""


def _constraint_facts(env: Environment) -> list[str]:
    """Static facts encoding the invariants; see the module docstring."""
    forbidden_rooms = {inv.room for inv in env.invariants if isinstance(inv, NeverEnter)}
    forbidden_pairs = {(inv.item_property, inv.room) for inv in env.invariants if isinstance(inv, NeverHoldIn)}
    facts = [f"(permitted {r})" for r in sorted(env.rooms) if r not in forbidden_rooms]
    for i in sorted(env.items, key=lambda i: i.name):
        if not i.portable:
            continue
        for r in sorted(env.rooms):
            if not any((p, r) in forbidden_pairs for p in i.properties):
                facts.append(f"(may-carry {i.name} {r})")
    return facts


def _literal_to_pddl(lit: GoalLiteral) -> str:
    if isinstance(lit, ItemIn):
        return f"(item-in {lit.item} {lit.room})"
    if isinstance(lit, RobotAt):
        return f"(at-robot {lit.room})"
    if isinstance(lit, Holding):
        return f"(holding {lit.item})"
    if isinstance(lit, DoorIs):
        return f"(door-{lit.state} {lit.door})"
    raise AssertionError(f"unhandled goal literal {lit!r}")


def compile_problem(env: Environment, goal: Goal, name: str = "seed", constrained: bool = False) -> str:
    if constrained:
        # The constrained model encodes invariants as action guards, which
        # says nothing about the initial state; the loader already rejects
        # environments that start in breach, and this keeps that explicit.
        initial = State.initial(env)
        assert all(inv.holds(initial, env) for inv in env.invariants), env.name
    objects = [
        " ".join(sorted(env.rooms)) + " - room",
        " ".join(sorted(d.name for d in env.doors)) + " - door" if env.doors else "",
        " ".join(sorted(i.name for i in env.items)) + " - item" if env.items else "",
    ]
    init: list[str] = [f"(at-robot {env.robot_room})", "(gripper-empty)"]
    for d in sorted(env.doors, key=lambda d: d.name):
        init.append(f"(door-{d.state} {d.name})")
        init.append(f"(connects {d.name} {d.connects[0]} {d.connects[1]})")
        init.append(f"(connects {d.name} {d.connects[1]} {d.connects[0]})")
    for i in sorted(env.items, key=lambda i: i.name):
        init.append(f"(item-in {i.name} {i.room})")
        if i.portable:
            init.append(f"(portable {i.name})")
    if constrained:
        init.extend(_constraint_facts(env))
    goals = " ".join(_literal_to_pddl(lit) for lit in goal.literals)
    objects_text = "\n    ".join(o for o in objects if o)
    init_text = "\n    ".join(init)
    return f"""(define (problem {name})
  (:domain {env.name})
  (:objects
    {objects_text})
  (:init
    {init_text})
  (:goal (and {goals}))
)
"""


@dataclass(frozen=True)
class TranslatedPlan:
    """Grounded PDDL action names, or the index of the first untranslatable step.

    A step is untranslatable when no grounded action can express it: the
    argument has the wrong sort, the robot's (optimistically tracked)
    position shares no door with a goto target, or goto targets the current
    room. In every such case our checker must also have rejected that step,
    which the differential tests assert.
    """

    names: tuple[str, ...]
    failed_index: int | None


def translate_plan(env: Environment, steps: tuple[Step, ...], constrained: bool = False) -> TranslatedPlan:
    """Ground each step's PDDL name.

    For the constrained domain a goto's name depends on the gripper, which
    is tracked as optimistically as the robot's room: a pick or place that
    is really inapplicable fails in PDDL at that step, before any later
    name built from the tracked value is consulted.
    """
    rooms = set(env.rooms)
    door_names = {d.name for d in env.doors}
    item_names = {i.name for i in env.items}
    room = env.robot_room
    holding: str | None = None
    names: list[str] = []
    for k, step in enumerate(steps):
        arg = step.args[0]
        if step.action == "goto":
            if arg not in rooms or arg == room:
                return TranslatedPlan(tuple(names), k)
            doors = [d for d, other in env.adjacency(room) if other == arg]
            if not doors:
                return TranslatedPlan(tuple(names), k)
            if constrained and holding is not None:
                names.append(f"(goto-carrying {room} {arg} {doors[0]} {holding})")
            else:
                names.append(f"(goto {room} {arg} {doors[0]})")
            room = arg
        elif step.action in ("open", "close", "unlock"):
            if arg not in door_names:
                return TranslatedPlan(tuple(names), k)
            door = env.door(arg)
            other = door.connects[0] if room == door.connects[1] else door.connects[1]
            names.append(f"({step.action} {arg} {room} {other})")
        elif step.action in ("pick", "place"):
            if arg not in item_names:
                return TranslatedPlan(tuple(names), k)
            names.append(f"({step.action} {arg} {room})")
            holding = arg if step.action == "pick" else None
        else:
            raise AssertionError(f"cannot translate unknown action {step.action!r}")
    return TranslatedPlan(tuple(names), None)
