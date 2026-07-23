"""Strict JSON loader for environment files.

Strict means: unknown keys are errors, missing keys are errors, and every
consistency problem found by Environment.validate() is reported at once.
Environment files are reviewable data; silent tolerance here would let an
authoring mistake corrupt ground truth downstream.
"""

from __future__ import annotations

import json
from pathlib import Path

from .schema import (
    Door,
    Environment,
    Invariant,
    Item,
    NeverEnter,
    NeverHoldIn,
    SchemaError,
)

_ENV_KEYS = {"name", "rooms", "doors", "items", "robot", "invariants"}
_DOOR_KEYS = {"name", "connects", "state"}
_ITEM_KEYS = {"name", "category", "properties", "room", "portable", "description"}
_ROBOT_KEYS = {"room", "capabilities"}
_INVARIANT_KINDS = {NeverEnter.KIND, NeverHoldIn.KIND}


def _require_keys(obj: dict, required: set[str], allowed: set[str], where: str) -> None:
    missing = sorted(required - obj.keys())
    unknown = sorted(obj.keys() - allowed)
    if missing:
        raise SchemaError(f"{where}: missing keys {missing}")
    if unknown:
        raise SchemaError(f"{where}: unknown keys {unknown}")


def _require_str(value: object, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise SchemaError(f"{where}: expected a non-empty string, got {value!r}")
    return value


def _require_str_list(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise SchemaError(f"{where}: expected a list of strings, got {value!r}")
    return value


def _parse_door(obj: object, index: int) -> Door:
    where = f"doors[{index}]"
    if not isinstance(obj, dict):
        raise SchemaError(f"{where}: expected an object, got {obj!r}")
    _require_keys(obj, _DOOR_KEYS, _DOOR_KEYS, where)
    connects = _require_str_list(obj["connects"], f"{where}.connects")
    if len(connects) != 2:
        raise SchemaError(f"{where}.connects: expected exactly two rooms, got {connects!r}")
    return Door(
        name=_require_str(obj["name"], f"{where}.name"),
        connects=(connects[0], connects[1]),
        state=_require_str(obj["state"], f"{where}.state"),
    )


def _parse_item(obj: object, index: int) -> Item:
    where = f"items[{index}]"
    if not isinstance(obj, dict):
        raise SchemaError(f"{where}: expected an object, got {obj!r}")
    _require_keys(obj, _ITEM_KEYS - {"description"}, _ITEM_KEYS, where)
    if not isinstance(obj["portable"], bool):
        raise SchemaError(f"{where}.portable: expected true or false, got {obj['portable']!r}")
    name = _require_str(obj["name"], f"{where}.name")
    category = _require_str(obj["category"], f"{where}.category")
    return Item(
        name=name,
        category=category,
        properties=frozenset(_require_str_list(obj["properties"], f"{where}.properties")),
        room=_require_str(obj["room"], f"{where}.room"),
        portable=obj["portable"],
        description=_require_str(obj.get("description", f"a {category}"), f"{where}.description"),
    )


def _parse_invariant(obj: object, index: int) -> Invariant:
    where = f"invariants[{index}]"
    if not isinstance(obj, dict):
        raise SchemaError(f"{where}: expected an object, got {obj!r}")
    kind = obj.get("kind")
    if kind == NeverEnter.KIND:
        _require_keys(obj, {"kind", "room", "text"}, {"kind", "room", "text"}, where)
        return NeverEnter(
            room=_require_str(obj["room"], f"{where}.room"),
            text=_require_str(obj["text"], f"{where}.text"),
        )
    if kind == NeverHoldIn.KIND:
        keys = {"kind", "property", "room", "text"}
        _require_keys(obj, keys, keys, where)
        return NeverHoldIn(
            item_property=_require_str(obj["property"], f"{where}.property"),
            room=_require_str(obj["room"], f"{where}.room"),
            text=_require_str(obj["text"], f"{where}.text"),
        )
    raise SchemaError(f"{where}: unknown kind {kind!r}, expected one of {sorted(_INVARIANT_KINDS)}")


def load_environment(path: str | Path) -> Environment:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchemaError(f"{path}: not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise SchemaError(f"{path}: top level must be an object")
    _require_keys(raw, _ENV_KEYS, _ENV_KEYS, str(path))

    robot = raw["robot"]
    if not isinstance(robot, dict):
        raise SchemaError("robot: expected an object")
    _require_keys(robot, _ROBOT_KEYS, _ROBOT_KEYS, "robot")

    doors = raw["doors"]
    items = raw["items"]
    invariants = raw["invariants"]
    for field, value in (("doors", doors), ("items", items), ("invariants", invariants)):
        if not isinstance(value, list):
            raise SchemaError(f"{field}: expected a list, got {value!r}")

    env = Environment(
        name=_require_str(raw["name"], "name"),
        rooms=tuple(_require_str_list(raw["rooms"], "rooms")),
        doors=tuple(_parse_door(d, i) for i, d in enumerate(doors)),
        items=tuple(_parse_item(it, i) for i, it in enumerate(items)),
        robot_room=_require_str(robot["room"], "robot.room"),
        capabilities=frozenset(_require_str_list(robot["capabilities"], "robot.capabilities")),
        invariants=tuple(_parse_invariant(inv, i) for i, inv in enumerate(invariants)),
    )
    problems = env.validate()
    if problems:
        raise SchemaError(f"{path} is inconsistent:\n" + "\n".join(f"- {p}" for p in problems))
    return env
