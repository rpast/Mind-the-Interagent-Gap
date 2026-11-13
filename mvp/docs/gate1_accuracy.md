# Gate 1 accuracy

As of 2026-11-13, against the reviewed gold set after round 2.
Numbers: `python mvp/gold/score_gate1.py` → `mvp/out/gate1_accuracy.json`.
Regenerate before citing. Methodology and how to read them: `mvp/docs/gold_set.md`.

## What is being measured

Gate 1 only: in scope (multi-agent) against out of scope (not multi-agent). Gate 2 labels
are not scored and will be reviewed by a human analyst later.

**The gold set is 57 rows: 21 in, 33 out, 3 unclear.** The 3 unclear rows (G-007, G-025,
G-031) are excluded from every figure, leaving **54 scorable rows**. Three further rows were
dropped before scoring and are kept with their reasons in `mvp/gold/dropped.csv`: two
duplicates and one row whose only source cannot be read.

## The headline: there is nothing of ours to score yet

**`mvp/proposals/` does not exist. The classifier has never been run,** so its accuracy
cannot be computed. Everything below scores the predictors that do exist, which is what the
model will have to beat.

| predictor | n | precision | recall | accuracy |
|---|---|---|---|---|
| The index's earlier hand-curation (the ceiling) | 22 | **81.8%** | 100% by construction | 81.8% |
| AIID CSETv1 `Multiple AI Interaction` (human annotators) | 5 | **20.0%** | 100% by construction | 20.0% |
| Keyword prefilter arm | 32 | 11.1% | 66.7% | 46.9% | 
| Prefilter queue membership, any arm | 32 | 9.4% | 100% | 9.4% |

Recall is "100% by construction" wherever a stratum contains only that predictor's
positives: it had no chance to miss anything, so the figure carries no information. Only
precision means anything on those rows.

## Read each number with its caveat

**The ceiling: 81.8% precision (18 of 22).** This is the one informative figure.
Four of its asserted positives do not survive review: G-002 (a tool that exists, with no
event), G-013 (an ordinary cloud misconfiguration where no agent acted), G-014 (a game whose
conflict the experimenters designed in) and G-005 (one agent moving through merged
identities). An 18% false-positive rate in a hand-built inventory is the thing the classifier
has to improve on, and it sets a realistic ceiling: these are hard calls, not sloppy ones.

**CSETv1 scored 20% precision (1 of 5).** Independent human annotators, and four of their
five positives fail our Gate 1. This is the measured form of the argument already in
`definitions.md`: an external rater's label means something different from ours. It is not a
criticism of their annotation, which answers a different question.

**The keyword arm's precision cannot be measured on this set, and the 11.1% above should
not be quoted.** All 18 rows of the `queue_boundary` stratum tripped the keyword arm — the
stratum was *defined* that way. The predictor is therefore the sampling frame, and its
"precision" on those rows is just that stratum's base rate. Measuring a predictor on a sample
drawn by that predictor is circular. Its recall rests on 3 positives in total (2 found, 1
missed), which is too few to carry a decimal point.

**This supersedes the keyword arm's previously recorded 78% recall.** That figure was
measured against the unreviewed inventory positives, most of which are not in the prefilter
queue at all: 22 of 54 scorable rows have no queue row, including every carried-over row from
AI Village, the Agent Incident Registry and LessWrong. The keyword net runs over AIID, and
most of the index's positives are not in AIID. The honest statement is that the keyword arm's
recall is **unmeasured**, not 78%.

## What 21 positives rest on

| basis | n |
|---|---|
| Gate 1 on agent-to-agent interaction (not security rows) | 15 |
| Stated evidence that multiplicity was load-bearing | 2 |
| The multi-agent-attack presumption alone (`unreported`) | 4 |

**Four of 21 positives — 19% — are in scope only because of the presumption**: G-017
(RubyGems), G-019 (Taiwan intrusion), G-047 (Canada archives), G-049 (Vanderbilt). Any claim
resting on the inventory should say so, because reversing that one rule moves a fifth of the
positives. The two rows with stated evidence are G-020, where OpenAI's own report asserts it,
and G-016.

## Fixing the sample before the next run

The circularity above is a design fault in the draw, not a result. To measure the keyword arm
or any screen honestly, the negatives must be drawn **independently of the predictor being
scored** — a random sample of the AIID window, screened by hand, with the keyword arm scored
afterwards. The present draw is still fit for what it was built for: measuring precision on
the decision boundary. It cannot measure recall, and it cannot score the screen that selected
it.
