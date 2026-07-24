"""Proof obligations for the seed suites.

Every planted label carries a mechanical obligation, and this module
re-proves all of them, for every registered suite, on each test run:

- valid, precondition_trap, sequencing_trap, feasible constraint_trap:
  the reference plan validates, and pyperplan agrees with the checker.
- decoy plans produce exactly the declared trap verdict.
- unreachable_goal: provably unreachable, and still unreachable with the
  full action vocabulary granted.
- missing_capability: provably unreachable under the robot's profile, not
  provable with the granted capability, and the capability plan validates
  in the augmented environment.
- infeasible constraint_trap: provably infeasible only because of an
  invariant.
- ambiguous_referent: at least two same category bindings, each with a
  validating reference plan and no infeasibility proof.

Plus suite wide hygiene: label counts, unique ids and instructions, and
no em or en dashes anywhere in the seed files.

Adding a suite means adding one Suite entry to SUITES; every obligation
then applies to it automatically.
"""

import dataclasses
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from plan_failure_bench.checker import check_response
from plan_failure_bench.differential import ground_task, run_plan
from plan_failure_bench.instructions import Seed, load_seeds, steps_to_text
from plan_failure_bench.loader import load_environment
from plan_failure_bench.pddl import compile_domain, compile_problem, translate_plan
from plan_failure_bench.reachability import classify_infeasibility
from plan_failure_bench.schema import GLOBAL_ACTIONS

REPO_ROOT = Path(__file__).resolve().parent.parent

# Both suites plant the same label distribution so the confusion matrix
# columns stay comparable across environments.
LABEL_DISTRIBUTION = {
    "valid": 9,
    "unreachable_goal": 4,
    "missing_capability": 3,
    "ambiguous_referent": 3,
    "precondition_trap": 4,
    "sequencing_trap": 3,
    "constraint_trap": 4,
}


@dataclass(frozen=True)
class Suite:
    environment: str
    seeds_path: Path
    # The one seed whose target object does not exist, with the words that
    # must name nothing in the environment.
    nonexistent_seed: str
    nonexistent_words: frozenset[str]
    # The one seed whose task verb is outside the action vocabulary, with
    # the verbs that must stay absent from it.
    inexpressible_seed: str
    inexpressible_verbs: frozenset[str]
    # Sorted reference plan lengths; intent documentation as much as a
    # test, so a drifting length profile fails loudly instead of silently.
    reference_plan_lengths: tuple[int, ...] = field(default=())


SUITES = (
    Suite(
        environment="house_01",
        seeds_path=REPO_ROOT / "instructions" / "seeds_house_01.json",
        nonexistent_seed="u4",
        nonexistent_words=frozenset({"lamp"}),
        inexpressible_seed="m3",
        inexpressible_verbs=frozenset({"mop", "wipe", "scrub", "clean"}),
        reference_plan_lengths=(1, 1, 2, 3, 5, 5, 5, 6, 6, 6, 6, 6, 7, 7, 9, 11, 12),
    ),
    Suite(
        environment="office_01",
        seeds_path=REPO_ROOT / "instructions" / "seeds_office_01.json",
        nonexistent_seed="u4",
        nonexistent_words=frozenset({"stapler"}),
        inexpressible_seed="m3",
        inexpressible_verbs=frozenset({"photocopy", "copy", "print", "scan"}),
        reference_plan_lengths=(1, 1, 2, 3, 3, 4, 5, 5, 6, 6, 6, 7, 8, 8, 9, 10, 15),
    ),
)

ENVS = {
    suite.environment: load_environment(REPO_ROOT / "environments" / f"{suite.environment}.json")
    for suite in SUITES
}
SEEDS_BY_SUITE = {suite.environment: load_seeds(suite.seeds_path) for suite in SUITES}
ALL_SEEDS = tuple(s for suite in SUITES for s in SEEDS_BY_SUITE[suite.environment])


def seed_id(seed: Seed) -> str:
    return f"{seed.environment}-{seed.id}"


def suite_id(suite: Suite) -> str:
    return suite.environment


def env_for(seed):
    return ENVS[seed.environment]


def augmented(env, capability):
    return dataclasses.replace(env, capabilities=env.capabilities | {capability})


def full_vocabulary(env):
    return dataclasses.replace(env, capabilities=frozenset(GLOBAL_ACTIONS))


def assert_plan_valid_both_ways(env, goal, steps):
    ours = check_response(env, goal, steps_to_text(steps))
    assert ours.verdict == "valid", ours
    translated = translate_plan(env, steps)
    assert translated.failed_index is None, translated
    task = ground_task(compile_domain(env), compile_problem(env, goal))
    theirs = run_plan(task, translated.names)
    assert theirs.status == "valid", theirs


class TestSuiteHygiene:
    @pytest.mark.parametrize("suite", SUITES, ids=suite_id)
    def test_count(self, suite):
        assert len(SEEDS_BY_SUITE[suite.environment]) == 30

    @pytest.mark.parametrize("suite", SUITES, ids=suite_id)
    def test_label_distribution(self, suite):
        seeds = SEEDS_BY_SUITE[suite.environment]
        assert Counter(s.label for s in seeds) == LABEL_DISTRIBUTION

    @pytest.mark.parametrize("suite", SUITES, ids=suite_id)
    def test_all_seeds_name_their_environment(self, suite):
        for s in SEEDS_BY_SUITE[suite.environment]:
            assert s.environment == suite.environment, s.id

    @pytest.mark.parametrize("suite", SUITES, ids=suite_id)
    def test_instructions_unique(self, suite):
        texts = [s.instruction for s in SEEDS_BY_SUITE[suite.environment]]
        assert len(set(texts)) == len(texts)

    @pytest.mark.parametrize("suite", SUITES, ids=suite_id)
    def test_no_em_or_en_dashes_anywhere(self, suite):
        raw = suite.seeds_path.read_text(encoding="utf-8")
        assert "—" not in raw, "em dash found in seed file"
        assert "–" not in raw, "en dash found in seed file"

    @pytest.mark.parametrize("seed", ALL_SEEDS, ids=seed_id)
    def test_instruction_sentence_shape(self, seed):
        assert seed.instruction[0].isupper() and seed.instruction.endswith("."), seed.id

    @pytest.mark.parametrize("seed", ALL_SEEDS, ids=seed_id)
    def test_every_seed_has_notes(self, seed):
        assert len(seed.notes) > 40, seed.id


class TestFeasibleSeeds:
    FEASIBLE = [s for s in ALL_SEEDS if s.reference_plan is not None]

    @pytest.mark.parametrize("seed", FEASIBLE, ids=seed_id)
    def test_reference_plan_validates_both_ways(self, seed):
        assert_plan_valid_both_ways(env_for(seed), seed.goal, seed.reference_plan)

    @pytest.mark.parametrize("seed", FEASIBLE, ids=seed_id)
    def test_no_spurious_infeasibility_proof(self, seed):
        assert classify_infeasibility(env_for(seed), seed.goal) is None, seed.id


class TestDecoys:
    DECOYED = [s for s in ALL_SEEDS if s.decoy_plan is not None]

    @pytest.mark.parametrize("seed", DECOYED, ids=seed_id)
    def test_decoy_produces_declared_verdict(self, seed):
        result = check_response(env_for(seed), seed.goal, steps_to_text(seed.decoy_plan))
        assert result.verdict == seed.decoy_verdict, (seed.id, result)


class TestUnreachableSeeds:
    UNREACHABLE = [s for s in ALL_SEEDS if s.label == "unreachable_goal" and s.goal is not None]

    @pytest.mark.parametrize("seed", UNREACHABLE, ids=seed_id)
    def test_provably_unreachable_even_with_full_vocabulary(self, seed):
        env = env_for(seed)
        assert classify_infeasibility(env, seed.goal) == "unreachable", seed.id
        assert classify_infeasibility(full_vocabulary(env), seed.goal) == "unreachable", seed.id

    @pytest.mark.parametrize("suite", SUITES, ids=suite_id)
    def test_nonexistent_object_seed_names_nothing_real(self, suite):
        (seed,) = [s for s in SEEDS_BY_SUITE[suite.environment] if s.id == suite.nonexistent_seed]
        env = ENVS[suite.environment]
        for word in suite.nonexistent_words:
            assert not any(i.category == word for i in env.items), word
            assert word not in {i.name for i in env.items}, word


class TestMissingCapabilitySeeds:
    WITH_GOAL = [s for s in ALL_SEEDS if s.label == "missing_capability" and s.goal is not None]

    @pytest.mark.parametrize("seed", WITH_GOAL, ids=seed_id)
    def test_infeasible_under_profile_feasible_under_grant(self, seed):
        env = env_for(seed)
        assert classify_infeasibility(env, seed.goal) == "unreachable", seed.id
        granted = augmented(env, seed.granted_capability)
        assert classify_infeasibility(granted, seed.goal) is None, seed.id
        assert_plan_valid_both_ways(granted, seed.goal, seed.capability_reference_plan)

    @pytest.mark.parametrize("suite", SUITES, ids=suite_id)
    def test_inexpressible_seed_relies_on_absent_verb(self, suite):
        (seed,) = [s for s in SEEDS_BY_SUITE[suite.environment] if s.id == suite.inexpressible_seed]
        assert not suite.inexpressible_verbs & set(GLOBAL_ACTIONS)


class TestConstraintSeeds:
    INFEASIBLE = [s for s in ALL_SEEDS if s.label == "constraint_trap" and s.expected_terminal is not None]

    @pytest.mark.parametrize("seed", INFEASIBLE, ids=seed_id)
    def test_infeasible_only_because_of_invariant(self, seed):
        assert classify_infeasibility(env_for(seed), seed.goal) == "constraint", seed.id


class TestAmbiguousSeeds:
    AMBIGUOUS = [s for s in ALL_SEEDS if s.label == "ambiguous_referent"]

    @pytest.mark.parametrize("seed", AMBIGUOUS, ids=seed_id)
    def test_bindings_share_a_category(self, seed):
        env = env_for(seed)
        categories = {env.item(a.binding).category for a in seed.alternatives}
        assert len(categories) == 1, (seed.id, categories)
        category = categories.pop()
        matching = [i.name for i in env.items if i.category == category]
        assert sorted(matching) == list(seed.clarify_candidates), seed.id

    @pytest.mark.parametrize("seed", AMBIGUOUS, ids=seed_id)
    def test_every_binding_is_feasible(self, seed):
        env = env_for(seed)
        for alt in seed.alternatives:
            assert classify_infeasibility(env, alt.goal) is None, (seed.id, alt.binding)
            assert_plan_valid_both_ways(env, alt.goal, alt.reference_plan)


class TestPlanLengthDistribution:
    @pytest.mark.parametrize("suite", SUITES, ids=suite_id)
    def test_reference_plan_lengths_are_recorded(self, suite):
        lengths = tuple(
            sorted(len(s.reference_plan) for s in SEEDS_BY_SUITE[suite.environment] if s.reference_plan is not None)
        )
        assert lengths == suite.reference_plan_lengths
