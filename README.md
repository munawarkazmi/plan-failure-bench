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
symbolic checker, differentially tested against the VAL plan validator,
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

Pre-alpha. Nothing below this line is implemented yet. Any number not
accompanied by a script that reproduces it should be treated as untested.

## Phase 1 scope

- World model schema and one hand-built environment
- Action DSL with a deterministic validity checker, differentially tested
  against VAL
- 30 seed instructions with ground-truth labels, counts reported rather than
  percentages at this scale
- One HTTP adapter covering local (OpenAI-compatible endpoint) and API models
- Fixed terminal-disclosure prompt, identical for every model, recorded
  verbatim in this repository

Out of scope for phase 1: web leaderboard, ROS2 or Gazebo integration,
runtime-verifier baselines, scaling past 30 instructions, paper writing.

## Licence

MIT. See [LICENSE](LICENSE).
