# Classifier design

Two model calls produce the labels, and they run only on records the context layer marks
ready: a record is read for the gate facts first and judged second
(`0.2/docs/context_layer.md`). Everything the calls emit is a **proposal**; a human
promotes. See `0.2/docs/definitions.md` for the definitions the classifiers apply.

Records the curator added by hand (`update --manual`) are already in scope on the curator's
word. For them call 1 gives no Gate 1 verdict; it extracts only the Gate 2 and evidence-type
facts, and call 2 runs as usual. Their labels rest on a `provisional` reading.

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
derive   rules in code (0.2/pipeline/derive.py), run by `run.py derive`
           -> multi_agent      rule over gate 1 + interaction_present
           -> evidence_type    rule over setting, stakes, who controlled the environment
           -> failure_mode     rule: the gate 2 tree, over the FM definitions
call 2   assign instance ids               (records in scope: by the rules, or by a person)
           -> instances        descriptive detail, assigned independently
```

The two calls answer different questions and neither feeds the other. Call 1 produces the
labels from a handful of extracted facts. Call 2 describes the incident more finely against
the 36 instance definitions in `0.2/taxonomy/instances.csv`, which do not fit in call 1's prompt and would skew its
judgement if they did — a model that has just read "Swarm Attacks" is readier to call the
next record a swarm.

**Instances do not determine the failure mode**, and the failure mode does not constrain the
instances. `definitions.md` § Instances says why. Call 2 can therefore run on records whose
failure mode is null, which is most security records.

## Runner: a Claude Code skill, not an API job

`0.2/skills/classify-incidents/`. A Claude Pro or Max subscription covers Claude Code; it
does not cover the Messages API, which bills separately through Console credits. At
prefiltered volumes — 1,133 candidates on 2026-11-16, most of them settled by the cheap
record pass before any judging — an in-session run needs no API key and no credit.

The skill reads a versioned prompt from `0.2/prompts/`, pulls un-dispositioned records from
the ledger (rows with `queued` true), works in batches of 10–20 per turn, and appends them to
`0.2/proposals/<prompt>.<date>.jsonl`. Every row it appends carries `record_key`. It is
**resumable**: a record whose `record_key` already has a row for that prompt is skipped, so
an interrupted run continues where it stopped.

**Proposals hold model output only.** No derived label is written into a proposal. The
labels are generated state: `python 0.2/pipeline/run.py derive` reads the newest
`extract_gate` proposal of every record, applies the rules, and writes the ledger's derive
columns. They are rewritten on every run, so a rule change reaches every
record at once and no stale label survives in a proposal.

**Which model.** Every prompt that judges an incident runs on `claude-opus-5-5`:
`enrich_context` (record and source pass), `extract_gate`, `assign_instances`, and their
gold calibrations. Decided 2026-11-17. On the gold set Sonnet gave Opus's Gate 1 labels on
the same inputs, but in the record pass it answered `agent_count: none` three times as
often, and on an unflagged record that closes it unseen (`gate1_accuracy.md`). Missing an
incident costs more than the model does. Sonnet does the work that judges nothing:
fetching pages verbatim, discovery searches, copying the Navigator list, code, docs and
reports.

An in-session run is less reproducible than a batch job, so the provenance has to
compensate. Every verdict records `prompt_id`, `prompt_version`, `model`, `run_date` and the
quotes it relied on. The prompt files and the proposal schema are written so that an
API/Batch runner — `claude-opus-5-5`, Batch API at half price, prompt caching on the shared
rubric prefix, structured outputs — can consume them unchanged if a key ever exists. Nothing
about the design assumes the in-session runner.

## Call 1 — extraction and gates

Prompt: `0.2/prompts/extract_gate.v4.md`. Older verdicts keep the version they were made with; the dataflow map counts them. Output, one JSON object per record:

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
  "cooperation_occurred": "no",
  "cooperation_expected": "expected",
  "objective_relation": "identical",
  "confidence": "high",
  "uncertainty_reason": "",
  "quotes": {"interaction_present": "bots reverted each other's edits in a loop"},
  "prompt_id": "extract_gate", "prompt_version": "v4",
  "model": "...", "run_date": "2026-11-12"
}
```

Every extracted fact carries a verbatim quote from the record. A fact with no quote is not
a fact; the field is left null and the confidence drops.

Vocabularies: `single_agent_counterfactual` ∈ could / could_not / unclear ·
`multiplicity_role` ∈ load_bearing / incidental / unreported ·
`cooperation_occurred` ∈ yes / no / unclear ·
`cooperation_expected` ∈ expected / unexpected / unclear · `objective_relation` ∈ identical /
mixed / opposing / unclear · `confidence` ∈ high / medium / low.

`multiplicity_role` is extracted on security records only — attacks, intrusions, abuse
campaigns. It is never null there: a fleet with no statement of its contribution is
`unreported`, not blank. `incidental` is the only value that requires evidence, and like
every other fact it requires a verbatim quote.

**Routing to review.** A record goes to review, rather than producing a label, when:

- its `confidence` is below high; or
- a Gate 1 field is `unclear` or null: `single_agent_counterfactual`, and
  `interaction_present` on a non-security record; or
- it is in scope and a Gate 2 field is `unclear` where it decides the branch (below); or
- it is in scope and its evidence type cannot be derived.

Gate 1 is the weak link — it asks for a counterfactual that the project's own reading notes
leave open — so the design never lets a model settle it silently.

Two exceptions, both on the security branch. `interaction_present` is not a review reason
there, because multiplicity stands in for it. And `definitions.md` sets a presumption: a
multi-agent attack whose `multiplicity_role` is `unreported` resolves to `could_not`
instead of routing to review — but only when the record does not show fewer than two AI
agents and the model did not answer `could` (decided 2026-11-16). When the presumption
does not fire, an `unclear` counterfactual routes as usual. Everywhere else `unreported`
has no meaning.

**The derived verdict.** The ledger's derive columns, on every record with an
`extract_gate` proposal (until 0.2, `state/verdicts.jsonl`): `rules_status` (`in_scope`,
`out_of_scope` or `review`), `gate1` (`in`, `out`, `review`, or `curator` for a manual
record), `why_a_person`, `by_presumption`, `rules_version`, and the labels
(`rules_multi_agent`, `rules_evidence_type`, `rules_failure_mode`,
`rules_instances_presumed`). `labels_settled` is `false` for a review item: its labels hold
only if a person confirms the facts, so nothing reads them as settled. They are never an
authority: they become proposals, and a person decides scope on `0.2/review/1_records.xlsx`
and the incident's labels on `0.2/review/2_incidents.xlsx`.

**Rules applied in code afterwards.** `0.2/pipeline/derive.py` is the single authority. It
is a pure function, `derive(gate_row)`, with a self-test (`python 0.2/pipeline/derive.py
--selftest`) that covers every branch. `run.py derive` and `0.2/gold/score_gate1.py` both
call it, so the pipeline and the gold measurement apply the same rules. In words:

- `single_agent_counterfactual`, on a security record, is overridden by
  `multiplicity_role`: `load_bearing` → `could_not`; `incidental` → `could`; `unreported` →
  `could_not` when the presumption fires, else the model's answer stands. The presumption
  is applied here, in code, not asked of the model
- `multi_agent` = `single_agent_counterfactual == "could_not"` AND `interaction_present`.
  On a security record `interaction_present` is not required: multiplicity stands in for it
- `instances_presumed`, on a security record that passed Gate 1: `unreported` → `I28;I29`.
  Call 2 still runs and may add quoted instances; a quoted I28 or I29 replaces the presumed
  pair. Presumed and quoted instances are never stored in the same field
- `evidence_type`, decided by `setting` first: `none` → `theoretical`; `narrow_probe` →
  `lab`; `researcher_built` → `synthetic`, whatever the stakes; `deployed` with `real`
  stakes and the environment controlled by `nobody` or the `operator` → `real_world`. Any
  other combination, including `environment_controlled_by: unclear`, gives no evidence type
  and, on an in-scope record, the review reason "evidence type not derivable"
- `failure_mode`: the Gate 2 tree in `definitions.md`. `cooperation_occurred == "yes"` AND
  `cooperation_expected == "unexpected"` → FM3. Otherwise by `objective_relation`:
  `identical` → FM1, `mixed` → FM2, `opposing` → none. An `unclear` routes to review only
  where it decides the branch: `cooperation_occurred` always, `cooperation_expected` only
  when cooperation occurred, `objective_relation` only off the FM3 branch. `opposing` yields
  no failure mode and does **not** remove the record
  from the index — Gate 1 alone decides scope

## Call 2 — instance assignment

Prompt: `0.2/prompts/assign_instances.v2.md`. Runs only after a person has decided scope,
on the records a person has put in scope. They are listed by
`python 0.2/pipeline/run.py instances-due`, which writes `0.2/state/instances_due.jsonl`:
every dossier with `multi_agent: true` and label source `ours` whose `instances` list is
empty and none of whose sources has an instance proposal, and every record a person
decided `in` on the scope sheet (`0.2/review/`), promoted or not — each with no instance
proposal. A hand-added record counts as decided `in`. A verdict `run.py derive` settles
`in_scope` gets no call 2 until a person decides it in. Instances follow the human's
scope decision, not only the model's. An instance proposal for a human-confirmed record is
a proposal like any other: it never edits the dossier. The update run's Review step shows
the count.

The 36 instance definitions fit in the prompt, so the model sees the actual definitions
rather than two-word names.

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

`0.2/gold/multiagent_gold.csv`, drawn as 60 rows in four strata; after two review rounds
58 rows remain, each with a human verdict (see `gold_set.md`):

| stratum | n | what it is |
|---|---|---|
| `carried_over` | 27 | everything the index already held, each row judged from primary sources |
| `aiid_csetv1` | 6 | AIID's 5 `yes` and 1 `maybe` on `Multiple AI Interaction` — independent human annotators, but a different concept from Gate 1 |
| `queue_boundary` | 18 | prefilter candidates that tripped the keyword arm: something looked multi-agent |
| `queue_base_rate` | 9 | prefilter candidates with no signal at all, as a control |

*Note, 2026-11-17: the prefilter's arms were replaced by `basis` and `flags`; "keyword arm" in this section means the `keyword` flag.*

The negative candidates are drawn from the prefilter queue, dated 2025–2026, excluding
anything AIID marks multi-agent (`0.2/gold/sample_negatives.py`, seeded). **They are
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

**Reviewing.** `python 0.2/gold/build_review.py` renders `0.2/out/gold_review.html`, a
self-contained worksheet that opens from disk. It shows each row's narrative, its sources as
links and any external labels, and asks the gate questions in order; the failure mode is
derived from the answers by the same tree the classifier uses. **The prior label is collapsed
behind a toggle**, so a verdict is formed before the earlier pass is seen — the point of the
review is independence. Verdicts persist in the browser, and **Export CSV** is the durable
record:

```
python 0.2/gold/build_review.py --merge ~/Downloads/gold_reviewed.csv
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
see `OPEN.md` item 31. The second review round of 2026-11-13 filled `multiplicity_role` on
the security rows, but item 31 has not been formally closed, so treat accuracy figures from
this file as provisional until it is.

**Scoring the classifier.** `python 0.2/gold/score_gate1.py` scores a blind
`extract_gate` run over the gold rows (`0.2/out/calibration/`), with the labels derived by
`derive.py`, the same code the pipeline runs. It reports all rows, and separately the rows
the rules settle without review. Figures in `0.2/docs/gate1_accuracy.md`.

**Baselines to beat.** Two, both cheap, and a classifier that cannot beat them is not worth
running:

- *An external human rater.* The MIT AI Risk Navigator's multi-agent facet, measured against
  the index's own incidents that also appear in AIID, misses a third of them. That figure is
  independent of the review, since it is about the rater's labels rather than ours.
- *The keyword prefilter flag alone* (the `keyword` arm until 2026-11-17). It catches most of the positives for free, which sets
  the floor the model has to clear. Its recall is measured against the in-scope rows of the
  reviewed file and has to be recomputed whenever those change.

**End-to-end test.** AIID incident 7, the Wikipedia vandalism-prevention bot loop, is a
textbook miscoordination case: two bots with the same objective reverting each other. It
should pass Gate 1, be `cooperation_occurred: no` with `objective_relation: identical`,
come out FM1, and pick up I01 Incompatible Strategies. If it does not, the prompts are wrong.

**Status on 2026-11-16: not yet passed.** In the first queue run aiid:7 came out a review
item, not FM1. Its reading is the seeded gold row, which left setting, cooperation and
objectives `unread`, so evidence type cannot be derived and Gate 2 is unclear. The test is
meaningful only after a source pass reads the cited reports for those facts.

## What the classifier may and may not write

It writes to `0.2/proposals/` only. It never edits a dossier, and it never decides scope:
the rules' `in_scope` is a proposal. A person decides scope on the records sheet
(`0.2/review/1_records.xlsx`); a record decided `in` with `duplicate_of` `new` (or
`python 0.2/pipeline/run.py promote <mig_key>`) gets a dossier with every narrative section
marked pending, its labels proposed from the ledger, and a human writes the prose against
the primary source and decides the labels on `0.2/review/2_incidents.xlsx`.

`run.py check` enforces the boundary: a dossier with `multi_agent: true` whose
`multi_agent_label_source` is anything other than `ours` fails the build.
