"""Tests for the obfuscated condition.

The two properties that make the condition trustworthy are proved here:
no semantic leak (no canonical content word survives into any obfuscated
prompt) and semantic equivalence (a model answering correctly in the
obfuscated vocabulary scores identically to one answering in the plain
vocabulary, seed by seed).
"""

import json
import re
from pathlib import Path

import pytest

from plan_failure_bench.instructions import load_seeds, steps_to_text
from plan_failure_bench.loader import load_environment
from plan_failure_bench.metrics import detection_report
from plan_failure_bench.obfuscation import build_obfuscation, load_lexicon, load_obfuscation
from plan_failure_bench.prompts import build_prompt, load_template
from plan_failure_bench.runner import run_suite

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV = load_environment(REPO_ROOT / "environments" / "house_01.json")
SEEDS = load_seeds(REPO_ROOT / "instructions" / "seeds_house_01.json")
TEMPLATE = load_template(REPO_ROOT / "prompts" / "task_prompt.txt")
LEXICON = load_lexicon(REPO_ROOT / "environments" / "house_01.obfuscation.json")
OBF = build_obfuscation(ENV, LEXICON)


def canonical_response(seed):
    if seed.expected_terminal is None:
        return steps_to_text(seed.reference_plan)
    if seed.expected_terminal[0] == "infeasible":
        return json.dumps({"infeasible": {"reason": seed.expected_terminal[1]}})
    return json.dumps({"clarify": {"candidates": list(seed.clarify_candidates)}})


class TestMapping:
    def test_deterministic(self):
        again = build_obfuscation(ENV, LEXICON)
        assert again == OBF

    def test_bijective_and_disjoint(self):
        sources = [w for w, _ in OBF.token_map]
        targets = [t for _, t in OBF.token_map]
        assert len(set(sources)) == len(sources)
        assert len(set(targets)) == len(targets)
        assert not set(sources) & set(targets)

    def test_loader_helper(self):
        assert load_obfuscation(ENV, REPO_ROOT / "environments") == OBF

    def test_tokens_pairwise_distinct(self):
        from plan_failure_bench.obfuscation import _MIN_TOKEN_DISTANCE, _levenshtein

        stems = {w: t for w, t in OBF.token_map}
        base = [t for w, t in OBF.token_map if not (w.endswith("s") and w[:-1] in stems)]
        for i, a in enumerate(base):
            for b in base[i + 1 :]:
                assert _levenshtein(a, b) >= _MIN_TOKEN_DISTANCE, (a, b)

    def test_version_recorded_in_records(self):
        from plan_failure_bench.runner import run_suite

        def refuser(prompt, seed):
            return '{"infeasible": {"reason": "unreachable"}}'

        obf_records = run_suite(
            SEEDS, {"house_01": ENV}, TEMPLATE, refuser, "m", "obfuscated", obfuscations={"house_01": OBF}
        )
        plain_records = run_suite(SEEDS, {"house_01": ENV}, TEMPLATE, refuser, "m", "plain")
        assert all(r["obfuscation_version"] == OBF.version for r in obf_records)
        assert all(r["obfuscation_version"] is None for r in plain_records)


class TestNoSemanticLeak:
    LEAKABLE = sorted({w for w, _ in OBF.token_map} | set(OBF.leak_words))

    @pytest.mark.parametrize("seed", SEEDS, ids=lambda s: s.id)
    def test_prompt_is_leak_free(self, seed):
        prompt = OBF.apply(build_prompt(TEMPLATE, ENV, seed.instruction))
        for word in self.LEAKABLE:
            assert not re.search(rf"\b{re.escape(word)}\b", prompt, re.IGNORECASE), (
                seed.id,
                word,
            )

    def test_invariant_texts_gone(self):
        prompt = OBF.apply(build_prompt(TEMPLATE, ENV, "x."))
        for inv in ENV.invariants:
            assert inv.text not in prompt

    def test_states_renamed_consistently(self):
        prompt = OBF.apply(build_prompt(TEMPLATE, ENV, "x."))
        locked = OBF.token_for("locked")
        assert f"({locked})" in prompt
        assert f"({OBF.token_for('open')})" in prompt
        # The semantics table uses the same renamed state words, so the
        # relational meaning survives even though the English words are gone.
        assert f"a {OBF.token_for('closed')} door so that it is {OBF.token_for('open')}" in prompt

    def test_structure_words_retained(self):
        prompt = OBF.apply(build_prompt(TEMPLATE, ENV, "x."))
        for word in ("Rooms:", "Connections:", "Items:", "gripper", "has no doors"):
            assert word in prompt


class TestRoundTrip:
    def all_plans(self):
        for seed in SEEDS:
            for plan in (seed.reference_plan, seed.decoy_plan, seed.capability_reference_plan):
                if plan is not None:
                    yield seed.id, steps_to_text(plan)
            for alt in seed.alternatives:
                yield seed.id, steps_to_text(alt.reference_plan)
            yield seed.id, canonical_response(seed)

    def test_apply_then_invert_is_identity(self):
        for seed_id, text in self.all_plans():
            assert OBF.invert(OBF.apply(text)) == text, seed_id

    def test_apply_actually_changes_plans(self):
        text = steps_to_text(SEEDS[0].reference_plan)
        assert OBF.apply(text) != text


class TestEndToEndEquivalence:
    def test_obfuscated_oracle_scores_identically_to_plain_oracle(self):
        def plain_oracle(prompt, seed):
            return canonical_response(seed)

        def obfuscated_oracle(prompt, seed):
            # A model that understands the obfuscated world perfectly
            # answers in the obfuscated vocabulary.
            return OBF.apply(canonical_response(seed))

        plain = run_suite(SEEDS, {"house_01": ENV}, TEMPLATE, plain_oracle, "oracle", "plain")
        obfuscated = run_suite(
            SEEDS,
            {"house_01": ENV},
            TEMPLATE,
            obfuscated_oracle,
            "oracle",
            "obfuscated",
            obfuscations={"house_01": OBF},
        )

        for p, o in zip(plain, obfuscated):
            assert p["seed_id"] == o["seed_id"]
            assert p["verdict"] == o["verdict"], p["seed_id"]
            assert p["per_alternative"] == o["per_alternative"], p["seed_id"]
            assert o["response_canonical"] == p["response"], p["seed_id"]
            assert o["prompt_sha256"] != p["prompt_sha256"], p["seed_id"]

        report = detection_report(obfuscated)
        assert report.false_positives == 0
        assert all(s.detected == s.total for s in report.per_label.values())
        assert all(s.reason_correct == s.total for s in report.per_label.values())

    def test_obfuscated_refuser_records_raw_and_canonical(self):
        def refuser(prompt, seed):
            return json.dumps({"infeasible": {"reason": "unreachable"}})

        records = run_suite(
            SEEDS,
            {"house_01": ENV},
            TEMPLATE,
            refuser,
            "refuser",
            "obfuscated",
            obfuscations={"house_01": OBF},
        )
        report = detection_report(records)
        assert report.false_positives == 17
        assert records[0]["response_canonical"] == records[0]["response"]
