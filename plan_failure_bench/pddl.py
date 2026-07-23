"""Compilation of environments, goals, and plans to PDDL (STRIPS plus typing).

Purpose: differential validation. Our checker's simulation semantics are
re-expressed as a PDDL domain, and plans are validated independently by a
third-party grounder and validator. If the checker and the PDDL route ever
disagree on executability or goal satisfaction, one of them is wrong and
the discrepancy is loud.

Invariants are deliberately absent here: STRIPS has no trajectory
constraints, and adopting PDDL 3 for one feature would loosen the subset.
Constraint checking stays on our side; the differential contract is that
our {valid, constraint_violation} together correspond to PDDL-valid.

The domain emits only the actions in the robot's capability profile, so
capability gaps hold in the compiled model too.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dsl import Step
from .schema import DoorIs, Environment, Goal, GoalLiteral, Holding, ItemIn, RobotAt

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


def compile_domain(env: Environment) -> str:
    actions = "\n".join(_ACTION_BLOCKS[a] for a in sorted(env.capabilities))
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
    (portable ?i - item))
{actions}
)
"""


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


def compile_problem(env: Environment, goal: Goal, name: str = "seed") -> str:
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


def translate_plan(env: Environment, steps: tuple[Step, ...]) -> TranslatedPlan:
    rooms = set(env.rooms)
    door_names = {d.name for d in env.doors}
    item_names = {i.name for i in env.items}
    room = env.robot_room
    names: list[str] = []
    for k, step in enumerate(steps):
        arg = step.args[0]
        if step.action == "goto":
            if arg not in rooms or arg == room:
                return TranslatedPlan(tuple(names), k)
            doors = [d for d, other in env.adjacency(room) if other == arg]
            if not doors:
                return TranslatedPlan(tuple(names), k)
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
        else:
            raise AssertionError(f"cannot translate unknown action {step.action!r}")
    return TranslatedPlan(tuple(names), None)
