"""The LLM-facing action DSL.

A model response is a single JSON object in exactly one of three forms:

    {"plan": [{"action": "goto", "args": ["kitchen"]}, ...]}
    {"infeasible": {"reason": "unreachable"}}
    {"clarify": {"candidates": ["cup_red", "cup_blue"]}}

Parsing policy, fixed and identical for every model: the response must be
the JSON object alone, optionally wrapped in a single markdown code fence.
Anything else is malformed. Leniency beyond fence stripping would make the
format-compliance metric depend on how forgiving the extractor happens to
be, which would quietly vary by model.

Arity is checked here for actions in the global vocabulary. A step naming
an action outside the vocabulary parses successfully; judging it is the
checker's job, because an invented action is a planning failure
(fabricated affordance), not a format failure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Union

from .schema import GLOBAL_ACTIONS, INFEASIBLE_REASONS

ARITY = {"goto": 1, "open": 1, "close": 1, "pick": 1, "place": 1, "unlock": 1}
assert set(ARITY) == set(GLOBAL_ACTIONS)


class DslError(ValueError):
    """Raised when a response is malformed. The message is the diagnosis."""


@dataclass(frozen=True)
class Step:
    action: str
    args: tuple[str, ...]


@dataclass(frozen=True)
class PlanResponse:
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class InfeasibleResponse:
    reason: str


@dataclass(frozen=True)
class ClarifyResponse:
    candidates: tuple[str, ...]


Response = Union[PlanResponse, InfeasibleResponse, ClarifyResponse]


def _strip_fence(text: str) -> str:
    text = text.strip()
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1])
    return text


def _parse_step(obj: object, index: int) -> Step:
    where = f"plan[{index}]"
    if not isinstance(obj, dict):
        raise DslError(f"{where}: expected an object, got {obj!r}")
    if set(obj.keys()) != {"action", "args"}:
        raise DslError(f"{where}: expected exactly the keys 'action' and 'args', got {sorted(obj.keys())}")
    action = obj["action"]
    args = obj["args"]
    if not isinstance(action, str) or not action:
        raise DslError(f"{where}.action: expected a non-empty string, got {action!r}")
    if not isinstance(args, list) or not all(isinstance(a, str) and a for a in args):
        raise DslError(f"{where}.args: expected a list of non-empty strings, got {args!r}")
    if action in ARITY and len(args) != ARITY[action]:
        raise DslError(f"{where}: {action} takes {ARITY[action]} argument(s), got {len(args)}")
    return Step(action=action, args=tuple(args))


def parse_response(text: str) -> Response:
    try:
        raw = json.loads(_strip_fence(text))
    except json.JSONDecodeError as exc:
        raise DslError(f"not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise DslError(f"top level must be an object, got {type(raw).__name__}")
    keys = set(raw.keys())

    if keys == {"plan"}:
        plan = raw["plan"]
        if not isinstance(plan, list):
            raise DslError(f"'plan' must be a list, got {plan!r}")
        return PlanResponse(steps=tuple(_parse_step(s, i) for i, s in enumerate(plan)))

    if keys == {"infeasible"}:
        body = raw["infeasible"]
        if not isinstance(body, dict) or set(body.keys()) != {"reason"}:
            raise DslError(f"'infeasible' must be an object with exactly the key 'reason', got {body!r}")
        reason = body["reason"]
        if reason not in INFEASIBLE_REASONS:
            raise DslError(f"infeasible reason must be one of {INFEASIBLE_REASONS}, got {reason!r}")
        return InfeasibleResponse(reason=reason)

    if keys == {"clarify"}:
        body = raw["clarify"]
        if not isinstance(body, dict) or set(body.keys()) != {"candidates"}:
            raise DslError(f"'clarify' must be an object with exactly the key 'candidates', got {body!r}")
        cands = body["candidates"]
        if not isinstance(cands, list) or not all(isinstance(c, str) and c for c in cands):
            raise DslError(f"'candidates' must be a list of non-empty strings, got {cands!r}")
        if len(cands) < 2:
            raise DslError("'candidates' must name at least two items; one candidate is not an ambiguity")
        if len(set(cands)) != len(cands):
            raise DslError(f"'candidates' contains duplicates: {cands!r}")
        return ClarifyResponse(candidates=tuple(cands))

    raise DslError(
        f"top level must have exactly one of the keys 'plan', 'infeasible', or 'clarify', got {sorted(keys)}"
    )
