# mvp

The current build, started from zero on 2026-11-12. An earlier exploratory pass established the
ontology and is frozen; this tree carries forward its lessons rather than its structure.

The **input layer** is built. Detection and mapping follow in this same tree until v1.0.

## Start here

New to the project? Read in this order:

1. [`docs/how_it_works.md`](docs/how_it_works.md), 15 minutes: what the index is, one
   record's journey from fetch to index, the two gates, how to run an update, and what is a
   model's judgement, a fixed rule, or a person's decision.
2. [`docs/glossary.md`](docs/glossary.md): every project term in a sentence or two.
3. [`docs/README.md`](docs/README.md): the reading order for the rest of `docs/`, and where
   the rules (`pipeline/derive.py`), prompts and skill live.

Where to read what: definitions and the gates are in `docs/definitions.md`; reading sources
and readiness in `docs/context_layer.md`; the record store and the runbook in
`docs/input_layer.md`; the classifier design in `docs/classifiers.md`; accuracy in
`docs/gold_set.md` and `docs/gate1_accuracy.md`.

## Run it

```
pip install -r ../requirements.txt

python mvp/pipeline/run.py serve                     # the front end: open http://127.0.0.1:8765/
python mvp/pipeline/run.py update                    # or run it from the terminal
python mvp/pipeline/run.py check                     # must exit 0 before committing
python mvp/pipeline/run.py testrun                   # a dry run on made-up incidents
python mvp/pipeline/run.py runs [RUN]                # past runs; with RUN, how its numbers changed
```

`testrun`, or the page's "Test run" button, runs the real update steps on a small fixed set
of made-up incidents in a scratch folder under the system temp directory. It never fetches
AIID, never writes to the real tree, and keeps no run log.
Where a real run waits for `/classify-incidents` or for a person, Continue puts sample
results in place; Skip shows what skipping costs. The command answers every prompt itself,
takes `--refetch`, `--manual`, `--discover` and `--skip STEP ...`, and exits 0 only if the
run ends `done`. See `testenv/README.md`.

`serve` shows the pipeline map with live numbers and can start a run from the page. It
listens on 127.0.0.1 only. When a step needs a person, the run waits and the page says what
to do. During a run, real or test, the map's numbers are recomputed each time a step changes
state. `mvp/out/pipeline_flow.html` also opens from disk, without a server, showing the
last build's numbers.

Every number on the map is a number of records, over all sources (`aiid:1604` is one
record). `run.py` computes the flow once, in `map_flow`: per box, the records that come
in, the wires out with their counts, what stops there and what waits there, plus a
`checks` list of the equations that must hold. Each box opens a breakdown by source and
by sub-group, with where its records come from, where they go and the files counted. A
failed equation shows as a warning above the map. Boxes whose number is not a record
count (sources, notes, rulebook size, a score) are set apart and say so.

Every real run, from the page or the terminal, leaves a log in `state/runs/<run id>.json`:
its options, steps, logs and a `trace` of the map's numbers at
each change of state. `run.py runs` lists them; `run.py runs RUN` prints what changed when.

`update` options:

- no option: refresh the AIID baseline from the snapshot saved in `raw/aiid/`
- `--refetch`: fetch AIID afresh; needs the AIID token (`--token-file F`) and network
- `--manual DIR`: add incidents the curator wrote up by hand, one `.txt` or `.md` per
  incident; they go straight to the ready, in-scope list on the curator's word
- `--discover`: search the discovery sources. A placeholder: not built yet

Reading sources and judging are not in `run.py`. They are the `/classify-incidents` skill,
run in Claude Code. The labels are not the model's: `run.py derive` applies the rules in
`pipeline/derive.py` to the model's extracted facts and writes `state/verdicts.jsonl`; an
`update` runs it right after the Judge step. `run.py instances-due` lists the records a
person put in scope that still need instances: they are proposed only after the scope
decision.

A person decides in two spreadsheets, `review/1_decide_scope.xlsx` (is the record in scope:
`in`, `out` or `unclear`) and `review/2_promote.xlsx` (which records decided in get a
dossier: `yes` or `no`). `run.py review`, which the update's Review step also runs, reads
the filled sheets, logs the decisions in `review/scope_decisions_log.csv` and
`review/promote_decisions_log.csv`, makes the dossier for each promote `yes`, and writes both
sheets again. The map counts what is left on each. `run.py promote` still makes one dossier
by hand. See `review/README.md`. The sheets need openpyxl (`pip install -r requirements.txt`).

## Layout

| path | what | who writes it |
|---|---|---|
| `registry/sources.csv` | the source registry the pipeline reads | hand |
| `registry/frozen_pre2024.csv` | the 34 pre-2024 records the prefilter keeps queuing; kept by hand | hand |
| `registry/labels/` | hand-made external label files, e.g. the Navigator's multi-agent list | hand |
| `taxonomy/` | risks, instances, associations, evidence types | hand |
| `raw/<source>/` | verbatim fetch output; `raw/manual/` holds copies of hand write-ups | `fetch`, `update --manual` |
| `records/<source>.jsonl` | normalised, append-only, content-hashed, with a `raw_ref` back to `raw/`; `manual.jsonl` for hand-added incidents | `normalise`, `update --manual` |
| `context/<source>.jsonl` | what each source says about the gate facts, with quotes and depth read | the skill; `update --manual` for manual rows |
| `review/` | the two sheets a person fills in (generated, gitignored) and the two decision logs, `scope_decisions_log.csv` and `promote_decisions_log.csv` | `review` writes; a person fills the sheets |
| `incidents/<ID>.md` | the curated record, one dossier per incident a person promotes: in, out or unclear | hand |
| `proposals/` | classifier output, the model's only, never authoritative | the skill |
| `prompts/` | versioned prompts: enrichment and the two classifier calls | hand |
| `gold/` | calibration labels | hand |
| `skills/classify-incidents/` | the reader and classifier runner | hand |
| `pipeline/` | `run.py`, `derive.py` (the labelling rules), the source adapters, the map page template, `testenv.py`, and `report/`, the published report's parts | hand |
| `testenv/` | the test run's made-up incidents and stand-ins; never read by a real run | hand |
| `state/` | candidate queue, readiness, derived verdicts, instances due, work orders, run state, run logs in `runs/` (gitignored) | `prefilter`, `readiness`, `derive`, `instances-due`, `discover`, `serve`, `update` |
| `out/` | the flat index, the pipeline flowchart `pipeline_flow.html`, and the published report `index_report.html` | `index`, `viz`; `report`, run on its own |

Every row in `records/`, `context/`, `proposals/` and the `state/` row files carries
`record_key`, `"<source_id>:<source_record_id>"`, e.g. `aiid:1604`: the pipeline's
internal join key. See `docs/input_layer.md` § The record key. A person never sees it:
sheets, logs, dossiers and reports name a record by `mig_key` (MIG-nnnn, ours, from
`registry/mig_keys.csv`) and `source_key` (the source's own key). `promote` takes either
a MIG key or a record_key.

## Documentation

- `docs/definitions.md` — what counts as an agent and as a multi-agent incident: the two
  gates, the failure-mode tree, the four evidence types, label provenance
- `docs/input_layer.md` — the schema, the vocabularies, the runbook, manual incidents
- `docs/context_layer.md` — read before you judge: the context layer, readiness, the flag rule
- `docs/classifiers.md` — the two classifier designs and the calibration protocol

## Where it stands

26 dossiers, carried over from the index's earlier holdings and re-judged from the primary
sources: 19 assert `multi_agent: true`, 4 `false`, 3 `unclear`. 1,844 records across four
sources. 1,133 candidates in the queue on 2026-11-18: every AIID record dated 2024 or later that no outside rater has answered "not multi-agent" on, plus the
34 on the frozen pre-2024 list (`docs/input_layer.md` § prefilter). Call 1 has been run on 103 queued records,
and on the gold set, where with the labels derived by `pipeline/derive.py` it scores 87.0%
precision and 90.9% recall (`docs/gate1_accuracy.md`).

**The gold set has been reviewed.** `mvp/gold/multiagent_gold.csv` holds 58 rows in four
strata, each with a human verdict: 22 `in`, 33 `out`, 3 `unclear`. Rework them with
`python mvp/gold/build_review.py` and `mvp/out/gold_review.html`. See
`docs/gold_set.md` and `docs/classifiers.md` → Calibration.

The things to know before extending it:

- **An external or machine label marks a candidate. Only a human verdict puts an incident in
  scope.** `check` fails the build otherwise. A manual incident is in scope on the curator's
  word, which is a human verdict.
- **Count agents, not systems.** One product or operator can hold several agents. A record
  the prefilter flagged by label or keyword is never dismissed on its record text alone.
- **The failure mode comes only from the Gate 2 tree.** Instances are descriptive detail,
  assigned independently; neither is derived from the other. An FM–RF association is never
  inferred from two labels on one incident. See `docs/definitions.md` § Instances.
- **Scoring is parked.** The evidence-scoring rubric is not applied anywhere here.
