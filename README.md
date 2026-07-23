# plan-failure-bench

A benchmark measuring whether large language models fail at robot task
planning in the ways their instructions predict, with ground truth decidable
by construction and no human or LLM adjudication anywhere in the loop.

## Contribution claim

Each instruction in the suite either admits a valid plan or contains exactly
one planted trap: unreachable goal, missing capability, ambiguous referent,
precondition trap, sequencing trap, or constraint trap. The model responds in
a constrained action DSL that includes explicit `infeasible` and `clarify`
terminals, so trap detection is machine-checkable rather than judged. A
symbolic checker, differentially tested against an independent PDDL toolchain,
assigns every response one observed verdict from a fixed decision procedure.
The primary artefact is the confusion matrix between planted trap and
observed failure, always reported alongside false positives on valid
instructions, under both a plain condition and a predicate-obfuscated
condition in the style of Mystery Blocksworld. Prior work establishes that
models plan poorly (PlanBench), catalogues observed error types (Embodied
Agent Interface), and tests single trap families in isolation (Plancraft's
impossible set, AmbiK's ambiguity, SafeAgentBench's hazards). The claim here
is the cross: one decidable instrument that measures whether models fail as
predicted, whether they detect traps rather than comply, and whether that
detection survives semantic obfuscation.

## Status

Phase 1 is complete and has produced its first results.

Built and tested (294 tests, stdlib runtime, pyperplan as a dev dependency):

- Symbolic world model with per-state trajectory invariants, strict loading,
  and a deterministic renderer ([plan_failure_bench/schema.py](plan_failure_bench/schema.py))
- Action DSL and deterministic checker with an ordered verdict procedure
  ([plan_failure_bench/checker.py](plan_failure_bench/checker.py))
- PDDL compilation and differential validation of the checker against
  pyperplan on hand-written and seeded random plan corpora
  ([plan_failure_bench/differential.py](plan_failure_bench/differential.py))
- Sound unreachability and constraint-infeasibility proofs for every planted
  label, re-proved on every test run
  ([plan_failure_bench/reachability.py](plan_failure_bench/reachability.py))
- 30 hand-written seed instructions with mechanical proof obligations
  ([instructions/seeds_house_01.json](instructions/seeds_house_01.json))
- Model-agnostic harness (one interface, OpenAI-compatible and Anthropic
  wire formats), fixed disclosure prompt, JSONL results with recorded prompt
  hashes ([plan_failure_bench/runner.py](plan_failure_bench/runner.py))
- Obfuscated condition: bijective renaming applied to the prompt and
  inverted on the response, so the checker always operates on the canonical
  world; token distinctiveness guaranteed by minimum edit distance since
  obfuscation v2 ([plan_failure_bench/obfuscation.py](plan_failure_bench/obfuscation.py))
- Metrics implementing the scoring contract: detection never reported
  without paired false positives, counts not percentages, plus offline
  re-scoring under a documented lenient extraction policy
  ([plan_failure_bench/metrics.py](plan_failure_bench/metrics.py),
  [plan_failure_bench/rescore.py](plan_failure_bench/rescore.py))

## First results

Two models, two conditions, 30 seeds each, raw records under
[results/](results/). At this scale every number is a count, not a rate;
treat the observations below as hypotheses the scaled suite will test.

- The two models fail in opposite ways. Llama 3.3 70B (via Groq) wraps
  mostly-correct JSON in prose (18 of 30 strict format failures in plain)
  but detects most infeasibility traps once responses are recovered by the
  lenient policy. Qwen 2.5 7B (local, 4-bit) is format-disciplined (3 of 30)
  but detects almost nothing: zero false positives because it never refuses,
  planting nearly every trapped instruction in `precondition_violation`.
- For Llama, trap detection survived obfuscation (unreachable 3/4 to 4/4,
  ambiguous 2/3 to 3/3, false positives 3 to 1) while plan execution
  collapsed (5 of 9 valid seeds solved to 1 of 9). Detection and execution
  dissociate.
- A planted-versus-observed diagonal materialises: all four precondition
  traps produced observed `precondition_violation` from Llama in plain.
- One methodological artefact was caught and fixed by the versioned
  obfuscation: under v1's confusable tokens, Qwen showed 15
  `hallucinated_entity` verdicts; under v2's distinct tokens, 1. Records
  carry `obfuscation_version`, and v1 results remain in history under their
  own version.

A per-seed view of all four runs is in
[docs/seed_review.md](docs/seed_review.md).

## Reproducing

Python 3.10+. Create a virtual environment, then:

```
pip install pytest pyperplan
python -m pytest -q
```

Run a model (config entries are documented in
[configs/models.example.json](configs/models.example.json); API keys come
from environment variables and are never stored):

```
python -m plan_failure_bench.runner --config configs/models.json --model <name> --condition plain
python -m plan_failure_bench.runner --config configs/models.json --model <name> --condition obfuscated
```

Score a results file (strict is the primary policy; lenient reports
planning with format discipline factored out):

```
python -m plan_failure_bench.rescore results/<file>.jsonl
```

## Layout

- `plan_failure_bench/` the library: schema, checker, DSL, PDDL, proofs,
  prompts, adapters, runner, metrics, obfuscation
- `environments/` world definitions and per-environment obfuscation lexicons
- `instructions/` the seed suite with labels and proof-bearing annotations
- `prompts/` the fixed disclosure prompt, recorded verbatim
- `results/` raw run records, one JSON object per seed per line
- `tests/` 294 tests, including the differential corpus and every label's
  proof obligations
- `docs/` generated review material

## Licence

MIT. See [LICENSE](LICENSE).
