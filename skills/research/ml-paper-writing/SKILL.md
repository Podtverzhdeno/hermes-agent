---
name: ml-paper-writing
description: Draft and audit AI/ML research manuscripts using traceable experimental evidence, verified citations, reproducibility and venue-specific requirements.
version: 2.0.0
author: Hermes Agent (curated from Orchestra Research)
license: MIT
metadata:
  hermes:
    tags: [ML-Research, Manuscripts, LaTeX, Citations, Reproducibility, Review]
    related_skills: [arxiv, evaluating-llms-harness, code-review]
---

# ML Paper Writing — every claim must have a source of truth

## Activation and responsibility

Use when turning a research repository, experiment log or scientific
hypothesis into a manuscript, camera-ready revision, literature review or
submission audit. For an unscientific marketing blog post use another skill.
Read `harness.yaml` for preflight, evidence, approvals, verification and
recovery. **Never fabricate** results, graphs, citations, human studies,
baseline conditions, reviewer feedback or venue rules.

The original long 2026-era guide is archived in
`references/legacy-paper-guide-2026.md`. It is not a live authority for
current submission deadlines, page limits or policies.

## 1. Establish provenance before writing prose

Build a concise **claim ledger** with fields:

| ID | Proposed claim | Source | Exact evidence | Scope | Verification |
|---|---|---|---|---|---|
| C1 | Proposed quantitative result | dataset/run/artifact | metric, unit, seed, CI | evaluation split | verified / pending |
| C2 | Literature contribution | DOI/arXiv/venue | supported section | prior work | verified / pending |

Collect repository commit, data version, preprocessing scripts, model
checkpoint hashes, metric definitions, baselines, train/dev/test split
protocol, sample counts, seeds, hardware and uncertainty. A CSV containing
numbers alone is not enough to support the paper's causal conclusions.

Distinguish:
- **Observation:** what was measured;
- **Inference:** which explanation is supported and under what assumptions;
- **Speculation:** a plausible mechanism requiring further experiments;
- **Prior work:** supported by primary literature, not inferred from a title.

If files are inaccessible, the manuscript can be a labeled **draft**,
but never a fabricated completed empirical study.

## 2. Verify literature at the source

For each claimed publication:

1. Search primary venues, DOI registries, arXiv or publisher records.
2. Match **title, authors, venue/date, identifier and version**.
3. Read the actual relevant methods/results, not merely the abstract, for
   claims about comparative performance or study limitations.
4. Fetch BibTeX from trustworthy metadata. Check every citekey resolves.
5. Record whether it is a preprint, accepted conference paper, journal
   paper or replication; avoid treating preprint claims as independently
   validated facts.

Never invent a BibTeX entry. When verification is impossible, keep an
explicit placeholder in the drafting tracker rather than inventing an
author, DOI or exact percentage. Claims like "X% of AI citations are wrong"
require verified, context-relevant empirical support; do not propagate an
unsourced figure.

## 3. Formulate a falsifiable contribution

Define research question, hypotheses, contribution, adjacent work,
target task, dataset, experimental controls and expected limitations.
A novelty claim must be relative to specific, inspected prior work;
avoid "first ever" without a defensible literature review.

Choose an evaluation protocol appropriate to the task:
- Tasks/datasets and licensing, contamination and split leakage;
- Tokenization, prompt template, decoding and model versions;
- Baseline comparability, compute and hyperparameter tuning budget;
- Significance/uncertainty (confidence intervals, paired tests or seeds)
  when warranted, with assumptions stated;
- Latency and cost under matched hardware/traffic, if performance claimed;
- Ablations and negative results where material;
- Human evaluation instructions, sampling and inter-rater consistency if
  human judgments underpin conclusions.

Do not report a delta without baseline definition and measurement units.

## 4. Manuscript structure and review

Create a clear contribution narrative without overstating certainty:

1. **Abstract:** concrete problem, method, evaluated setting, actual result
   and bounded impact, with no novel facts absent from the body.
2. **Introduction:** motivation, gap, method overview, hypotheses and
   contributions; each prior-work statement cited.
3. **Related work:** fair distinctions; the same baseline/dataset setting
   determines whether results are comparable.
4. **Method:** definitions, algorithm, implementation, complexity,
   reproducibility details and failure cases.
5. **Experiments:** datasets, baselines, splits, metrics, compute,
   ablations, uncertainty and protocol.
6. **Limitations, ethics and broader impact:** known weak settings,
   representativeness and privacy/safety concerns.
7. **Conclusion:** only takeaways supported by the presented evidence.

Use descriptive tables/figures with readable axis labels, units, sample
sizes and captions. Trace each plotted number to an experiment artifact.
Never include a visual generated from invented values in a real-results
figure.

## 5. Venue-specific submission audit

Official NeurIPS, ICML, ICLR, ACL, AAAI and COLM rules change annually.
Before choosing a template or page count, inspect the **current, official
Call for Papers / author instructions for the exact event year and track**.
Record checked URL and access date. Do not reuse rules from the archived
2026 guide without verification.

Check double-blind identity rules, supplementary material, code/data
statements, ethical review, reference formatting, publication policy and
deadline timezone against official pages. The author retains the final
responsibility for submission. Do not upload or submit manuscripts, source
code or unpublished results without explicit authorization.

## 6. LaTeX and artifact verification

Start with the official venue template; preserve its required style files
and license. Keep a separate build directory for outputs. Avoid enabling
shell escape for untrusted documents. If authorized and the environment
supports it, run:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Confirm citation resolution, missing files, overfull content, figure
readability, anonymization and PDF page count. A successful compile is not
proof of paper correctness; verify against the claim ledger and official
review checklist. Where a PDF must be checked visually, inspect rendered
pages rather than relying solely on parsed text.

## 7. Final independent validation

Re-read the paper as three separate reviewers:

- **Scientific validity:** is each conclusion justified by the protocol?
- **Reproducibility:** can another researcher reconstruct the experiment?
- **Communication/compliance:** are citations, claims, figures and venue
  requirements exact and understandable?

Audit a sample of the most important numerical claims *back to raw artifacts*,
and verify every bibliography identifier. Separate "cannot verify" from
"verified incorrect". Never use self-assigned 10/10 without independent tests.

## Recovery and reporting

On missing results, stop short of quantitative claims and create a list of
needed experiments. On unverifiable citations, use explicit TODO entries.
On a failed build, preserve the project and capture the exact error without
overwriting source files. Never delete or publicly release research artifacts
just to "clean" a failed submission.

Output: paper revision, claim ledger, checked sources, experiment lineage,
venue instruction URL/date, compilation result, reviewer findings and
remaining blockers. Say clearly if there was no actual submission.

Reference index: `references/legacy-paper-guide-2026.md` (historical).
