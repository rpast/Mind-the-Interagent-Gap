# The gold set and the ceiling

How the evaluation set was built, what is in it, and how the accuracy ceiling is calculated.
Companion to `mvp/docs/gate1_accuracy.md`, which reports the figures.

## What the gold set is for

One job: to measure whether an automatic screen can decide **Gate 1** — is an event in scope
(multi-agent) or out of scope (not multi-agent) — as well as a careful human reading the
primary sources. Gate 2 labels are recorded in the set but are not scored; a human analyst
reviews those separately.

A set built for that job needs two things the index did not originally have: **negatives**,
without which precision cannot be measured at all, and **verdicts formed independently of
whatever labelled the rows before**, without which the measurement is circular.

## How the set was assembled

60 rows drawn in four strata, deliberately not in proportion to the population.

| stratum | n | how it was drawn |
|---|---|---|
| `carried_over` | 27 | Every incident the index already held, taken whole, not sampled. |
| `aiid_csetv1` | 6 | Every AIID incident whose CSETv1 `Multiple AI Interaction` attribute is `yes` or `maybe` — the only purpose-built multi-agent label in the corpus, applied by independent human annotators. |
| `queue_boundary` | 18 | Candidates that tripped the prefilter's keyword arm: something in the text looked multi-agent. |
| `queue_base_rate` | 9 | Candidates with no signal at all, as a control. |

The 27 negative candidates come from the prefilter queue, dated 2025–2026, excluding anything
AIID marks multi-agent (`mvp/gold/sample_negatives.py`, seeded). **They were drawn as
unscreened, not as negatives.** AIID applies no multi-agent label in that window at all —
CSETv1 stops in 2024 — so the absence of one carries no information, and a real multi-agent
incident sitting in the pool would become a false negative that unfairly penalises any screen.
Each needed a human verdict, and got one.

**Known bias, stated up front.** The draw oversamples the keyword arm on purpose: only 32 of
267 pool members trip it, so a proportional sample would be almost all signal-free records.
Precision measured against this set is therefore **pessimistic** and describes the decision
boundary, not the population. `--hard 0` draws a base-rate sample instead.

## How the verdicts were formed

Two rounds, both by a human against the sources.

**Round 1 (2026-11-13).** Each row was judged in a self-contained worksheet
(`python mvp/gold/build_review.py` → `mvp/out/gold_review.html`) showing the narrative, the
sources as links and any external labels, and asking the gate questions in order. Any label
the row already carried was **collapsed behind a toggle, so the verdict was formed before the
earlier one was seen.** That independence is the point of the exercise; without it the
measurement would report agreement with an earlier pass rather than accuracy.

**Round 2 (2026-11-13).** Round 1 was conducted on the rows' one-line inventory text —
70–261 characters for the carried-over rows, 335–500 for the AIID ones. That is a headline,
not a record, and several facts the gates require were simply absent from it: how many agents,
whether they interacted, who controlled the environment, what multiplicity contributed. The
sources were then read properly and written up field by field in `mvp/gold/context/`, and
every row was re-judged against them. Five verdicts changed. Nineteen rows carry a round-2
note recording the basis; `review_round` says which round settled each row.

**Two rows are removed from scoring**, with reasons, in `mvp/gold/dropped.csv`: one
duplicate of a row that survives, and one whose only source cannot be read (Reuters refuses
automated fetches). A third, G-024, was dropped as a duplicate of G-020 and restored on
2026-11-14: the primary source treats the two as separate events in one chain.

**Gold ids are permanent.** `mvp/gold/gold_ids.csv` registers every id ever issued, so
dropping, restoring or merging a row never renumbers another.

## The set as it stands

**58 rows: 22 in · 33 out · 3 unclear.** The 3 unclear rows are excluded from every figure,
leaving **55 scorable**. The 22 in-scope rows cover 21 distinct incidents.

| stratum | n |
|---|---|
| `carried_over` | 25 |
| `aiid_csetv1` | 6 |
| `queue_boundary` | 18 |
| `queue_base_rate` | 9 |

`unclear` is a real verdict, not a failure to answer. It means the sources do not settle
Gate 1, and `definitions.md` requires that it never be guessed.

## The ceiling calculation

### What it measures

The ceiling is **not a classifier score.** The classifier's own score on this set is a
separate block of `score_gate1.py`, first measured on 2026-11-16; see `gate1_accuracy.md`.

It is the accuracy of **the index's own earlier hand-curation**, measured against the
independent review. The 25 `carried_over` rows were each added to the index by a human
applying the same inclusion test, and each asserted the event was multi-agent. The review then
re-decided every one from the primary sources. The ceiling is how often those two human
passes agree.

### Method

1. Take the `carried_over` stratum only. Other strata were not curated this way, so they
   cannot speak to curation quality.
2. Drop rows whose review verdict is `unclear`: with no ground truth there is nothing to
   score against. 25 → **23 scorable**.
3. The prediction for every one of these rows is **in scope**, because each was added to the
   index as a multi-agent incident.
4. The truth is the review verdict.
5. Count: a row the review kept is a true positive, a row it rejected is a false positive.

### Why only precision

Every row in the stratum is an asserted positive, so the stratum contains **no negatives for
the curation to have correctly rejected and none it could have missed**. Recall is therefore
100% by construction and carries no information, and so do accuracy and F1, which are
arithmetic on the same degenerate counts. Precision is the only figure that means anything,
and it is the only one that should be quoted.

### The numbers

```
n = 23    TP = 19    FP = 4    FN = 0    TN = 0
precision = 19 / 23 = 82.6%
```

The four the review rejected, and why:

| row | reason it failed Gate 1 |
|---|---|
| G-002 | A capability that exists and is sold. No event, no victim, and no interaction between its models. |
| G-005 | One agent moving laterally through merged identities. No second agent acts; the risk is a privilege-architecture flaw. |
| G-013 | An ordinary cloud misconfiguration on a platform that happens to serve agents. No agent acted at all. |
| G-014 | A game whose adversarial roles the experimenters designed in. The conflict was built, not produced by interaction. |

### How to read 82.6%

As a **realistic target, not a floor to clear trivially.** Careful hand-curation against the
same definitions put roughly one in five of its positives wrong, and the four misses above are
genuinely hard calls rather than carelessness: each turns on a distinction the definitions
make but a headline does not show — a tool against an event, one agent against two, a designed
conflict against an emergent one.

Two consequences. A screen scoring far below 82.6% is not usable. A screen scoring far
**above** it should be treated as suspect until checked, because the comparison is against
human judgement that has itself been revised once, on a set small enough that one row moves
the figure by about 4 points.

### What the ceiling is not

- Not a measure of any automatic classifier.
- Not a population estimate. The stratum is the whole of the index's earlier holdings, so it
  describes that inventory and nothing wider.
- Not stable to one more review round. 23 rows is small; the confidence interval is wide and
  no decimal place should be trusted.

## A second measured comparison

The `aiid_csetv1` stratum gives the same precision-only test on an outside rater's positives:
independent human annotators, 5 scorable rows, **1 true positive — 20% precision.** Four of
their five positives fail our Gate 1. This is not a criticism of their annotation; their
attribute answers a different question, which is exactly the point `definitions.md` makes
about external labels. It bounds how much an inherited label can be trusted as a verdict.

## What this set cannot measure

**It cannot score the prefilter's keyword arm.** All 18 `queue_boundary` rows tripped that
arm, because the stratum was defined that way. The predictor is the sampling frame, so its
precision on those rows is just the stratum's base rate — circular. Its recall rests on 3
positives in total.

**It cannot measure any screen's recall over the index's subject matter.** 23 of the 55
scorable rows have no prefilter queue row at all: the keyword net runs over AIID, and most of
the index's positives are not in AIID.

To fix either, the negatives must be drawn **independently of the predictor being scored** —
a random sample of the window, hand-screened, with the screen scored afterwards.

## Reproducing the figures

```
python mvp/gold/score_gate1.py                           # every figure in this doc
python mvp/gold/build_review.py                          # rebuild the worksheet
python mvp/gold/build_review.py --merge <exported.csv>   # fold verdicts back in
```

`build_review.py` regenerates the set from the dossiers on every run, so it filters out
anything listed in `mvp/gold/dropped.csv`; without that the retired rows would silently
return.

Figures: `python mvp/gold/score_gate1.py` → `mvp/out/gate1_accuracy.json`. The inputs to the ceiling calculation —
the earlier curation's assertions, row by row — are archived in
`mvp/gold/archive/`, not held in the live set, so the number stays reproducible without those
labels sitting next to the verdicts where they could contaminate a later review.
