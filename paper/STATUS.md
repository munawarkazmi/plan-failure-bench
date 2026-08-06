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
- If accepted (notification 22 September 2026), two deliverables follow.
  **Camera-ready:** two edits to paper.tex, verified to build clean on
  4 August 2026 (13 pages, zero unresolved references, zero Type 3 fonts,
  line numbers gone, workshop name in the footer). Change the style option
  to `[dblblindworkshop, final]`, and repoint `\anonrepourl` at
  `https://github.com/munawarkazmi/plan-failure-bench`, because the
  conditional emits it once the preprint branch is false and there is
  nothing left to anonymise. Then incorporate reviewer feedback, which is
  the part that cannot be prepared in advance. **Poster:** drafted at
  paper/poster/, A0 portrait; confirm the board dimensions NeurIPS
  publishes closer to the date and adjust the geometry line if they differ.
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
  and arXiv endorsement and posting, which the call's non-archival
  status permits. The page limit and blinding policy were confirmed
  against the call on 4 August 2026 and are recorded below, and the
  blinded build was verified against every point of it that can be
  checked mechanically. Anonymity checked 1
  August 2026: no identifying content outside the author block, which
  the dblblindworkshop option strips; if the submission is double
  blind, the abstract's closing line switches automatically to cite an
  anonymised mirror (anonymous.4open.science over the anon-mirror
  branch, which excludes the compiled preprint; the URL drops into the
  \anonrepourl macro once generated). OpenReview profile must exist well before the
  deadline; profiles created on non-institutional email can take up to
  two weeks of moderation

## TAE call for papers, read 4 August 2026

Checked against https://tai-eval.github.io/cfp/ rather than assumed. This
discharges the standing obligation to confirm the page limit and the
blinding policy before submitting.

- Up to 8 pages, excluding references and appendices. Appendices carry no
  page restriction, but reviewers are not required to read them, so
  nothing load bearing may live only in an appendix.
- Submission style option `\usepackage[dblblindworkshop]{neurips_2026}`,
  and `[dblblindworkshop, final]` for the camera-ready. Workshop title
  string required verbatim as
  `\workshoptitle{TAE (Trust-AI-Eval): Can We Trust AI Evaluation?}`.
- Double blind. All papers must be appropriately anonymised.
- Non-archival. This matters for two other plans: the Zenodo preprint
  and an arXiv posting do not conflict with submitting here, and
  acceptance would not count as publication.
- OpenReview group NeurIPS.cc/2026/Workshop/TAE. Deadline 29 August 2026
  AoE, notification 22 September 2026 AoE, in-person poster session in
  Sydney on 11 or 12 December 2026.
- The call does not state a dual submission policy.

The submission build conforms on every point that can be checked
mechanically. The body occupies pages 1 to 8 and the References heading
begins page 9, so the paper is exactly at the 8 page limit with no
margin: any addition to the body must displace something else. Fonts are
Type 1 throughout, embedded and subsetted, no Type 3. The blinded build
contains no author name, affiliation, email, repository URL, or DOI.

## Final pre-submission read and literature micro-sweep, 4 August 2026

**The read.** Every hand-written number in the results section was
recomputed from the committed records rather than compared against the
prose. The four sampled cells were re-run through
`plan_failure_bench.consistency` and all match: 26 of 30 and 14 of 30 on
house, 24 of 30 and 17 of 30 on office for Qwen, and for Llama 19 of 30
with strict format failures of 17, 18, 17, 18 and 16 and a trap split of
7 detected in all five, 5 in some, 1 in none. The temperature 0.7
hallucination counts of 13 and 11 of 150 against 1 and 0 of 30 were
confirmed under lenient rescoring, which is the policy the paper reports.
Two claims not in any table were checked directly from records: Flash
Lite solved none of house\_01's seven ordering traps, and its
unreachability detection is 4 of 4 with all four exact under obfuscation
on house against 3 of 4 falling to 1 of 4 on office. The generated
tables regenerate byte-identically from the records. No LaTeX double
hyphen, no unicode dash, and no American spelling anywhere in the source.

Two defects were found and fixed.

- The abstract called both environments household. `office_01` is a
  lobby, canteen, server room, workshop, studio, supply room, archive
  and strong room. It now reads "two symbolic indoor environments".
- The over-refusal paragraph gave Qwen's obfuscated false positives as
  "2 and 3 of 17" immediately after a sentence that lists house before
  office, which reads as house 2 and office 3. The actual values are 3
  on house and 2 on office, so the figures are now attributed explicitly
  rather than left to positional reading.

**The micro-sweep.** Nothing published after the 1 August 2026 sweep was
found, which is unsurprising over three days. One earlier item that the 1
August sweep missed did surface and is a genuine gap: Agent Planning
Benchmark (arXiv 2606.04874, 3 June 2026), a planning-specific
diagnostic benchmark of 4,209 multimodal cases whose five settings
include unsolvable tasks, which measures calibrated refusal across 12
models, and which is motivated by the same complaint as this paper, that
end-to-end success rates cannot separate planning failures from
execution failures. It is concurrent rather than prior work, and it is
not cited. Its abstract does not state whether ground truth is proved or
authored, nor whether any judge is used in scoring, so it cannot be
positioned against without reading its body. Citing it also costs space
the paper does not have, since the body is exactly at the 8 page limit.
This is an open decision, not an oversight.

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
