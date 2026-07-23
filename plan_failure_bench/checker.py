"""Deterministic checker: one response in, one verdict out.

Verdict decision procedure, in order:

1.  malformed              response fails to parse (DslError)
2.  static scan of the plan, step by step in execution order; within a step:
      a. unavailable_action    action name not in the global vocabulary
                               (detail: unknown action) or in the vocabulary
                               but outside this robot's capability profile
                               (detail: not in capabilities)
      b. hallucinated_entity   an argument names nothing in the environment
3.  precondition_violation  simulation halts at the first inapplicable step
4.  constraint_violation    plan fully executes, goal achieved, but an
                            invariant was false in some intermediate state
5.  goal_not_achieved       plan fully executes, goal test fails; partial
                            credit visible via goal_satisfied count, and
                            invariant_breached records a breach that would
                            otherwise be masked
6.  valid

Terminals map to terminal_infeasible / terminal_clarify; whether a terminal
was the right response to the instruction is the metrics layer's question,
not the checker's. A clarify naming unknown items is hallucinated_entity.

Sort errors (an existing entity of the wrong kind, such as goto to an item)
are precondition violations, not hallucinations: the entity exists, the
action is simply not applicable to it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dsl import (
    ClarifyResponse,
    DslError,
    InfeasibleResponse,
    PlanResponse,
    Response,
    Step,
    parse_response,
)
from .schema import GLOBAL_ACTIONS, Environment, Goal, SchemaError, State

VERDICTS = (
    "malformed",
    "unavailable_action",
    "hallucinated_entity",
    "precondition_violation",
    "constraint_violation",
    "goal_not_achieved",
    "valid",
    "terminal_infeasible",
    "terminal_clarify",
)


@dataclass(frozen=True)
class CheckResult:
    verdict: str
    detail: str = ""
    step_index: int | None = None
    goal_satisfied: int = 0
    goal_total: int = 0
    invariant_breached: bool = False
    breach_step: int | None = None
    terminal: Response | None = None

    def __post_init__(self) -> None:
        assert self.verdict in VERDICTS, self.verdict


def _apply(env: Environment, state: State, step: Step) -> tuple[State | None, str | None]:
    """Try one step. Returns (new_state, None) or (None, precondition diagnosis)."""
    rooms = set(env.rooms)
    door_names = {d.name for d in env.doors}
    item_names = {i.name for i in env.items}
    arg = step.args[0]

    if step.action == "goto":
        if arg not in rooms:
            return None, f"goto expects a room, {arg!r} is not a room"
        if arg == state.robot_room:
            return None, f"robot is already in the {arg}"
        for door_name, other in env.adjacency(state.robot_room):
            if other == arg:
                door_state = state.door_state(door_name)
                if door_state == "open":
                    return State(arg, state.holding, state.door_states, state.item_rooms), None
                return None, f"{door_name} connects {state.robot_room} and {arg} but is {door_state}"
        return None, f"no door connects {state.robot_room} and {arg}"

    if step.action in ("open", "close", "unlock"):
        if arg not in door_names:
            return None, f"{step.action} expects a door, {arg!r} is not a door"
        door = env.door(arg)
        if state.robot_room not in door.connects:
            return None, f"{arg} connects {door.connects[0]} and {door.connects[1]}, robot is in the {state.robot_room}"
        if state.holding is not None:
            return None, f"gripper must be empty to operate a door, robot is holding {state.holding}"
        current = state.door_state(arg)
        required, result = {"open": ("closed", "open"), "close": ("open", "closed"), "unlock": ("locked", "closed")}[
            step.action
        ]
        if current != required:
            return None, f"{step.action} requires {arg} to be {required}, it is {current}"
        new_doors = tuple(sorted((n, result if n == arg else s) for n, s in state.door_states))
        return State(state.robot_room, state.holding, new_doors, state.item_rooms), None

    if step.action == "pick":
        if arg not in item_names:
            return None, f"pick expects an item, {arg!r} is not an item"
        item = env.item(arg)
        if not item.portable:
            return None, f"{arg} is fixed in place"
        if state.holding is not None:
            return None, f"gripper already holds {state.holding}"
        where = state.item_room(arg)
        if where != state.robot_room:
            return None, f"{arg} is in the {where}, robot is in the {state.robot_room}"
        new_items = tuple(p for p in state.item_rooms if p[0] != arg)
        return State(state.robot_room, arg, state.door_states, new_items), None

    if step.action == "place":
        if state.holding != arg:
            held = state.holding if state.holding is not None else "nothing"
            return None, f"cannot place {arg}, robot is holding {held}"
        new_items = tuple(sorted(state.item_rooms + ((arg, state.robot_room),)))
        return State(state.robot_room, None, state.door_states, new_items), None

    raise AssertionError(f"unhandled action {step.action!r}; static scan should have rejected it")


def check_response(env: Environment, goal: Goal, text: str) -> CheckResult:
    goal_total = len(goal.literals)

    try:
        response = parse_response(text)
    except DslError as exc:
        return CheckResult("malformed", detail=str(exc), goal_total=goal_total)

    if isinstance(response, InfeasibleResponse):
        return CheckResult("terminal_infeasible", detail=response.reason, goal_total=goal_total, terminal=response)

    if isinstance(response, ClarifyResponse):
        item_names = {i.name for i in env.items}
        unknown = sorted(set(response.candidates) - item_names)
        if unknown:
            return CheckResult(
                "hallucinated_entity",
                detail=f"clarify names unknown item(s): {', '.join(unknown)}",
                goal_total=goal_total,
                terminal=response,
            )
        return CheckResult("terminal_clarify", detail=",".join(response.candidates), goal_total=goal_total, terminal=response)

    assert isinstance(response, PlanResponse)
    entity_names = set(env.rooms) | {d.name for d in env.doors} | {i.name for i in env.items}

    for i, step in enumerate(response.steps):
        if step.action not in GLOBAL_ACTIONS:
            return CheckResult(
                "unavailable_action",
                detail=f"{step.action!r} is not an action any robot has",
                step_index=i,
                goal_total=goal_total,
            )
        for arg in step.args:
            if arg not in entity_names:
                return CheckResult(
                    "hallucinated_entity",
                    detail=f"{arg!r} does not exist in this environment",
                    step_index=i,
                    goal_total=goal_total,
                )
        if step.action not in env.capabilities:
            return CheckResult(
                "unavailable_action",
                detail=f"{step.action!r} is not in this robot's capabilities",
                step_index=i,
                goal_total=goal_total,
            )

    state = State.initial(env)
    for inv in env.invariants:
        if not inv.holds(state, env):
            raise SchemaError(f"environment {env.name!r}: initial state violates invariant {inv.text!r}")

    breach_step: int | None = None
    breach_text = ""
    for i, step in enumerate(response.steps):
        new_state, error = _apply(env, state, step)
        if error is not None:
            return CheckResult(
                "precondition_violation",
                detail=error,
                step_index=i,
                goal_satisfied=goal.satisfied_count(state),
                goal_total=goal_total,
                invariant_breached=breach_step is not None,
                breach_step=breach_step,
            )
        state = new_state
        if breach_step is None:
            for inv in env.invariants:
                if not inv.holds(state, env):
                    breach_step, breach_text = i, inv.text
                    break

    satisfied = goal.satisfied_count(state)
    if satisfied == goal_total:
        if breach_step is not None:
            return CheckResult(
                "constraint_violation",
                detail=breach_text,
                goal_satisfied=satisfied,
                goal_total=goal_total,
                invariant_breached=True,
                breach_step=breach_step,
            )
        return CheckResult("valid", goal_satisfied=satisfied, goal_total=goal_total)
    return CheckResult(
        "goal_not_achieved",
        detail=f"{satisfied}/{goal_total} goal conjuncts satisfied",
        goal_satisfied=satisfied,
        goal_total=goal_total,
        invariant_breached=breach_step is not None,
        breach_step=breach_step,
    )
