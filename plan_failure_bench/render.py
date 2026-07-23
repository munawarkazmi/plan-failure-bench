"""Deterministic rendering of an environment into the text shown to the model.

This is part of the fixed-disclosure contract: every model sees exactly this
text for a given environment, including every invariant verbatim. Ordering is
sorted or author-ordered, never set-ordered, so the output is reproducible.
"""

from __future__ import annotations

from .schema import Environment


def render_environment(env: Environment) -> str:
    lines: list[str] = []
    lines.append(f"Environment: {env.name}")
    lines.append("")
    lines.append("Rooms: " + ", ".join(sorted(env.rooms)))
    lines.append("")
    lines.append("Connections:")
    for door in sorted(env.doors, key=lambda d: d.name):
        a, b = door.connects
        lines.append(f"- {door.name} connects {a} and {b} ({door.state})")
    doorless = sorted(r for r in env.rooms if not env.adjacency(r))
    for room in doorless:
        lines.append(f"- {room} has no doors")
    lines.append("")
    lines.append("Items:")
    for item in sorted(env.items, key=lambda i: i.name):
        props = ", ".join(sorted(item.properties)) if item.properties else "none"
        mobility = "Portable." if item.portable else "Fixed in place."
        lines.append(f"- {item.name}: {item.description} (category: {item.category}; properties: {props}). In the {item.room}. {mobility}")
    lines.append("")
    lines.append(f"You are a mobile robot currently in the {env.robot_room}.")
    lines.append("Your gripper is empty and holds at most one item at a time.")
    lines.append("Actions available to you: " + ", ".join(sorted(env.capabilities)) + ".")
    if env.invariants:
        lines.append("")
        lines.append("Constraints (these must hold at every moment, not just at the end):")
        for inv in env.invariants:
            lines.append(f"- {inv.text}")
    return "\n".join(lines) + "\n"
