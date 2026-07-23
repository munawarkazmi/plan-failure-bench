"""Tests for prompt assembly under the fixed disclosure contract."""

from pathlib import Path

import pytest

from plan_failure_bench.loader import load_environment
from plan_failure_bench.prompts import build_prompt, load_template, prompt_sha256, render_action_semantics

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV = load_environment(REPO_ROOT / "environments" / "house_01.json")
TEMPLATE = load_template(REPO_ROOT / "prompts" / "task_prompt.txt")


class TestBuildPrompt:
    def test_deterministic(self):
        a = build_prompt(TEMPLATE, ENV, "Go to the nursery.")
        b = build_prompt(TEMPLATE, ENV, "Go to the nursery.")
        assert a == b
        assert prompt_sha256(a) == prompt_sha256(b)

    def test_contains_instruction_and_environment(self):
        prompt = build_prompt(TEMPLATE, ENV, "Take the red cup to the bedroom.")
        assert "Take the red cup to the bedroom." in prompt
        assert "cellar has no doors" in prompt
        for inv in ENV.invariants:
            assert inv.text in prompt

    def test_terminals_disclosed_without_examples(self):
        prompt = build_prompt(TEMPLATE, ENV, "Go to the nursery.")
        assert '"infeasible"' in prompt
        assert '"clarify"' in prompt
        assert "missing_capability" in prompt
        # No worked example: the only place candidate items could appear is
        # the environment section, never inside the response format section.
        format_section = prompt.split("Respond with a single JSON object")[1]
        assert "cup_red" not in format_section.split("Instruction:")[0]

    def test_semantics_follow_capability_profile(self):
        prompt = build_prompt(TEMPLATE, ENV, "Go to the nursery.")
        assert "pick <item>" in prompt
        assert "unlock <door>" not in prompt

    def test_missing_token_rejected(self):
        with pytest.raises(ValueError, match="ENVIRONMENT"):
            build_prompt("no tokens here <<INSTRUCTION>> <<ACTION_SEMANTICS>>", ENV, "x")


class TestSemantics:
    def test_one_line_per_capability(self):
        text = render_action_semantics(ENV)
        assert len(text.splitlines()) == len(ENV.capabilities)
