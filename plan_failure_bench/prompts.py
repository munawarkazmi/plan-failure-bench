"""Prompt assembly under the fixed disclosure contract.

The template in prompts/task_prompt.txt is the exact text every model sees,
with three placeholder tokens filled deterministically. It names both
terminals with one line of semantics each and shows the JSON response
shapes, but contains no worked examples of using a terminal. The sha256 of
every assembled prompt is recorded in the results, so a result produced
under a drifted prompt is detectable.

Action semantics are disclosed only for actions in the robot's capability
profile. Describing unlock to a robot that cannot unlock would bait
fabricated affordance responses rather than measure them.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .schema import Environment
from .render import render_environment

# Each line states its effect in terms of state words rather than relying on
# the English meaning of the action verb. Under the obfuscated condition the
# action and state names are renamed, and only effect-explicit phrasing keeps
# the disclosed semantics complete after renaming.
_SEMANTICS = {
    "goto": "goto <room>: move to an adjacent room. There must be an open door connecting your current room to the target room. You can only move one room at a time.",
    "open": "open <door>: change a closed door so that it is open. You must be in one of the rooms the door connects, and your gripper must be empty.",
    "close": "close <door>: change a door that is open so that it is closed. You must be in one of the rooms the door connects, and your gripper must be empty.",
    "unlock": "unlock <door>: change a locked door so that it is closed. You must be in one of the rooms the door connects, and your gripper must be empty.",
    "pick": "pick <item>: move a portable item from your current room into your gripper. Your gripper must be empty.",
    "place": "place <item>: move the item you are holding from your gripper into your current room.",
}


def render_action_semantics(env: Environment) -> str:
    return "\n".join(f"- {_SEMANTICS[a]}" for a in sorted(env.capabilities))


def load_template(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def build_prompt(template: str, env: Environment, instruction: str) -> str:
    for token in ("<<ENVIRONMENT>>", "<<ACTION_SEMANTICS>>", "<<INSTRUCTION>>"):
        if token not in template:
            raise ValueError(f"prompt template is missing the token {token}")
    return (
        template.replace("<<ENVIRONMENT>>", render_environment(env).rstrip("\n"))
        .replace("<<ACTION_SEMANTICS>>", render_action_semantics(env))
        .replace("<<INSTRUCTION>>", instruction)
    )


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
