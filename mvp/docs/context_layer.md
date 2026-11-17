# The context layer: read before you judge

How the index makes sure a record carries enough information to be classified. Decided
2026-11-14; resolves `OPEN.md` item 53.

## The problem

Every label the index assigns — in or out of scope, the failure mode, the risk instances —
is derived from a handful of facts: how many AI agents there were, whether they interacted,
what their number contributed, who controlled the setting, whether they cooperated, how
their objectives related, and what the mechanism was. `definitions.md` says which fact
feeds which decision.

The records do not contain those facts. All 347 queued records are under 600 characters,
median 406. The gold review showed what that costs: judged on headlines, five verdicts were
wrong and had to be reversed once the sources were read.

## The decision

**No label is derived from a fact nobody looked for.** Classification is split into two
steps that used to be one: first *read* the source for the gate facts and write down what it
says; then *judge* from what was written down. The first step is a new layer,
`mvp/context/`, and a record cannot be classified, promoted or asserted in a dossier until
its context row says enough has been read.

The rule turns on one distinction:

- **The source is silent.** It was read and does not say. That is a finding. The fact is
  `not_stated`, the answer to the gate question is `unclear`, and the record is *ready*: it
  has all the information it will ever have.
- **Nobody looked.** The fact is `unread`. Nothing may be derived from it, and the record
  is *not ready*.

Put plainly: "the source does not say" counts as an answer, because someone read the source
and can vouch that it is silent. "Nobody looked" does not count, because the fact may be on
the next page. A short record that leaves a fact out is the second case, not the first.
Until now the pipeline could not tell them apart, so thin input and a silent source both
came out as `unclear`.

## Why this design and not the alternatives

- **Enrich everything.** Thorough, and mostly wasted: about two thirds of queued records
  describe a single-agent event — a deepfake, a voice-cloning scam, one chatbot
  conversation — and are out of scope on that fact alone, which the record text already
  shows.
- **Classify first, enrich what comes back unclear.** Cheaper, but it lets a confident wrong
  answer through on thin text, and a thin record usually supports a confident wrong answer
  better than a careful one. The gold review's five reversals were all of this kind.
- **Read in two depths, gate on readiness.** Chosen. A cheap first reading of the record
  settles the single-agent majority; only what survives gets its source fetched; and a
  rule in code, not a model's confidence, decides whether a record may be classified.

## The layer

`mvp/context/<source_id>.jsonl`, one row per record, keyed like `mvp/records/`: the pair
`source_id`, `source_record_id`, and the same pair as one string, `record_key`
(`input_layer.md` § The record key). The newest row for a record wins; `run.py` reads it by
`record_key` when the row has one, else by the pair. It is the third machine-written
layer: `raw/` is verbatim, `records/` is normalised, `context/` is a *reading* — sourced
facts with quotes, assembled for judgement.

```json
{
  "source_id": "aiid", "source_record_id": "1731", "record_key": "aiid:1731",
  "agent_count": "none | one | several | unknown",
  "attack": true,
  "read": [{"url": "...", "depth": "secondary", "read_on": "2026-11-13"}],
  "facts": {
    "agents":       {"status": "stated",     "text": "...", "quote": "..."},
    "interaction":  {"status": "not_stated", "text": "...", "quote": ""},
    "multiplicity": {"status": "not_stated", "text": "...", "quote": ""},
    "setting":      {"status": "unread",     "text": "",    "quote": ""},
    "cooperation":  {"status": "unread",     "text": "",    "quote": ""},
    "objectives":   {"status": "unread",     "text": "",    "quote": ""},
    "mechanism":    {"status": "stated",     "text": "...", "quote": "..."}
  },
  "provenance": {"method": "enrich_context@v2", "model": "...", "run_date": "..."}
}
```

A manual record's row also carries `"manual": true` and `provenance: {"method": "manual"}`
(see Manual records below).

**Fact status**: `stated` (with a verbatim quote) · `not_stated` (read, silent) ·
`not_applicable` · `unread`.

**`agent_count`** counts **agents**, as `definitions.md` § What counts as an agent defines
them, not AI systems, products or companies. One product, platform, workflow or operator
can hold several agents, so one principal is not one agent. `one` needs the text to show a
single-agent kind of event: one chatbot conversation, one generated deepfake, one ranking
system. A named system whose insides the text does not describe is `unknown`.

**Read depth**, worst to best:

| depth | what was read |
|---|---|
| `unreadable` | the source could not be fetched |
| `record` | the source record's own text and nothing else |
| `secondary` | an aggregator's page in full — an AIID incident page, a registry entry — with the article it cites unread |
| `curator` | a write-up added by hand by the curator, who vouches for it; manual records only |
| `primary_partial` | part of the primary source |
| `primary_full` | the primary source, in full |

## What each decision needs

| decision | facts that must be resolved | |
|---|---|---|
| scope (Gate 1) | `agents`, `interaction`; plus `multiplicity` on an attack | |
| evidence type | `setting` | |
| failure mode (Gate 2) | `interaction`, `cooperation`, `objectives` | |
| instances | `mechanism` | |

"Resolved" means `stated` or `not_stated`, never `unread`.

**The shortcut that makes this affordable.** A source that shows one agent only, or none,
is out of scope on that fact alone. `agent_count` of `one` or `none`, stated, settles scope
as **out**, and the other three decisions do not arise. Such a record is not judged and is
not counted among the records that can be judged; it is finished.

**The flag rule.** The shortcut may rest on the record text alone only for a record that
nothing but the `unasked` arm put in the queue (called `unclassified` before 2026-11-16;
see `input_layer.md` § prefilter). A record the `label` or `keyword` arm
queued is *flagged*: someone else's rater, or a multi-agent term in its text, already points
the other way. A flagged record that the record pass calls `one` or `none` still goes to the
source pass, and the shortcut applies only once a reading of depth `secondary` or better
confirms it. A dossier source with no queue row counts as flagged.

## Readiness

`python mvp/pipeline/run.py readiness` reports one level per decision for every queued
record and every dossier source, and writes `mvp/state/readiness.jsonl`, one row per
record with its `record_key`.

| level | meaning | what it permits |
|---|---|---|
| `ready` | primary source read in full, facts resolved | any label; `verification: verified` |
| `provisional` | facts resolved from a partial or secondary reading | a label, marked as resting on that reading; never `verified` |
| `not_ready` | a needed fact is unread, or nothing usable was read | nothing — enrich first |
| `not_needed` | the record is out of scope | — |

Scope `ready` has two meanings that are kept apart in the counts: settled **out** by the
shortcut (finished), or ready **to be judged** by Gate 1. Only the second is "can be judged".

## Manual records

The curator can add incidents by hand: `run.py update --manual DIR` reads a directory of
plain write-ups (see `input_layer.md`). These records skip the gate on the curator's word.
The curator is the human whose verdict, by project rule, is the only thing that puts an
incident in scope.

Each manual record gets a context row written by the pipeline, not by a model:
`"manual": true`, `agent_count: "several"`, one `read` entry of depth `curator`,
`provenance: {"method": "manual"}`, and every fact `unread` except what that settles.

`readiness` reports such a row as:

| decision | level | why |
|---|---|---|
| scope | `ready` | added by hand: in scope on the curator's word |
| evidence type, failure mode, instances | `provisional` | to be judged from the curator's write-up |

The classifier skips the record pass and the Gate 1 verdict for them, and still proposes
evidence type, failure mode and instances from the write-up. `curator` is not a primary
reading: it ranks below `primary_partial`, and a dossier that rests on it may not be
`verification: verified`.

## How it is enforced

- **The classifier** does not run call 1 on a record whose scope is `not_ready`. It sends
  the record to enrichment instead (`SKILL.md`).
- **`run.py promote`** refuses a `not_ready` record unless given `--force`.
- **`run.py check`** fails a dossier that asserts `multi_agent` true or false with no source
  read far enough to decide scope, and fails one marked `verified` whose scope rests on a
  partial, secondary or `curator` reading. It warns on a `provisional` dossier. It also
  validates every context row: the vocabularies (including depth `curator` and the `manual`
  flag), a `read` entry, and a quote for every `stated` fact.

## The enrichment routine

Who does what: `run.py` (a script) writes the queue and computes readiness. The two passes
are a model reading text, run by the `/classify-incidents` skill in Claude Code with the
prompt `mvp/prompts/enrich_context.v2.md` (v1 is kept, unchanged, for the record). Each pass
appends rows to `mvp/context/<source>.jsonl`. The second pass runs only on what the first
leaves open.

1. **Record pass**, over every queued record, no fetching. Reads the record text and sets
   `agent_count`, `attack`, and whatever facts the text states. An unflagged record with
   `agent_count` of `one` or `none` is finished.
2. **Source pass**, on records with `agent_count` of `several` or `unknown`, and on flagged
   records the record pass called `one` or `none`. Fetches the record's page and the primary
   source it cites, reads them for the seven facts, and records the depth reached. A source
   that cannot be fetched is recorded as `unreadable`; it is not guessed.

Enrichment is an inference step, so it carries a proposal's provenance — `prompt_id`,
`prompt_version`, `model`, `run_date` — and a quote per stated fact. `reuse_status` in the
registry governs what may be stored: where a source asks to be contacted before reuse, the
row holds a paraphrase and one short quote, not bulk text.

## Where things stand

Measured 2026-11-14 with `run.py readiness`, before the flag rule and the manual source:

| pool | records | scope `ready` | `provisional` | `not_ready` |
|---|---|---|---|---|
| queue | 347 | 3 | 11 | **333** |
| dossier sources | 27 | 13 | 13 | 1 |

**96% of the queue cannot be classified yet**, and no enrichment run has been made.

On 2026-11-16, after the third prefilter arm was widened to `unasked`, the queue holds
1,133 records: scope `ready` 319, `provisional` 42, `not_ready` 772. The 772 are the newly
queued records, none of them read yet. The 361 queued before kept their readiness. The
layer was seeded with the 41 rows the gold review produced (`mvp/pipeline/seed_context.py`);
`mvp/gold/context/` stays frozen as the record of what the reviewer saw.

Of the 26 dossiers, 11 rest on a secondary reading: the Agent Incident Registry entry was
read, the article it cites was not. They carry a warning from `check` and none is marked
`verified`.

## Limits

- **The seeded rows carry one quote per row, not one per fact.** `check` exempts them from
  the per-fact quote rule and will not exempt anything written by the enrichment prompt.
- **`agent_count`, `attack` and read depth on the seeded rows were set by hand**, listed in
  `seed_context.py` so they can be checked.
- **The record pass is itself a judgement** and can wrongly call a multi-agent record
  single-agent, which would drop it silently. v1 made this likelier by counting AI systems:
  a product or operator running several agents came out `one`. v2 counts agents, and the
  flag rule sends every flagged record to the source pass, so only unflagged records can be
  dropped on record text. It still has to be measured on the gold set before it runs over
  the queue: no gold row judged `in` may come out `one` or `none`.
- **Readiness says the reading was done, not that it was done well.** A context row can be
  wrong. The human who promotes still reads the source.
