# Working paper status

A living draft, completed as the research completes. Every tick below is
verifiable from this repository; nothing is marked done that cannot be
inspected.

## Current status

- [x] Benchmark implementation (two environments, 60 proof-carrying
  seeds, a 548-test suite in CI that includes proofs for every label)
- [x] Methodology (world model, checker, differential testing,
  reachability proofs, versioned obfuscation; documented in the README
  and in sections 3 to 5 of the draft)
- [x] Literature review (related work section drafted and positioned;
  every citation verified against public records and every finding
  attributed to a paper checked against its body, 25 July 2026, with
  TREK and AgentAbstain added and body-checked by the 30 July 2026
  sweep, and the 1 August 2026 sweep for the venue decision adding a
  measurement-validity paragraph, Bean et al.'s construct validity
  review, Norman et al.'s judge reliability evaluation, the Clever
  Hans shallow-feature result, and SIMMER, each body-checked; the
  section carries its own verification log. One standing obligation:
  a final micro-sweep for work newer than 1 August 2026 immediately
  before submission)
- [x] Experiments, original grid (all 14 planned single-decode runs
  complete: three models, both environments, both conditions, with
  superseded v1 runs retained and marked; plus the frontier model's
  full grid on both environments in both conditions, the three-prompt
  sensitivity experiment, Qwen's full k=5 sampling grid, and Llama's
  k=5 plain house_01 cell. No run is pending; the follow-on tracked in
  future work is sampling for the remaining cells)
- [ ] Statistical analysis (the k=5 sampling harness and per-seed
  consistency report are implemented and tested; Qwen's full grid is
  sampled and committed, both environments in both conditions, 600
  decodes, plus Llama's plain house_01 cell, 150 decodes. The
  remaining cells are single decodes, so the analysis stays open)
- [ ] Writing (every section drafted, related work included; an
  editing pass over the full draft applied 30 July 2026, catching the
  stale test count, the stale figure caption, and the setup and
  abstract sentences the frontier office runs had overtaken; framing
  decided 31 July 2026: a methodology paper, the instrument is the
  contribution and the four-model grid its demonstration, with the
  abstract and introduction rewritten to that framing; a final
  pre-submission read remains)
- Preprint published: Zenodo, 2 August 2026. Concept DOI
  10.5281/zenodo.21756817 (always newest version), V1 DOI
  10.5281/zenodo.21756818. The uploaded file was byte-identical to the
  committed paper.pdf (MD5 verified) until the correction of 4 August
  2026 below, so the V1 record on Zenodo now differs from the committed
  paper by one number and carries a wrong one. Pushing a new version is
  therefore no longer only a pre-submission tidy, it is a correction.
  After the pre-submission rebuild,
  push the new paper.pdf to Zenodo as a new version under the same
  concept DOI.
- Target venue: decided 1 August 2026, the TAE workshop (Can We Trust
  AI Evaluation?) at NeurIPS 2026, Sydney. Submission deadline 29
  August 2026 AoE via OpenReview, NeurIPS 2026 format, in-person
  poster presentation expected. The draft is in the official NeurIPS
  2026 template (vendored neurips_2026.sty; committed builds use the
  preprint option, and the submission build switches one option to
  dblblindworkshop, which anonymises automatically). Remaining before
  submission: final pre-submission read, final literature micro-sweep,
  arXiv endorsement and posting, and confirming TAE's page limit and
  blinding policy from its call before uploading. Anonymity checked 1
  August 2026: no identifying content outside the author block, which
  the dblblindworkshop option strips; if the submission is double
  blind, the abstract's closing line switches automatically to cite an
  anonymised mirror (anonymous.4open.science over the anon-mirror
  branch, which excludes the compiled preprint; the URL drops into the
  \anonrepourl macro once generated). OpenReview profile must exist well before the
  deadline; profiles created on non-institutional email can take up to
  two weeks of moderation

## Corrections

- 4 August 2026. The sampling stability paragraph said the eleven
  undetected trap seeds went undetected in "their 65 decodes". Eleven
  seeds at five decodes each is 55. Sixty-five is thirteen seeds at five,
  which is every trap decode including the ten belonging to the two seeds
  that were detected, so the figure contradicted the sentence it sat in.
  Corrected in the paper and in the README, and the arithmetic now closes
  against the run: 55 undetected plus 10 detected plus 85 feasible is
  150, which is 30 seeds at five decodes. The split of 13 trap and 17
  feasible seeds is reproduced by
  `python -m plan_failure_bench.consistency` over the five committed
  sample files rather than asserted. The published V1 preprint carries
  the wrong figure and needs a new version under the concept DOI.

## Ground rules for this draft

- The results tables are generated by `tools/build_paper_results.py`
  from the committed records in `results/`; they are never edited by
  hand, so the paper cannot drift from the data.
- Counts, not percentages, at n=30 per condition. Detection numbers are
  never reported without the paired false positive count.
- Findings are labelled hypotheses until the sampling protocol supports
  more.

## Building the PDF

Requires a LaTeX toolchain (for example `texlive` plus `latexmk`, or
`tectonic`). From `paper/`:

```
make            # latexmk
make tectonic   # single-binary alternative
```

The PDF is committed at milestones rather than on every edit.
