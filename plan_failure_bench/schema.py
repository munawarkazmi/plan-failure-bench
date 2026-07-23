"""Typed world model.

Design contract, agreed 2026-07-23:
- State is a finite set of ground atoms over a fixed object universe.
  No numerics anywhere, so the state space is finite and reachability
  questions are decidable.
- Invariants are per-state predicates. Their `text` field is shown to the
  model verbatim in the environment description, so constraint traps test
  planning, not telepathy.
- Names of rooms, doors, and items share one namespace and must be unique,
  because DSL action arguments refer to them by bare name.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Union

DOOR_STATES = ("open", "closed", "locked")

CORE_ACTIONS = ("goto", "open", "close", "pick", "place")
OPTIONAL_ACTIONS = ("unlock",)
GLOBAL_ACTIONS = CORE_ACTIONS + OPTIONAL_ACTIONS
TERMINAL_ACTIONS = ("infeasible", "clarify")
INFEASIBLE_REASONS = ("unreachable", "missing_capability", "constraint")


class SchemaError(ValueError):
    """Raised when an environment definition is malformed or inconsistent."""


@dataclass(frozen=True)
class Door:
    name: str
    connects: tuple[str, str]
    state: str


@dataclass(frozen=True)
class Item:
    name: str
    category: str
    properties: frozenset[str]
    room: str
    portable: bool
    description: str


@dataclass(frozen=True)
class NeverEnter:
    """The robot must never be in `room`, in any state."""

    KIND: ClassVar[str] = "never_enter"
    room: str
    text: str

    def holds(self, state: "State", env: "Environment") -> bool:
        return state.robot_room != self.room


@dataclass(frozen=True)
class NeverHoldIn:
    """The robot must never be in `room` while holding an item with `item_property`."""

    KIND: ClassVar[str] = "never_hold_in"
    item_property: str
    room: str
    text: str

    def holds(self, state: "State", env: "Environment") -> bool:
        if state.holding is None or state.robot_room != self.room:
            return True
        return self.item_property not in env.item(state.holding).properties


Invariant = Union[NeverEnter, NeverHoldIn]


@dataclass(frozen=True)
class Environment:
    name: str
    rooms: tuple[str, ...]
    doors: tuple[Door, ...]
    items: tuple[Item, ...]
    robot_room: str
    capabilities: frozenset[str]
    invariants: tuple[Invariant, ...]

    def door(self, name: str) -> Door:
        for d in self.doors:
            if d.name == name:
                return d
        raise KeyError(f"no door named {name!r} in environment {self.name!r}")

    def item(self, name: str) -> Item:
        for i in self.items:
            if i.name == name:
                return i
        raise KeyError(f"no item named {name!r} in environment {self.name!r}")

    def adjacency(self, room: str) -> tuple[tuple[str, str], ...]:
        """Doors touching `room`, as (door_name, other_room) pairs, sorted."""
        out = []
        for d in self.doors:
            if room == d.connects[0]:
                out.append((d.name, d.connects[1]))
            elif room == d.connects[1]:
                out.append((d.name, d.connects[0]))
        return tuple(sorted(out))

    def validate(self) -> list[str]:
        """Return every consistency problem found. Empty list means valid."""
        problems: list[str] = []
        rooms = set(self.rooms)

        names = list(self.rooms) + [d.name for d in self.doors] + [i.name for i in self.items]
        for name in sorted({n for n in names if names.count(n) > 1}):
            problems.append(f"name {name!r} is used more than once (rooms, doors, and items share one namespace)")

        for d in self.doors:
            if d.state not in DOOR_STATES:
                problems.append(f"door {d.name!r} has unknown state {d.state!r}, expected one of {DOOR_STATES}")
            if d.connects[0] == d.connects[1]:
                problems.append(f"door {d.name!r} connects room {d.connects[0]!r} to itself")
            for r in d.connects:
                if r not in rooms:
                    problems.append(f"door {d.name!r} connects unknown room {r!r}")

        for i in self.items:
            if i.room not in rooms:
                problems.append(f"item {i.name!r} is in unknown room {i.room!r}")
            if not i.category:
                problems.append(f"item {i.name!r} has an empty category")
            if not i.description:
                problems.append(f"item {i.name!r} has an empty description")

        if self.robot_room not in rooms:
            problems.append(f"robot starts in unknown room {self.robot_room!r}")
        for c in sorted(self.capabilities):
            if c not in GLOBAL_ACTIONS:
                problems.append(f"capability {c!r} is not in the global action vocabulary {GLOBAL_ACTIONS}")
        if "goto" not in self.capabilities:
            problems.append("capabilities must include 'goto'; a robot that cannot move defeats every instruction at once")

        all_properties = {p for i in self.items for p in i.properties}
        for inv in self.invariants:
            if not inv.text:
                problems.append(f"invariant {inv} has empty text; constraints must be stated to the model verbatim")
            if inv.room not in rooms:
                problems.append(f"invariant {inv} names unknown room {inv.room!r}")
            if isinstance(inv, NeverHoldIn) and inv.item_property not in all_properties:
                problems.append(
                    f"invariant {inv} names property {inv.item_property!r} carried by no item; dead constraints are not allowed"
                )
        return problems


@dataclass(frozen=True)
class State:
    """One world state. Frozen and hashable so search can use it as a set key.

    A held item appears in `holding` and is absent from `item_rooms`.
    """

    robot_room: str
    holding: str | None
    door_states: tuple[tuple[str, str], ...]
    item_rooms: tuple[tuple[str, str], ...]

    @staticmethod
    def initial(env: Environment) -> "State":
        return State(
            robot_room=env.robot_room,
            holding=None,
            door_states=tuple(sorted((d.name, d.state) for d in env.doors)),
            item_rooms=tuple(sorted((i.name, i.room) for i in env.items)),
        )

    def door_state(self, name: str) -> str:
        for n, s in self.door_states:
            if n == name:
                return s
        raise KeyError(f"no door named {name!r} in state")

    def item_room(self, name: str) -> str | None:
        """Room the item is in, or None if it is being held."""
        if name == self.holding:
            return None
        for n, r in self.item_rooms:
            if n == name:
                return r
        raise KeyError(f"no item named {name!r} in state")


@dataclass(frozen=True)
class ItemIn:
    item: str
    room: str

    def satisfied(self, state: State) -> bool:
        return state.item_room(self.item) == self.room


@dataclass(frozen=True)
class RobotAt:
    room: str

    def satisfied(self, state: State) -> bool:
        return state.robot_room == self.room


@dataclass(frozen=True)
class DoorIs:
    door: str
    state: str

    def satisfied(self, state: State) -> bool:
        return state.door_state(self.door) == self.state


@dataclass(frozen=True)
class Holding:
    item: str

    def satisfied(self, state: State) -> bool:
        return state.holding == self.item


GoalLiteral = Union[ItemIn, RobotAt, DoorIs, Holding]


@dataclass(frozen=True)
class Goal:
    """Conjunction of literals over the final state."""

    literals: tuple[GoalLiteral, ...]

    def satisfied(self, state: State) -> bool:
        return all(lit.satisfied(state) for lit in self.literals)

    def satisfied_count(self, state: State) -> int:
        """How many conjuncts hold. Feeds the `partial` flag on goal_not_achieved."""
        return sum(1 for lit in self.literals if lit.satisfied(state))
