"""Independent plan validation via pyperplan's PDDL grounder.

This is the second opinion on the checker. pyperplan parses and grounds
the compiled PDDL with its own semantics; we then walk the plan over its
grounded operators. None of our checker's simulation code is involved, so
a bug there cannot hide here.

Grounding is called with both pruning flags off: static-fact removal and
irrelevant-operator removal are planner optimisations, and the second
would delete operators a wandering-but-executable plan legitimately uses,
producing false disagreements.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from pyperplan.grounding import ground
from pyperplan.pddl.parser import Parser


@dataclass(frozen=True)
class PddlVerdict:
    status: str  # "valid" | "inapplicable" | "unknown_operator" | "goal_unsatisfied"
    step_index: int | None = None


def ground_task(domain_text: str, problem_text: str):
    """Parse and ground once; the returned task can validate many plans."""
    with tempfile.TemporaryDirectory() as tmp:
        domain_path = Path(tmp) / "domain.pddl"
        problem_path = Path(tmp) / "problem.pddl"
        domain_path.write_text(domain_text, encoding="utf-8")
        problem_path.write_text(problem_text, encoding="utf-8")
        parser = Parser(str(domain_path), str(problem_path))
        domain = parser.parse_domain()
        problem = parser.parse_problem(domain)
    return ground(problem, remove_statics_from_initial_state=False, remove_irrelevant_operators=False)


def run_plan(task, action_names: tuple[str, ...]) -> PddlVerdict:
    operators = {op.name: op for op in task.operators}
    state = task.initial_state
    for k, name in enumerate(action_names):
        op = operators.get(name)
        if op is None:
            # Grounding only omits an operator when its static preconditions
            # (door-room adjacency, sorts) can never hold, so the step could
            # never have been applicable.
            return PddlVerdict("unknown_operator", k)
        if not op.applicable(state):
            return PddlVerdict("inapplicable", k)
        state = op.apply(state)
    if task.goal_reached(state):
        return PddlVerdict("valid")
    return PddlVerdict("goal_unsatisfied")
