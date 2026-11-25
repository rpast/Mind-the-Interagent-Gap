# Input layer

How incidents get in: the sources, the record store, the dossiers, and the one command that
runs it.

## The shape

Two levels, because one incident appears in several sources and a single-level store
duplicates it the first time a second adapter runs.

```
0.2/raw/<source>/          verbatim fetch output. Never hand-edited.
0.2/records/<source>.jsonl normalised, append-only, content-hashed. Machine-written.
0.2/context/<source>.jsonl what each source says about the gate facts. A reading, with quotes.
0.2/incidents/<ID>.md      the curated record. Hand-edited. One dossier per incident.
0.2/out/incident_index.csv a flat index generated from the dossiers.
```

A record is what one source said, when we fetched it. A dossier is what we believe happened,
citing the records that attest it.

Hand-made label files are not fetch output, so they do not go in `raw/`. They live in
`0.2/registry/labels/`: today one file, `navigator_multiagent.tsv`, the MIT AI Risk
Navigator's multi-agent facet, copied by hand on 2026-11-09 (see its `README.md`).

### The record key

A record's identity is the pair `(source_id, source_record_id)`; `source_record_id` is
the source's own id, the AIID `incident_id` for AIID. Every row in `records/`,
`context/`, `proposals/`, `state/readiness.jsonl` and `state/instances_due.jsonl` carries
the pair, every row of the ledger (`ledger/ledger.csv`) carries the key,
and also one string, `record_key`, `"<source_id>:<source_record_id>"`, e.g. `"aiid:1604"`.
It is the same string `run.py promote` takes. `run.py` builds it in one place
(`record_key`, `split_key`). It reads a row by `record_key` when the row has one, else by
the pair, so a proposal written without it still counts. `check` fails a row whose
`record_key` does not match its pair.

### A record row

```json
{
  "source_id": "aiid", "source_record_id": "1604", "record_key": "aiid:1604",
  "title": "...", "text": "...", "date": "2026-10-17", "url": "...",
  "external_labels": [{"source": "aiid", "namespace": "CSETv1", "field": "...",
                       "value": "no", "fetched_at": "2026-11-15"}],
  "meta": {"has_classification": true, "namespaces": ["..."]},
  "fetched_at": "2026-11-15",
  "raw_ref": {"path": "0.2/raw/aiid/incidents.jsonl", "id_field": "_id",
              "id": "6...", "fetched_at": "2026-11-15"},
  "content_hash": "sha256:..."
}
```

`raw_ref` says which raw row the record was built from: the raw file, repo-relative; the
source's own id field and its value (`_id` for AIID); and the fetch date. For a manual
record it names the copy in `raw/manual/`. For the records carried over from the PoC it
names `poc/data/incidents.csv` and the `event_id`. It is not part of the content hash.

## The update routine

```
python 0.2/pipeline/run.py update                       # AIID baseline refresh, from the saved snapshot
python 0.2/pipeline/run.py update --refetch             # fetch AIID afresh; needs the token and network
python 0.2/pipeline/run.py update --manual DIR          # also add incidents written up by hand in DIR
python 0.2/pipeline/run.py update --discover            # also run discover: a placeholder, not built yet
python 0.2/pipeline/run.py update --token-file F        # read the AIID token from F
python 0.2/pipeline/run.py serve [--port 8765]          # the front end, on 127.0.0.1 only
```

The old three modes (`labelled-only`, `aiid-full`, `all-sources`) are gone. By default
`update` refreshes the AIID baseline: it reuses the snapshot already in `0.2/raw/aiid/` and
fetches only with `--refetch`. It then normalises, prefilters, computes readiness, builds
the index and renders the pages.

AIID is the **baseline** source. Everything else is a **discovery** source, searched for
incidents AIID does not carry — which matters, because 18 of the 27 incidents the project
started with are absent from AIID entirely, including all 7 AI Village rows. Discovery has
no working module yet; see **discover** below.

Each stage is also runnable alone: `fetch`, `normalise`, `discover`, `prefilter`, `readiness`,
`derive`, `instances-due`, `promote`, `index`, `viz`, `check`.

An `update` run walks: sources, discover, fetch, manual, normalise, prefilter, read,
readiness, judge, **derive**, review, check, index. `derive` comes right after judge: it
applies the labelling rules (`0.2/pipeline/derive.py`) to the newest `extract_gate`
proposal of every record and writes the ledger's derive columns. The review step also runs
`instances-due` and shows how many records in scope still have no instance proposal.

### Who does each step

Most steps are `run.py`, a script. Two are not:

| step | done by | produces |
|---|---|---|
| fetch, normalise, prefilter, readiness, derive, instances-due, index, viz, check | `run.py` | files under `raw/`, `records/`, `state/`, `out/`; `check` produces only an exit code |
| read the sources, judge | a model, through the `/classify-incidents` skill in Claude Code | rows in `context/`, verdicts in `proposals/` |
| promote, write up | a person, helped by `run.py promote` | a dossier in `incidents/` |
| work orders | a person, following `state/work_orders.md` | records pasted back for a source no script can reach |

### The front end

`run.py serve` starts a local server on `http://127.0.0.1:8765/` and serves the pipeline
map page with live numbers. From the page you can start an `update` run and watch each step
light up. When a step needs a person — reading sources, judging, reviewing proposals — the
run waits, the page says what to do (normally run `/classify-incidents` in Claude Code, or
`run.py promote`), and you press continue or skip. It binds to 127.0.0.1 only, accepts
requests only from its own page, and runs no shell commands. Run state is kept in
`0.2/state/run.json`, so a reload picks up where it was.

### Manual incidents

`update --manual DIR` adds incidents the curator has written up by hand. `DIR` holds plain
`.txt` or `.md` files.

- One file is one incident, unless it has two or more headings of the same top level
  (`# ` or `## `); then each heading starts an incident.
- Title is the heading, or the first non-empty line. Text is the rest, verbatim. Date is the
  first ISO date in the text, full or partial, else empty. URL is the first `http(s)` link,
  else empty.
- A verbatim copy of each file goes to `0.2/raw/manual/`. Records go to
  `0.2/records/manual.jsonl` by the normal append and content-hash path, with
  `meta.manual: true` and the original path.
- Each record goes straight into the queue (`basis: "manual"`, whatever the prefilter says)
  and gets a context row in `0.2/context/manual.jsonl` with read depth `curator`.

They land on the **ready, in-scope** list on the curator's word: the curator is the human
whose verdict puts an incident in scope. The classifier skips Gate 1 for them and proposes
only the failure mode, evidence type and instances, marked provisional. A dossier still
needs `run.py promote` and a hand write-up, and it may not be `verified` on the write-up
alone. See `context_layer.md` § Manual records.

## Stages

**fetch** dispatches on the registry's `adapter` column. AIID imports
`0.2/pipeline/fetch_aiid.py` as a library and never modifies it. In `update` it reuses the
saved AIID snapshot unless `--refetch` is given. A refetch with no token, or with no
network, fails the step and offers to retry or to fall back on the snapshot.

**discover** is a **placeholder**. Searching the discovery sources for new incidents is not
built yet: `update --discover` reports the step as "not built yet" and carries on. Work
orders are a sub-step of discover. A work order is a note **per source**, not per incident,
written to `0.2/state/work_orders.md`: for a source no script can reach, it says what to
search, where, and what to paste back. `run.py discover` still writes these notes on its
own, but an `update` run does not depend on them. A human-in-the-loop source is a stage,
not a gap.

**normalise** writes one record per source record. AIID needs a join: `incidents.jsonl` at
depth 0 carries no classifications, and `classifications.jsonl` has no `incident_id` — its
only path back is the expanded `incidents` list, so the join is on `incidents[]._id`. It
harvests the `Multiple AI Interaction` attribute from the consensus `CSETv1` namespace *and*
all three `CSETv1_Annotator-*` namespaces, so rater disagreement stays visible. It also
adds the Navigator's label from `0.2/registry/labels/navigator_multiagent.tsv`. What the two
AIID files hold is described in `0.2/pipeline/fetch_aiid.md`.

**prefilter** queues a record for one reason (its `basis`) and flags it for another (its
`flags`):

| basis | a record is queued when | 2026-11-18 |
|---|---|---|
| `recent` | it is an AIID record dated on or after 2024-01-01 that no outside rater has answered "not multi-agent" on | 1,099 |
| `frozen` | its `record_key` is on the frozen list, `0.2/registry/frozen_pre2024.csv` | 34 |
| `manual` | the curator added it by hand | 0 |

The queue is 1,133 records. Each has exactly one basis.

**An outside answer is acted on (decided by the curator, 2026-11-18).** For a 2024+ record
an outside rater has already answered the multi-agent question on, its answer stands: `no`
(every `Multiple AI Interaction` label on it says no, and the Navigator does not list it)
leaves the record out of the queue; `yes` or `maybe` queues it and flags it. A
disagreement between annotators counts as yes. Only unlabelled records are queued for our
own reading. The rule is `outside_says_no()` in `run.py`. On 2026-11-18 it leaves out 4
records, each on one CSETv1 annotator's `no`: `aiid:631`, `633`, `642`, `676`. This is a
deliberate exception to the principle that an outside label never decides scope: since 2024
there is almost no outside labelling, apart from the Navigator list copied by hand, so the
cost is small, and an answer someone has already given is not asked again.

| flag | a queued record is flagged when | 2026-11-17 |
|---|---|---|
| `label` | any external label says `yes` or `maybe`, including one dissenting annotator, or the Navigator lists it | 39 |
| `keyword` | the recall-first regex net, lifted from the exploratory notebook, matches its title or text | 64 |

A flag never queues a record by itself. A record can carry both
flags, so the two counts add up to more than the 93 flagged records.

**Why the prefilter was simplified (2026-11-17).** It used to be a union of three arms,
`label`, `keyword` and `unasked`, and `unasked` skipped an AIID record that CSETv1 had
answered `no`. CSETv1 stops in 2024, so for 2024 onwards the arms came to "every AIID
record". On 2026-11-17 four records that a CSETv1 `no` had kept out were queued; on
2026-11-18 the curator decided an outside answer is acted on, and they are out again (see
above). The 1,133 records queued
before keep their readiness; the 34 dated before 2024 were copied once into the frozen
list, which is now kept by hand. Normalise still harvests the CSETv1 labels into
`external_labels` exactly as before; they just no longer decide queue membership. For 2024
onwards the only multi-agent signals are our own classification and the MIT Navigator list
(`0.2/registry/labels/navigator_multiagent.tsv`, copied by hand and refreshed from time to
time).

The rules are constants at the top of `0.2/pipeline/run.py`: `KEYWORD_TERMS` (the regexes),
`RECENT_FROM` (the date) and `MA_POSITIVE` (the label values that count). The queue row
records the `basis` and the `flags` of each record. A flagged record may not be dismissed
on its record text alone (`context_layer.md` § The flag rule). Manual records are queued
with `basis: "manual"`, whatever the prefilter says.

Measured, which is why there are two flags and not one: the MIT Navigator's rater has a
**33% false-negative rate** on the 9 of our incidents that are in AIID. The keyword flag's
recall is unmeasured; an earlier 78% figure was withdrawn (`0.2/docs/gate1_accuracy.md`).

**readiness** reports, per record, whether enough has been read to classify it, from the
context layer. A record whose scope is `not_ready` is not classified and cannot be promoted
without `--force`. See `0.2/docs/context_layer.md`.

**classify** is not part of `run.py`. It is a Claude Code skill, `/classify-incidents`,
because a Pro subscription covers Claude Code and not the Messages API. See
`0.2/docs/classifiers.md`.

**viz** renders one page into `0.2/out/` from the live counts. `pipeline_flow.html` is
the plain-language map of the whole pipeline: every step is a box, the wires show what flows
between them, and clicking a box explains it. The same page, served by `run.py serve`, is
the front end: it can start a run and shows it step by step. Opened from disk it shows the
numbers of the last build but cannot run anything.

**promote** scaffolds a dossier from a record, with every narrative section marked pending.
A scaffold is not a record: the gaps are filled by hand against the primary source.

A dossier exists only for a record a person has judged. It records that person's verdict —
in, out or unclear — so dossiers exist for out-of-scope and unclear records too, not only
for in-scope ones. A record nobody has judged has no dossier, by design: the classifier
reads records and context, never dossiers.

**check** validates and exits non-zero. It enforces the id pattern, every required
frontmatter key, ISO or partial-ISO dates with matching precision, that every `sources[]`
entry resolves to a record that exists, that every instance id is in the taxonomy, every
controlled vocabulary, all seven narrative sections, that AIID is the canonical source
wherever it attests an incident, and that no `e1..e5` key has crept in. It accepts read
depth `curator` and the `manual` flag in the context layer, and fails a dossier marked
`verified` whose reading is only `curator`. Over the files it checks that every record row
has a `record_key` matching its pair, a `raw_ref`, a `content_hash` that is the hash of its
substance, and no version identical to the one before; and that every queue, readiness,
context and proposal row with a `record_key` has the right one.

## Idempotency

Records are keyed on `(source_id, source_record_id)`, written `record_key`, and carry a
`content_hash` over their substance only: `title`, `text`, `date`, `url`, `meta`, and
`external_labels` with each label's `fetched_at` left out. No fetch date is hashed, and
neither is `raw_ref`. A re-fetch appends a new version **only when the hash changed**, so
an upstream edit is detected rather than silently overwriting, and re-running `update` on
unchanged upstream data produces no diff, whatever the fetch date.

Until 2026-11-16 the hash covered each label's `fetched_at`, so the 2026-11-15 re-fetch
appended a second, identical version of all 313 labelled AIID incidents.
`0.2/pipeline/migrate_keys_20261116.py` recomputed every hash, dropped those 313 rows
(2,130 rows became 1,817, one per incident), and added `record_key` and `raw_ref`. `check`
now fails a record whose `content_hash` is not the hash of its substance, and a version
identical to the one before it.

## Dossier format

YAML frontmatter plus seven fixed sections, so dossiers diff cleanly and `rg` finds them by
narrative content.

Two keys name a dossier. `mig_key`, MIG-nnnn, is ours and names the file
(`MIG-0034.md`): the key its record was given in `0.2/registry/mig_keys.csv` when it first
reached the decide-scope sheet, unique and never changed. `source_key` is the key the
canonical source uses (`794` for AIID incident 794), blank when the source has none. When
AIID is among the sources it is the canonical one, and `check` enforces that; linking AIID
later changes `canonical_source` and `source_key`, never `mig_key`. Until 2026-11-23
dossiers were named after AIID (`AIID-0794.md`);
`0.2/pipeline/migrate_mig_keys_20261123.py` renamed them.

Required frontmatter: `mig_key`, `source_key`, `title`, `canonical_source`, `sources`, `occurrence_date`,
`occurrence_date_precision`, `first_seen`, `last_verified`, `systems`, `actor_count`,
`interaction_kind`, `evidence_type`, `multi_agent`, `multi_agent_basis`,
`multi_agent_label_source`, `external_labels`, `failure_mode`, `failure_mode_source`,
`instances`, `instances_presumed`, `verification`.

Sections, in this order: `## Context`, `## What happened`, `## Mechanism`,
`## Agents and interaction`, `## Response`, `## Verification notes`, `## Sources`.

**No evidence scores.** The evidence-scoring rubric is parked, so a dossier carries no
score fields.

## Vocabularies

- `evidence_type`: `real_world` · `synthetic` · `lab` · `theoretical`
- `interaction_kind`: `communication` · `one-acting-on-another` · `shared-environment` ·
  `none` · `unclear`
- `verification`: `verified` · `partially_verified` · `unverified`
- `multi_agent_label_source`: `ours` · `external:<source_id>` · `classifier:<prompt>@<ver>`
- `failure_mode_source`: `ours` (a person judged it) · `classifier:<prompt>@<ver>` (derived
  by rule from that prompt's facts and not yet confirmed by a person) · empty when there is
  no failure mode
- `occurrence_date_precision`: `day` · `month` · `year`

## The registry

`0.2/registry/sources.csv` is the machine-readable spine the pipeline reads: one row per
source, with its role, access method, adapter, reuse status and where its multi-agent label
lives, if it has one. Three files describe sources and each has one job:

| file | job |
|---|---|
| `0.2/registry/sources.csv` | what the pipeline reads: role, adapter, access, reuse, label field |
| `RESOURCES.md` | the human lead list: what is worth reading, what blocks reading it |
| `docs/sources.txt` | the audit trail: which source backs which row, what was screened and rejected |

A source may appear in all three. Each note belongs to exactly one.

## Known gaps

- The ForumMagnum adapter (LessWrong, Alignment Forum, EA Forum) is specified but not
  implemented, and neither is the companyscope reader. Those four sources get no work order:
  a script could reach them, so `discover` lists them as readers still to write. Work orders
  go only to the seven sources a person has to read.
- The discover step as a whole is a placeholder. `update --discover` does nothing yet.
- None of the 27 migrated incidents, now 26 dossiers after one merge, is linked to an AIID
  record. The migration looked for
  close title matches and found none above threshold; linking is deliberately not automatic,
  because a wrong merge is worse than a missing one.
- Four migrated titles were truncated from a long summary sentence and want renaming by
  hand: the dossiers for AIR-2026-0101, AIR-2026-0219, AIR-2026-0194 and AIR-2026-0183.
- `actor_count` and `interaction_kind` are `unclear` on every carried-over dossier, because
  the inventory they came from did not record either. Both have to be filled from the
  primary sources; `interaction_kind` feeds the failure-mode assignment.
