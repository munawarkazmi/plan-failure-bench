"""Seed instruction schema and loader.

Each seed carries a natural language instruction, a planted label, and the
machinery that makes its ground truth decidable: a structured goal, a
reference plan for feasible goals, a decoy plan documenting the intended
trap, capability grants for missing_capability seeds, and alternative goal
bindings for ambiguous seeds.

The loader enforces structural rules per label (which fields a seed of
each label must and must not have). The semantic proof obligations (does
the reference plan actually validate, is the infeasibility actually
provable) are enforced by tests/test_seeds.py, so the whole suite is
re-proved on every test run.

A null goal is permitted only for seeds whose expected response is an
infeasible terminal and whose task cannot be expressed as state literals
at all: the target object does not exist, or the requested effect is
outside the world model. Plans emitted against such seeds are judged for
executability only; the metrics layer scores them as non-detections.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .dsl import Step, parse_response
from .schema import (
    DoorIs,
    GLOBAL_ACTIONS,
    Goal,
    Holding,
    INFEASIBLE_REASONS,
    ItemIn,
    RobotAt,
    SchemaError,
)

PLANTED_LABELS = (
    "valid",
    "unreachable_goal",
    "missing_capability",
    "ambiguous_referent",
    "precondition_trap",
    "sequencing_trap",
    "constraint_trap",
)

_SEED_KEYS = {
    "id",
    "environment",
    "instruction",
    "label",
    "goal",
    "expected_terminal",
    "reference_plan",
    "decoy_plan",
    "decoy_verdict",
    "capability_reference_plan",
    "granted_capability",
    "alternatives",
    "notes",
}
_REQUIRED_KEYS = {"id", "environment", "instruction", "label", "goal", "expected_terminal", "notes"}
_LABEL_REASONS = {
    "unreachable_goal": "unreachable",
    "missing_capability": "missing_capability",
}


@dataclass(frozen=True)
class Alternative:
    binding: str
    goal: Goal
    reference_plan: tuple[Step, ...]


@dataclass(frozen=True)
class Seed:
    id: str
    environment: str
    instruction: str
    label: str
    goal: Goal | None
    expected_terminal: tuple | None  # ("infeasible", reason) or ("clarify",)
    reference_plan: tuple[Step, ...] | None
    decoy_plan: tuple[Step, ...] | None
    decoy_verdict: str | None
    capability_reference_plan: tuple[Step, ...] | None
    granted_capability: str | None
    alternatives: tuple[Alternative, ...]
    notes: str

    @property
    def clarify_candidates(self) -> tuple[str, ...]:
        return tuple(sorted(a.binding for a in self.alternatives))


def steps_to_text(steps: tuple[Step, ...]) -> str:
    return json.dumps({"plan": [{"action": s.action, "args": list(s.args)} for s in steps]})


def parse_goal(literals: object, where: str) -> Goal:
    if not isinstance(literals, list) or not literals:
        raise SchemaError(f"{where}: goal must be a non-empty list of literals, got {literals!r}")
    parsed = []
    for k, lit in enumerate(literals):
        if not isinstance(lit, dict) or "kind" not in lit:
            raise SchemaError(f"{where}[{k}]: expected an object with a 'kind' key, got {lit!r}")
        kind = lit["kind"]
        try:
            if kind == "item_in":
                parsed.append(ItemIn(item=lit["item"], room=lit["room"]))
            elif kind == "robot_at":
                parsed.append(RobotAt(room=lit["room"]))
            elif kind == "door_is":
                parsed.append(DoorIs(door=lit["door"], state=lit["state"]))
            elif kind == "holding":
                parsed.append(Holding(item=lit["item"]))
            else:
                raise SchemaError(f"{where}[{k}]: unknown literal kind {kind!r}")
        except KeyError as exc:
            raise SchemaError(f"{where}[{k}]: literal of kind {kind!r} is missing key {exc}") from exc
    return Goal(tuple(parsed))


def _parse_plan(raw: object, where: str) -> tuple[Step, ...]:
    if not isinstance(raw, list):
        raise SchemaError(f"{where}: expected a list of steps, got {raw!r}")
    response = parse_response(json.dumps({"plan": raw}))
    return response.steps


def _parse_terminal(raw: object, where: str) -> tuple | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or "type" not in raw:
        raise SchemaError(f"{where}: expected null or an object with a 'type' key, got {raw!r}")
    if raw["type"] == "infeasible":
        if set(raw.keys()) != {"type", "reason"} or raw["reason"] not in INFEASIBLE_REASONS:
            raise SchemaError(f"{where}: infeasible terminal needs a reason from {INFEASIBLE_REASONS}, got {raw!r}")
        return ("infeasible", raw["reason"])
    if raw["type"] == "clarify":
        if set(raw.keys()) != {"type"}:
            raise SchemaError(f"{where}: clarify terminal takes no other keys, candidates come from alternatives")
        return ("clarify",)
    raise SchemaError(f"{where}: unknown terminal type {raw['type']!r}")


def _structural_problems(seed: Seed) -> list[str]:
    p: list[str] = []
    label = seed.label

    if label == "valid":
        if seed.expected_terminal is not None:
            p.append("valid seeds must not expect a terminal")
        if seed.goal is None or seed.reference_plan is None:
            p.append("valid seeds need a goal and a reference plan")
        if seed.decoy_plan or seed.capability_reference_plan or seed.alternatives:
            p.append("valid seeds must not carry decoy, capability, or alternative fields")

    elif label == "ambiguous_referent":
        if seed.expected_terminal != ("clarify",):
            p.append("ambiguous seeds must expect a clarify terminal")
        if seed.goal is not None:
            p.append("ambiguous seeds have no single goal, only alternatives")
        if len(seed.alternatives) < 2:
            p.append("ambiguous seeds need at least two alternatives")

    elif label in ("unreachable_goal", "missing_capability"):
        if seed.expected_terminal != ("infeasible", _LABEL_REASONS[label]):
            p.append(f"{label} seeds must expect infeasible({_LABEL_REASONS[label]})")
        if seed.reference_plan is not None or seed.decoy_plan is not None or seed.alternatives:
            p.append(f"{label} seeds must not carry reference, decoy, or alternative plans")
        if label == "missing_capability" and seed.goal is not None:
            if seed.capability_reference_plan is None or seed.granted_capability is None:
                p.append("goal-bearing missing_capability seeds need a capability_reference_plan and granted_capability")
        if label == "unreachable_goal" and seed.capability_reference_plan is not None:
            p.append("unreachable_goal seeds must not have a capability plan, no grant makes them feasible")

    elif label in ("precondition_trap", "sequencing_trap"):
        if seed.expected_terminal is not None:
            p.append(f"{label} seeds have feasible goals and must not expect a terminal")
        if seed.goal is None or seed.reference_plan is None or seed.decoy_plan is None or seed.decoy_verdict is None:
            p.append(f"{label} seeds need a goal, a reference plan, and a decoy plan with its verdict")

    elif label == "constraint_trap":
        feasible_shape = seed.expected_terminal is None and seed.reference_plan is not None and seed.decoy_verdict == "constraint_violation"
        infeasible_shape = seed.expected_terminal == ("infeasible", "constraint") and seed.reference_plan is None and seed.decoy_plan is None
        if not (feasible_shape or infeasible_shape):
            p.append(
                "constraint_trap seeds are either feasible (reference plan plus a decoy whose verdict is "
                "constraint_violation) or infeasible (expect infeasible(constraint), no plans)"
            )
        if seed.goal is None:
            p.append("constraint_trap seeds need a goal")

    if seed.granted_capability is not None:
        if seed.granted_capability not in GLOBAL_ACTIONS:
            p.append(f"granted_capability {seed.granted_capability!r} is not in the global vocabulary")
        if label != "missing_capability":
            p.append("only missing_capability seeds may grant a capability")
    if (seed.decoy_plan is None) != (seed.decoy_verdict is None):
        p.append("decoy_plan and decoy_verdict must appear together")
    if seed.goal is None and seed.expected_terminal is not None and seed.expected_terminal[0] != "infeasible" and label != "ambiguous_referent":
        p.append("a null goal is only permitted for infeasible or ambiguous seeds")
    return p


def _parse_seed(raw: object, index: int) -> Seed:
    where = f"seeds[{index}]"
    if not isinstance(raw, dict):
        raise SchemaError(f"{where}: expected an object, got {raw!r}")
    missing = sorted(_REQUIRED_KEYS - raw.keys())
    unknown = sorted(raw.keys() - _SEED_KEYS)
    if missing or unknown:
        raise SchemaError(f"{where}: missing keys {missing}, unknown keys {unknown}")
    if raw["label"] not in PLANTED_LABELS:
        raise SchemaError(f"{where}: unknown label {raw['label']!r}, expected one of {PLANTED_LABELS}")

    alternatives = []
    for k, alt in enumerate(raw.get("alternatives", [])):
        alt_where = f"{where}.alternatives[{k}]"
        if not isinstance(alt, dict) or set(alt.keys()) != {"binding", "goal", "reference_plan"}:
            raise SchemaError(f"{alt_where}: expected exactly binding, goal, and reference_plan")
        alternatives.append(
            Alternative(
                binding=alt["binding"],
                goal=parse_goal(alt["goal"], f"{alt_where}.goal"),
                reference_plan=_parse_plan(alt["reference_plan"], f"{alt_where}.reference_plan"),
            )
        )

    seed = Seed(
        id=raw["id"],
        environment=raw["environment"],
        instruction=raw["instruction"],
        label=raw["label"],
        goal=parse_goal(raw["goal"], f"{where}.goal") if raw["goal"] is not None else None,
        expected_terminal=_parse_terminal(raw["expected_terminal"], f"{where}.expected_terminal"),
        reference_plan=_parse_plan(raw["reference_plan"], f"{where}.reference_plan") if raw.get("reference_plan") is not None else None,
        decoy_plan=_parse_plan(raw["decoy_plan"], f"{where}.decoy_plan") if raw.get("decoy_plan") is not None else None,
        decoy_verdict=raw.get("decoy_verdict"),
        capability_reference_plan=_parse_plan(raw["capability_reference_plan"], f"{where}.capability_reference_plan")
        if raw.get("capability_reference_plan") is not None
        else None,
        granted_capability=raw.get("granted_capability"),
        alternatives=tuple(alternatives),
        notes=raw["notes"],
    )
    problems = _structural_problems(seed)
    if problems:
        raise SchemaError(f"{where} ({seed.id}):\n" + "\n".join(f"- {x}" for x in problems))
    return seed


def load_seeds(path: str | Path) -> tuple[Seed, ...]:
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SchemaError(f"{path}: top level must be a list of seeds")
    seeds = tuple(_parse_seed(s, i) for i, s in enumerate(raw))
    ids = [s.id for s in seeds]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise SchemaError(f"{path}: duplicate seed ids {duplicates}")
    return seeds
