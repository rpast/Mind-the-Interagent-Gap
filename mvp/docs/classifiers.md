# Classifier design

Two model calls produce three labels. Everything they emit is a **proposal**; a human
promotes. See `mvp/docs/definitions.md` for the definitions the classifiers apply.

## Why this shape

**Not a trained model.** There are 27 positive examples in total. The decision is a
definitional counterfactual, not a surface pattern. Every verdict needs a citable rationale
and a quote, because it will be argued with. The label set is still moving. A fine-tuned or
BERT-style classifier needs hundreds to thousands of labels, returns no reasoning, and would
have to be retrained every time a definition is sharpened.

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
           -> failure_mode     rule: the gate 2 tree
call 2   assign instance ids               (only if the record passed the gate)
           -> failure mode and risk factors derived from instances.risk_id
           -> cross-checked against call 1's tree result
```

Two model calls, three labels, and a free consistency check: the failure mode is reached
twice by independent routes, and a disagreement is a review signal rather than a tiebreak.

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

Prompt: `mvp/prompts/extract_gate.v1.md`. Output, one JSON object per record:

```json
{
  "source_id": "aiid", "source_record_id": "7",
  "n_ai_agents": 2, "agent_names": ["ClueBot NG", "Xqbot"],
  "interaction_present": true,
  "interaction_kind": "one-acting-on-another",
  "setting": "deployed", "stakes": "real",
  "environment_controlled_by": "nobody",
  "single_agent_counterfactual": "could_not",
  "cooperation_expected": "expected",
  "objective_relation": "identical",
  "confidence": "high",
  "uncertainty_reason": "",
  "quotes": {"interaction_present": "bots reverted each other's edits in a loop"},
  "prompt_id": "extract_gate", "prompt_version": "v1",
  "model": "...", "run_date": "2026-11-12"
}
```

Every extracted fact carries a verbatim quote from the record. A fact with no quote is not
a fact; the field is left null and the confidence drops.

Vocabularies: `single_agent_counterfactual` ∈ could / could_not / unclear ·
`cooperation_expected` ∈ expected / unexpected / unclear · `objective_relation` ∈ identical /
mixed / opposing / unclear · `confidence` ∈ high / medium / low.

**Routing to review.** Anything with `confidence` below high, or any `unclear` in the three
gate fields, goes to the review queue rather than producing a label. Gate 1 is the weak
link — it asks for a counterfactual that the project's own reading notes leave open — so the
design never lets a model settle it silently.

**Rules applied in code afterwards:**

- `multi_agent` = `single_agent_counterfactual == "could_not"` AND `interaction_present`
- `evidence_type`: deployed + real stakes + environment not controlled by an experimenter →
  `real_world`; researcher-built or simulated environment → `synthetic`; narrow probe on
  real models with no environment → `lab`; no AI system run → `theoretical`
- `failure_mode`: the Gate 2 tree in `definitions.md`

## Call 2 — instance assignment

Prompt: `mvp/prompts/assign_instances.v1.md`. Runs only on records that passed Gate 1. The
36 instance definitions fit in the prompt, so the model sees the actual definitions rather
than two-word names.

```json
{
  "source_id": "aiid", "source_record_id": "7",
  "instances": [
    {"instance_id": "I01", "confidence": "high",
     "quote": "each bot repeatedly undid the other's change"},
    {"instance_id": "I19", "confidence": "medium", "quote": "..."}
  ],
  "no_failure_mode": false
}
```

Failure mode and risk factors are derived in code from `instances.risk_id` — never taken
from the model directly. This matters: in the PoC, a row's failure modes and risk factors
had to equal exactly the set reachable through its instances, and a label that cannot be
routed through an instance cannot be used at all.

`no_failure_mode: true` is a legitimate answer. Most security events carry risk factors
only.

**Cross-check.** The failure mode derived from the instances is compared with the one the
Gate 2 tree produced in call 1. Agreement raises confidence; disagreement flags the record
for review and is recorded in the proposal. Neither route wins automatically.

## Calibration, before any bulk run

The gold set:

| part | n | role |
|---|---|---|
| The 27 migrated PoC incidents | 27 | positives, with failure modes from `poc/docs/mapping_2026-10-26.md` |
| AIID CSETv1 `yes` — incidents 7, 19, 25, 44, 125, plus `maybe` 47 | 6 | independent external positives, and a test of whether CSETv1 means what we mean |
| MIT Navigator candidates not already ours | 22 | unscreened, mixed |
| Stratified sample of AIID records judged out of scope | ~50 | negatives |

Report recall and precision **per gate**, not just end to end, so it is visible whether a
miss came from extraction or from the counterfactual.

**Baselines already measured, to beat:**

- The MIT Navigator's rater: **33% false negative** on the 9 of our incidents in AIID.
- The keyword prefilter arm alone: **78% recall** (21 of 27) against our own positives. The
  6 it misses are AIR-2025-0019, AIR-2025-0027, AIR-2025-0068, AIR-2025-0136, AIR-2026-0180
  and LW-03.

A classifier that does not beat 78% recall is not worth running, because the keyword net is
free.

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
