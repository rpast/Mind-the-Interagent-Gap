# Classifier design

Two model calls produce the labels. Everything they emit is a **proposal**; a human
promotes. See `mvp/docs/definitions.md` for the definitions the classifiers apply.

## Why this shape

**Not a trained model.** The labelled set is small — tens of positive examples, not
thousands — and that is unlikely to change, because each positive requires a human to read a
primary source. The decision is also a definitional counterfactual rather than a surface
pattern: every verdict needs a citable rationale and a quote, because it will be argued with,
and the definitions are still being sharpened. A fine-tuned or BERT-style classifier needs
hundreds to thousands of labels, returns no reasoning, and would have to be retrained each
time a definition moves.

**Not one master prompt.** Asking for multi-agent, evidence type and failure mode in one
answer is cheapest, but the three judgements contaminate each other — a model that has just
written "collusion" is more likely to call the setting real-world — and no single rubric can
be revised without redoing all of them. It also throws away the independent cross-check
described below.

**Not three classifiers either.** Three separate calls each re-read the whole record, so the
input cost triples for no gain, and the three passes can contradict each other with no
shared basis to adjudicate from.

**What is actually expensive is reading the record once.** So: one extraction call, then
rules in code, then one more call for the only judgement that genuinely needs the model to
hold more context.

```
call 1   read the record, extract facts, answer the two gate questions
           -> multi_agent      rule over gate 1 + interaction_present
           -> evidence_type    rule over setting, stakes, who controlled the environment
           -> failure_mode     rule: the gate 2 tree, over the FM definitions
call 2   assign instance ids               (only if the record passed Gate 1)
           -> instances        descriptive detail, assigned independently
```

The two calls answer different questions and neither feeds the other. Call 1 produces the
labels from a handful of extracted facts. Call 2 describes the incident more finely against
the 33 instance definitions, which do not fit in call 1's prompt and would skew its
judgement if they did — a model that has just read "Swarm Attacks" is readier to call the
next record a swarm.

**Instances do not determine the failure mode**, and the failure mode does not constrain the
instances. `definitions.md` § Instances says why. Call 2 can therefore run on records whose
failure mode is null, which is most security records.

## Runner: a Claude Code skill, not an API job

`mvp/skills/classify-incidents/`. A Claude Pro or Max subscription covers Claude Code; it
does not cover the Messages API, which bills separately through Console credits. At
prefiltered volumes — currently 347 candidates, not 1,803 — an in-session run needs no API
key and no credit.

The skill reads a versioned prompt from `mvp/prompts/`, pulls un-dispositioned records from
`mvp/state/queue.jsonl`, works in batches of 10–20 per turn, and appends verdicts to
`mvp/proposals/<prompt>.<date>.jsonl`. It is **resumable**: record ids already present in
the proposals file are skipped, so an interrupted run continues where it stopped.

An in-session run is less reproducible than a batch job, so the provenance has to
compensate. Every verdict records `prompt_id`, `prompt_version`, `model`, `run_date` and the
quotes it relied on. The prompt files and the proposal schema are written so that an
API/Batch runner — `claude-opus-5-5`, Batch API at half price, prompt caching on the shared
rubric prefix, structured outputs — can consume them unchanged if a key ever exists. Nothing
about the design assumes the in-session runner.

## Call 1 — extraction and gates

Prompt: `mvp/prompts/extract_gate.v2.md`. Output, one JSON object per record:

```json
{
  "source_id": "aiid", "source_record_id": "7",
  "n_ai_agents": 2, "agent_names": ["ClueBot NG", "Xqbot"],
  "interaction_present": true,
  "interaction_kind": "one-acting-on-another",
  "setting": "deployed", "stakes": "real",
  "environment_controlled_by": "nobody",
  "single_agent_counterfactual": "could_not",
  "multiplicity_role": "unreported",
  "cooperation_expected": "expected",
  "objective_relation": "identical",
  "confidence": "high",
  "uncertainty_reason": "",
  "quotes": {"interaction_present": "bots reverted each other's edits in a loop"},
  "prompt_id": "extract_gate", "prompt_version": "v2",
  "model": "...", "run_date": "2026-11-12"
}
```

Every extracted fact carries a verbatim quote from the record. A fact with no quote is not
a fact; the field is left null and the confidence drops.

Vocabularies: `single_agent_counterfactual` ∈ could / could_not / unclear ·
`multiplicity_role` ∈ load_bearing / incidental / unreported ·
`cooperation_expected` ∈ expected / unexpected / unclear · `objective_relation` ∈ identical /
mixed / opposing / unclear · `confidence` ∈ high / medium / low.

`multiplicity_role` is extracted on security records only — attacks, intrusions, abuse
campaigns. It is never null there: a fleet with no statement of its contribution is
`unreported`, not blank. `incidental` is the only value that requires evidence, and like
every other fact it requires a verbatim quote.

**Routing to review.** Anything with `confidence` below high, or any `unclear` in the three
gate fields, goes to the review queue rather than producing a label. Gate 1 is the weak
link — it asks for a counterfactual that the project's own reading notes leave open — so the
design never lets a model settle it silently.

The one exception is the security branch, where `definitions.md` sets a presumption: a
multi-agent attack whose `multiplicity_role` is `unreported` resolves to `could_not` instead
of routing to review. Everywhere else `unreported` has no meaning and `unclear` still
routes.

**Rules applied in code afterwards:**

- `single_agent_counterfactual`, on a security record, is overridden by
  `multiplicity_role`: `load_bearing` or `unreported` → `could_not`; `incidental` → `could`.
  The presumption is applied here, in code, not asked of the model
- `multi_agent` = `single_agent_counterfactual == "could_not"` AND `interaction_present`
- `evidence_type`: deployed + real stakes + environment not controlled by an experimenter →
  `real_world`; researcher-built or simulated environment → `synthetic`; narrow probe on
  real models with no environment → `lab`; no AI system run → `theoretical`
- `failure_mode`: the Gate 2 tree in `definitions.md`, over `cooperation_expected` and
  `objective_relation`. `opposing` yields no failure mode and does **not** remove the record
  from the index — Gate 1 alone decides scope

## Call 2 — instance assignment

Prompt: `mvp/prompts/assign_instances.v2.md`. Runs only on records that passed Gate 1. The
33 instance definitions fit in the prompt, so the model sees the actual definitions rather
than two-word names.

```json
{
  "source_id": "aiid", "source_record_id": "7",
  "instances": [
    {"instance_id": "I01", "confidence": "high",
     "quote": "each bot repeatedly undid the other's change"},
    {"instance_id": "I19", "confidence": "medium", "quote": "..."}
  ]
}
```

Output is the instance ids and their quotes, nothing else. The call does **not** emit a
failure mode, a risk factor, or an opinion about either: those come from call 1 and from a
later step, and deriving them from `instances.risk_id` would manufacture agreement between
two judgements that are supposed to be independent.

An empty instance list is a legitimate answer. So is a list of instances on a record whose
failure mode is null.

## Calibration, before any bulk run

A classifier is only as good as the set it is measured against, so the gold set comes first.

**Where it came from, and why it had to be re-reviewed.** The index began with an inventory
of incidents whose labels were all produced in AI-assisted sessions and never independently
checked. Calibrating against those labels would have measured agreement with an earlier
model pass rather than accuracy — the one thing a gold set must not do. Many of the rows also
failed the project's own verification rule: a minority carried an explicit verdict against a
primary source, several had notes but no verdict, some had no verification record at all,
and about half rested on a single source. Every one of those rows has since been re-judged
by a human against its sources, with the earlier label hidden until the verdict was formed.

`mvp/gold/multiagent_gold.csv`, 60 rows in four strata, all `to_judge`:

| stratum | n | what it is |
|---|---|---|
| `carried_over` | 27 | everything the index already held, each row judged from primary sources |
| `aiid_csetv1` | 6 | AIID's 5 `yes` and 1 `maybe` on `Multiple AI Interaction` — independent human annotators, but a different concept from Gate 1 |
| `queue_boundary` | 18 | prefilter candidates that tripped the keyword arm: something looked multi-agent |
| `queue_base_rate` | 9 | prefilter candidates with no signal at all, as a control |

The negative candidates are drawn from the prefilter queue, dated 2025–2026, excluding
anything AIID marks multi-agent (`mvp/gold/sample_negatives.py`, seeded). **They are
unscreened, not negative.** AIID applies no multi-agent label to 2025–2026 records at all —
CSETv1 stops in 2024 — so the absence of one carries no information, and a real multi-agent
incident sitting in the pool becomes a false negative that unfairly penalises the classifier.
Each needs a human verdict.

The draw deliberately oversamples the keyword arm: only 32 of 267 pool members trip it, so a
proportional sample would be almost all signal-free records. The consequence is a known bias
in the other direction — precision measured against this set is **pessimistic**, and it
describes the decision boundary rather than the population. `--hard 0` draws a base-rate
sample instead.

**Why negatives had to be added.** The original set was positives and nothing else, so
recall was measurable and precision was not: a classifier that labelled every record
multi-agent would have scored 100% on it. That hole was structural and separate from the
provenance problem — re-reviewing the positives would not have closed it.

**Reviewing.** `python mvp/gold/build_review.py` renders `mvp/out/gold_review.html`, a
self-contained worksheet that opens from disk. It shows each row's narrative, its sources as
links and any external labels, and asks the gate questions in order; the failure mode is
derived from the answers by the same tree the classifier uses. **The prior label is collapsed
behind a toggle**, so a verdict is formed before the earlier pass is seen — the point of the
review is independence. Verdicts persist in the browser, and **Export CSV** is the durable
record:

```
python mvp/gold/build_review.py --merge ~/Downloads/gold_reviewed.csv
```

folds them into `multiagent_gold.csv`, where they survive later rebuilds.

**Where the numbers live.** Every count in this section — how many rows are in scope, what
recall the cheap baselines achieve, what the classifier scores — is computed from the
reviewed gold file, and that file is the only authority. Figures are not restated here,
because a label changing in review would silently make this page wrong. Read them from the
file.

The reviewed set, as merged on 2026-11-13, is 60 rows judged `in`, `out` or `unclear`. The
security rows in it were judged before `definitions.md` settled the presumption for
coordinated attacks, so the in-scope count will move once they are re-judged against it;
see `OPEN.md` item 31. Until that is done, no accuracy figure computed from this file is
final.

**Baselines to beat.** Two, both cheap, and a classifier that cannot beat them is not worth
running:

- *An external human rater.* The MIT AI Risk Navigator's multi-agent facet, measured against
  the index's own incidents that also appear in AIID, misses a third of them. That figure is
  independent of the review, since it is about the rater's labels rather than ours.
- *The keyword prefilter arm alone.* It catches most of the positives for free, which sets
  the floor the model has to clear. Its recall is measured against the in-scope rows of the
  reviewed file and has to be recomputed whenever those change.

**End-to-end test.** AIID incident 7, the Wikipedia vandalism-prevention bot loop, is a
textbook miscoordination case: two bots with the same objective reverting each other. It
should pass Gate 1, be `cooperation_expected: expected` with `objective_relation: identical`,
come out FM1, and pick up I01 Incompatible Strategies. If it does not, the prompts are wrong.

## What the classifier may and may not write

It writes to `mvp/proposals/` only. It never edits a dossier. Promotion is
`python mvp/pipeline/run.py promote <source_id>:<record_id>`, which scaffolds a dossier with
every narrative section marked pending, and a human fills it in against the primary source.

`run.py check` enforces the boundary: a dossier with `multi_agent: true` whose
`multi_agent_label_source` is anything other than `ours` fails the build.
