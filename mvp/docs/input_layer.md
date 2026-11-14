# Input layer

How incidents get in: the sources, the record store, the dossiers, and the one command that
runs it.

## The shape

Two levels, because one incident appears in several sources and a single-level store
duplicates it the first time a second adapter runs.

```
mvp/raw/<source>/          verbatim fetch output. Never hand-edited.
mvp/records/<source>.jsonl normalised, append-only, content-hashed. Machine-written.
mvp/context/<source>.jsonl what each source says about the gate facts. A reading, with quotes.
mvp/incidents/<ID>.md      the curated record. Hand-edited. One dossier per incident.
mvp/out/incident_index.csv a flat index generated from the dossiers.
```

A record is what one source said, when we fetched it. A dossier is what we believe happened,
citing the records that attest it.

## The update routine

```
python mvp/pipeline/run.py update                       # AIID baseline refresh, from the saved snapshot
python mvp/pipeline/run.py update --refetch             # fetch AIID afresh; needs the token and network
python mvp/pipeline/run.py update --manual DIR          # also add incidents written up by hand in DIR
python mvp/pipeline/run.py update --discover            # also run discover: a placeholder, not built yet
python mvp/pipeline/run.py update --token-file F        # read the AIID token from F
python mvp/pipeline/run.py serve [--port 8765]          # the front end, on 127.0.0.1 only
```

The old three modes (`labelled-only`, `aiid-full`, `all-sources`) are gone. By default
`update` refreshes the AIID baseline: it reuses the snapshot already in `mvp/raw/aiid/` and
fetches only with `--refetch`. It then normalises, prefilters, computes readiness, builds
the index and renders the pages.

AIID is the **baseline** source. Everything else is a **discovery** source, searched for
incidents AIID does not carry — which matters, because 18 of the 27 incidents the project
started with are absent from AIID entirely, including all 7 AI Village rows. Discovery has
no working module yet; see **discover** below.

Each stage is also runnable alone: `fetch`, `normalise`, `discover`, `prefilter`, `readiness`,
`promote`, `index`, `viz`, `check`.

### Who does each step

Most steps are `run.py`, a script. Two are not:

| step | done by | produces |
|---|---|---|
| fetch, normalise, prefilter, readiness, index, viz, check | `run.py` | files under `raw/`, `records/`, `state/`, `out/`; `check` produces only an exit code |
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
`mvp/state/run.json`, so a reload picks up where it was.

### Manual incidents

`update --manual DIR` adds incidents the curator has written up by hand. `DIR` holds plain
`.txt` or `.md` files.

- One file is one incident, unless it has two or more headings of the same top level
  (`# ` or `## `); then each heading starts an incident.
- Title is the heading, or the first non-empty line. Text is the rest, verbatim. Date is the
  first ISO date in the text, full or partial, else empty. URL is the first `http(s)` link,
  else empty.
- A verbatim copy of each file goes to `mvp/raw/manual/`. Records go to
  `mvp/records/manual.jsonl` by the normal append and content-hash path, with
  `meta.manual: true` and the original path.
- Each record goes straight into the queue (`arms: "manual"`, whatever the prefilter says)
  and gets a context row in `mvp/context/manual.jsonl` with read depth `curator`.

They land on the **ready, in-scope** list on the curator's word: the curator is the human
whose verdict puts an incident in scope. The classifier skips Gate 1 for them and proposes
only the failure mode, evidence type and instances, marked provisional. A dossier still
needs `run.py promote` and a hand write-up, and it may not be `verified` on the write-up
alone. See `context_layer.md` § Manual records.

## Stages

**fetch** dispatches on the registry's `adapter` column. AIID imports
`mvp/pipeline/fetch_aiid.py` as a library and never modifies it. In `update` it reuses the
saved AIID snapshot unless `--refetch` is given. A refetch with no token, or with no
network, fails the step and offers to retry or to fall back on the snapshot.

**discover** is a **placeholder**. Searching the discovery sources for new incidents is not
built yet: `update --discover` reports the step as "not built yet" and carries on. Work
orders are a sub-step of discover. A work order is a note **per source**, not per incident,
written to `mvp/state/work_orders.md`: for a source no script can reach, it says what to
search, where, and what to paste back. `run.py discover` still writes these notes on its
own, but an `update` run does not depend on them. A human-in-the-loop source is a stage,
not a gap.

**normalise** writes one record per source record. AIID needs a join: `incidents.jsonl` at
depth 0 carries no classifications, and `classifications.jsonl` has no `incident_id` — its
only path back is the expanded `incidents` list, so the join is on `incidents[]._id`. It
harvests the `Multiple AI Interaction` attribute from the consensus `CSETv1` namespace *and*
all three `CSETv1_Annotator-*` namespaces, so rater disagreement stays visible.

**prefilter** is a union of three arms, because no single net has acceptable recall:

| arm | rule | current |
|---|---|---|
| `label` | any external label says `yes` or `maybe`, including one dissenting annotator | 39 |
| `keyword` | the recall-first regex net, lifted from the exploratory notebook | 62 |
| `unclassified` | no classification at all, and dated on or after 2024-01-01 | 286 |

The third arm exists because 305 of AIID's 1,803 incidents carry no classification, and they
are the recent ones. An unclassified record is unscreened, not negative — which is a
different thing from a record CSETv1 looked at and called `no`.

The rules are constants at the top of `mvp/pipeline/run.py`: `KEYWORD_TERMS` (the regexes),
`UNCLASSIFIED_CUTOFF` (the date) and `MA_POSITIVE` (the label values that count). The queue
row records which arms caught each record. A record caught by `label` or `keyword` is
**flagged**, and the record pass may not dismiss it on its text alone
(`context_layer.md` § The flag rule). Manual records bypass the arms and are queued with
`arms: "manual"`.

Measured, which is why there are three arms and not one: the MIT Navigator's rater has a
**33% false-negative rate** on the 9 of our incidents that are in AIID. The keyword arm's
recall is unmeasured; an earlier 78% figure was withdrawn (`mvp/docs/gate1_accuracy.md`).

**readiness** reports, per record, whether enough has been read to classify it, from the
context layer. A record whose scope is `not_ready` is not classified and cannot be promoted
without `--force`. See `mvp/docs/context_layer.md`.

**classify** is not part of `run.py`. It is a Claude Code skill, `/classify-incidents`,
because a Pro subscription covers Claude Code and not the Messages API. See
`mvp/docs/classifiers.md`.

**viz** renders two pages into `mvp/out/` from the live counts. `pipeline_patch.html` is
the plain-language map of the whole pipeline: every step is a box, the wires show what flows
between them, and clicking a box explains it. The same page, served by `run.py serve`, is
the front end: it can start a run and shows it step by step. Opened from disk it shows the
numbers of the last build but cannot run anything. `input_workflow.html` is the older
stage-by-stage view of the input layer.

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
`verified` whose reading is only `curator`.

## Idempotency

Records are keyed on `(source_id, source_record_id)` and carry a `content_hash` over the
fields that matter. A re-fetch appends a new version **only when the hash changed**, so an
upstream edit is detected rather than silently overwriting, and re-running `update` on
unchanged upstream data produces no diff.

## Dossier format

YAML frontmatter plus seven fixed sections, so dossiers diff cleanly and `rg` finds them by
narrative content.

Id comes from the canonical source: `AIID-0007.md` where AIID attests the incident,
`MIG-nnnn.md` where no indexed database does. When AIID is among the sources it is the
canonical one, and `check` enforces that.

Required frontmatter: `id`, `title`, `canonical_source`, `sources`, `occurrence_date`,
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
- `occurrence_date_precision`: `day` · `month` · `year`

## The registry

`mvp/registry/sources.csv` is the machine-readable spine the pipeline reads: one row per
source, with its role, access method, adapter, reuse status and where its multi-agent label
lives, if it has one. Three files describe sources and each has one job:

| file | job |
|---|---|
| `mvp/registry/sources.csv` | what the pipeline reads: role, adapter, access, reuse, label field |
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
