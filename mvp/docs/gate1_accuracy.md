# Gate 1 accuracy

Numbers: `python mvp/gold/score_gate1.py` → `mvp/out/gate1_accuracy.json`.
Regenerate before citing. Methodology and how to read them: `mvp/docs/gold_set.md`.

*Note, 2026-11-17: the prefilter's arms were replaced by `basis` and `flags`. "Keyword arm" and "any arm" in the sections below are the figures as measured on 2026-11-16; read them as the `keyword` flag and queue membership.*

## 2026-11-18: the record pass on Opus

`enrich_context.v2`, record pass, run on `claude-opus-5-5` over all 58 gold rows from the
same blind inputs as the Sonnet run (`mvp/out/calibration/enrich_context_v2_gold_opus_20261118.jsonl`;
comparison in `enrich_opus_vs_sonnet_20261118.txt`). Until now Opus had never run the
record pass on a gold row judged `in`: those rows were read by hand during the gold review.

**The safety check passes:** no row judged `in` came out `one` or `none` (21 `several`,
1 `unknown`), the same as Sonnet.

| | Opus | Sonnet |
|---|---|---|
| gold `in` rows called `one` or `none` | 0 of 22 | 0 of 22 |
| rows that would close if unflagged (`one` or `none`) | 15 of 58 | 21 of 58 |
| gold `out` rows among them | 15 of 33 | 21 of 33 |
| `unknown` on gold `out` rows | 11 | 6 |

Every row either model would close is a gold `out`, so both are safe on this set. Opus is
more cautious: where the text names no agent it says `unknown` and sends the record on to
a source read, which costs fetches but loses nothing. The two models agree on
`agent_count` on 47 of 58 rows; all 11 disagreements are gold `out` rows.

**Run-to-run variation.** On the 19 rows Opus also read on 2026-11-15, today's run agrees
on 13. All 6 changes are on gold `out` rows, and 4 of them moved from `one` to `unknown`,
the cautious direction. The `agent_count` of a single run is not stable to the row. The
check that matters, no `in` row closed, held in both runs.

## 2026-11-17: the same calibration on Sonnet

Both prompts were run on `claude-sonnet-5-5`, blind to the verdicts, and scored with
`python mvp/gold/score_gate1.py --run <file> --json <file>`. Files in
`mvp/out/calibration/`, all dated 20261117: `extract_gate_v3_gold_sonnet_*`,
`enrich_context_v2_gold_sonnet_*`, `gate1_accuracy_sonnet_*.json` and the per-row comparison
`sonnet*_vs_opus_*.txt`. Rules `2026-11-16` throughout.

| run | n | TP | FP | FN | TN | precision | recall | settled without review |
|---|---|---|---|---|---|---|---|---|
| Opus, 2026-11-15 (below) | 55 | 20 | 3 | 2 | 30 | 87.0% | 90.9% | 6 |
| **Sonnet, same inputs as Opus** | 55 | 20 | 3 | 2 | 30 | **87.0%** | 90.9% | 3 |
| Sonnet, with the source-pass context rows | 55 | 20 | 6 | 2 | 27 | 76.9% | 90.9% | 4 |

**On the same inputs, Sonnet gives Opus's Gate 1 labels on all 55 rows**, with the same five
errors (G-002, G-056 by presumption; G-014; G-011, G-012). The difference is confidence:
Sonnet answers `low` on 21 rows to Opus's 11 and `high` on 4 to Opus's 9, so 52 rows are
review items against 49. Field-level agreement is lower on the facts Gate 1 does not turn
on: `environment_controlled_by` 41/55, counterfactual 46/55, `multiplicity_role` 48/55.

**Which inputs.** 13 gold rows now hold two context rows: a record pass and a source pass,
both dated 2026-11-15. Opus's own `uncertainty_reason` on them says multiplicity was
`unread`. On that evidence it saw only the record-pass row, though git cannot confirm it,
because both went in with one commit. The first Sonnet run was given both rows, and three
labels changed: G-035, G-036, G-054 became FP by presumption. The source pass marks
multiplicity `not_stated`, so the prompt correctly asks for `unreported`. On those three
records Sonnet left `n_ai_agents` null while saying no AI agent is described, and a null
count lets the presumption fire. Re-run with the record-pass row only, the three return
to TN (the "same inputs" row above). **This is a gap in the rule, not a Sonnet fault**: a
null agent count on an attack record whose source pass is silent on multiplicity is put in
scope. Opus was not run on the source-pass inputs, so whether it closes the gap is untested.
The queue will carry source-pass rows, so this matters before the queue run.

**enrich_context.v2, record pass.** Sonnet ran on all 58 gold rows. **The safety check
passes:** no row judged `in` came out `one` or `none` (21 `several`, 1 `unknown`). The 19
gold rows that also have an Opus record-pass row are all `out`. On those, the two models
agree on `attack` 18/19 but on `agent_count` only 8/19: Sonnet answers `none` 9 times to
Opus's 3. No in-scope row was lost that way. The prompt asks for `unknown` whenever the
reader is unsure, and Sonnet is readier to close a record. On unflagged queue records that
ends their journey, so it is the place to watch. Fact-status agreement is low on
`cooperation` (6/19), `objectives` (8/19) and `interaction` (9/19).

## 2026-11-16: the classifier, scored

The classifier has now been run on the gold set. `extract_gate.v3` read each of the 55
scorable gold rows, with its record and its `mvp/context/` row, blind to the verdict
(`mvp/out/calibration/extract_gate_v3_gold_20261115.jsonl`, run 2026-11-15). The labels
were derived by `mvp/pipeline/derive.py`, the code the pipeline runs. The script's block 4
gives these figures.

| rule | n | TP | FP | FN | TN | precision | recall |
|---|---|---|---|---|---|---|---|
| attack presumption as it was to 2026-11-15 | 55 | 20 | 6 | 2 | 27 | 76.9% | 90.9% |
| **presumption with two conditions, from 2026-11-16** | 55 | 20 | **3** | 2 | 30 | **87.0%** | 90.9% |
| the ceiling: earlier hand-curation (below) | 23 | 19 | 4 | — | — | 82.6% | — |

**The rule change.** Under the old rule, 5 of the 6 false positives came from the attack
presumption: an `unreported` attack was put in scope even where the model had answered
`could`, and even where no AI agent was on the attacking side. From 2026-11-16 the
presumption fires only when the record does not show fewer than two AI agents and the model
did not answer `could` (`definitions.md`). That removes G-005, G-013 and G-058. The three
false positives left are G-002 and G-056, both still by the presumption, and G-014, a
counterfactual call. The two false negatives, G-011 and G-012, are low-confidence `unclear`
counterfactuals on non-attack rows. No true positive was lost.

The classifier now beats the ceiling of 82.6%, the precision of the index's own earlier
hand-curation.

**Most rows still go to a person.** 49 of the 55 rows are review items: confidence below
high, or a gate field unclear. Under the skill they produce no settled label. The figures
above score them on the labels the rules would give if a person confirmed the facts. The
6 rows the rules settle on their own are all correct (3 TP, 3 TN), which is too few to
quote as a rate.

**Caveat: this measures the gate given good readings, not end to end.** The gold rows'
readings in `mvp/context/` were written during the gold review, and some carry judgement
wording such as "NOT LOAD-BEARING". A reading made by the enrichment prompt on a fresh
record will be weaker. The figures say how well the rules and call 1 do when the reading
is good.

## 2026-11-14: the predictors before the classifier

As of 2026-11-14, against the reviewed gold set after round 2, with G-024 restored.

## What is being measured

Gate 1 only: in scope (multi-agent) against out of scope (not multi-agent). Gate 2 labels
are not scored and will be reviewed by a human analyst later.

**The gold set is 58 rows: 22 in, 33 out, 3 unclear.** The 3 unclear rows (G-007, G-025,
G-031) are excluded from every figure, leaving **55 scorable rows**. Two further rows were
dropped before scoring and are kept with their reasons in `mvp/gold/dropped.csv`: one
duplicate and one row whose only source cannot be read. The 22 in-scope rows cover 21
distinct incidents: G-049 (Vanderbilt) is one incident with G-016 (DSEWiki).

## The headline on 2026-11-14: nothing of ours to score yet

*Superseded by the 2026-11-16 section above, which scores the classifier.* On 2026-11-14
the classifier had never been run, so its accuracy could not be computed. What follows
scores the predictors that did exist, which is what the model had to beat.

| predictor | n | precision | recall | accuracy |
|---|---|---|---|---|
| The index's earlier hand-curation (the ceiling) | 23 | **82.6%** | 100% by construction | 82.6% |
| AIID CSETv1 `Multiple AI Interaction` (human annotators) | 5 | **20.0%** | 100% by construction | 20.0% |
| Keyword prefilter arm | 32 | 11.1% | 66.7% | 46.9% | 
| Prefilter queue membership, any arm | 32 | 9.4% | 100% | 9.4% |

Recall is "100% by construction" wherever a stratum contains only that predictor's
positives: it had no chance to miss anything, so the figure carries no information. Only
precision means anything on those rows.

## Read each number with its caveat

**The ceiling: 82.6% precision (19 of 23).** This is the one informative figure.
Four of its asserted positives do not survive review: G-002 (a tool that exists, with no
event), G-013 (an ordinary cloud misconfiguration where no agent acted), G-014 (a game whose
conflict the experimenters designed in) and G-005 (one agent moving through merged
identities). A 17% false-positive rate in a hand-built inventory is the thing the classifier
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
queue at all: 23 of 55 scorable rows have no queue row, including every carried-over row from
AI Village, the Agent Incident Registry and LessWrong. The keyword net runs over AIID, and
most of the index's positives are not in AIID. The honest statement is that the keyword arm's
recall is **unmeasured**, not 78%.

## What 22 positives rest on

| basis | n |
|---|---|
| Gate 1 on agent-to-agent interaction (not security rows) | 15 |
| Stated evidence that multiplicity was load-bearing | 3 |
| The multi-agent-attack presumption alone (`unreported`) | 4 |

**Four of 22 positives — 18% — are in scope only because of the presumption**: G-017
(RubyGems), G-019 (Taiwan intrusion), G-047 (Canada archives), G-049 (Vanderbilt). Any claim
resting on the inventory should say so, because reversing that one rule moves a fifth of the
positives. The three rows with stated evidence are G-020, where OpenAI's own report asserts it,
G-016 and G-024. G-049 is counted here on its own source, which is silent; as an incident
it is part of G-016, which has stated evidence.

## Fixing the sample before the next run

The circularity above is a design fault in the draw, not a result. To measure the keyword arm
or any screen honestly, the negatives must be drawn **independently of the predictor being
scored** — a random sample of the AIID window, screened by hand, with the keyword arm scored
afterwards. The present draw is still fit for what it was built for: measuring precision on
the decision boundary. It cannot measure recall, and it cannot score the screen that selected
it.
