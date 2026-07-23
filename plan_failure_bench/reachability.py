"""Sound unreachability proofs for goal labels.

The full state space of an environment is too large for exhaustive search
(item positions are combinatorial), so labels are proved with a per-literal
abstraction that OVER-approximates what the robot can do:

- Track exactly: the robot's room, the door states, the position of the one
  item the literal mentions (if any), and what the gripper holds, collapsed
  to {nothing, the tracked item, OTHER}.
- Over-approximate everything else: picking up OTHER is allowed in any room
  whenever the gripper is free (as if some portable item were always to
  hand), and carrying OTHER is never blocked by a NeverHoldIn invariant
  (OTHER might lack the property).

Because every real trajectory has a counterpart in the abstraction, a goal
literal BFS cannot reach is unreachable in the real environment: the proof
direction is sound. The converse is not claimed; reachable-looking goals
are proved by a reference plan the checker validates, never by this module.

With respect_invariants=True, transitions that necessarily violate an
invariant are removed (entering a NeverEnter room; entering a room while
provably holding an item with a forbidden property). classify_infeasibility
uses the two modes to tell "unreachable" (impossible even ignoring
invariants) from "constraint" (possible only by breaching one).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .schema import (
    DoorIs,
    Environment,
    Goal,
    GoalLiteral,
    Holding,
    ItemIn,
    NeverEnter,
    NeverHoldIn,
    RobotAt,
)

_OTHER = "__other__"
_HELD = "__held__"


@dataclass(frozen=True)
class _AbstractState:
    robot_room: str
    holding: str | None  # None, _OTHER, or the tracked item's name
    item_pos: str | None  # room, _HELD, or None when no item is tracked
    doors: tuple[tuple[str, str], ...]


def _tracked_item(lit: GoalLiteral) -> str | None:
    if isinstance(lit, (ItemIn, Holding)):
        return lit.item
    return None


def _literal_holds(lit: GoalLiteral, s: _AbstractState) -> bool:
    if isinstance(lit, ItemIn):
        return s.item_pos == lit.room
    if isinstance(lit, Holding):
        return s.holding == lit.item
    if isinstance(lit, RobotAt):
        return s.robot_room == lit.room
    if isinstance(lit, DoorIs):
        return dict(s.doors).get(lit.door) == lit.state
    raise AssertionError(f"unhandled goal literal {lit!r}")


def _goto_forbidden(env: Environment, s: _AbstractState, target: str, tracked: str | None) -> bool:
    for inv in env.invariants:
        if isinstance(inv, NeverEnter) and inv.room == target:
            return True
        if (
            isinstance(inv, NeverHoldIn)
            and inv.room == target
            and s.holding is not None
            and s.holding == tracked
            and inv.item_property in env.item(tracked).properties
        ):
            return True
    return False


def _successors(env: Environment, s: _AbstractState, tracked: str | None, respect_invariants: bool):
    caps = env.capabilities
    doors = dict(s.doors)

    for door_name, other_room in env.adjacency(s.robot_room):
        if doors[door_name] == "open":
            if respect_invariants and _goto_forbidden(env, s, other_room, tracked):
                continue
            yield _AbstractState(other_room, s.holding, s.item_pos, s.doors)

    if s.holding is None:
        for action, required, result in (("open", "closed", "open"), ("close", "open", "closed"), ("unlock", "locked", "closed")):
            if action not in caps:
                continue
            for door_name, _ in env.adjacency(s.robot_room):
                if doors[door_name] == required:
                    new_doors = tuple(sorted((n, result if n == door_name else st) for n, st in s.doors))
                    yield _AbstractState(s.robot_room, None, s.item_pos, new_doors)

    if "pick" in caps and s.holding is None:
        if tracked is not None and s.item_pos == s.robot_room and env.item(tracked).portable:
            yield _AbstractState(s.robot_room, tracked, _HELD, s.doors)
        if any(i.portable and i.name != tracked for i in env.items):
            yield _AbstractState(s.robot_room, _OTHER, s.item_pos, s.doors)

    if "place" in caps:
        if s.holding == tracked and tracked is not None:
            yield _AbstractState(s.robot_room, None, s.robot_room, s.doors)
        if s.holding == _OTHER:
            yield _AbstractState(s.robot_room, None, s.item_pos, s.doors)


def _literal_unreachable(env: Environment, lit: GoalLiteral, respect_invariants: bool) -> bool:
    tracked = _tracked_item(lit)
    initial = _AbstractState(
        robot_room=env.robot_room,
        holding=None,
        item_pos=env.item(tracked).room if tracked is not None else None,
        doors=tuple(sorted((d.name, d.state) for d in env.doors)),
    )
    seen = {initial}
    queue = deque([initial])
    while queue:
        s = queue.popleft()
        if _literal_holds(lit, s):
            return False
        for nxt in _successors(env, s, tracked, respect_invariants):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return True


def prove_goal_unreachable(env: Environment, goal: Goal, respect_invariants: bool = True) -> str | None:
    """Proof note if some conjunct is provably unreachable, else None.

    None means "no proof found", never "reachable". Reachability is proved
    constructively elsewhere, by a reference plan the checker accepts.
    """
    for lit in goal.literals:
        if _literal_unreachable(env, lit, respect_invariants):
            mode = "respecting invariants" if respect_invariants else "ignoring invariants"
            return f"{lit} is unreachable ({mode}, over-approximating abstraction)"
    return None


def classify_infeasibility(env: Environment, goal: Goal) -> str | None:
    """"unreachable", "constraint", or None when neither is provable."""
    if prove_goal_unreachable(env, goal, respect_invariants=False) is not None:
        return "unreachable"
    if prove_goal_unreachable(env, goal, respect_invariants=True) is not None:
        return "constraint"
    return None
