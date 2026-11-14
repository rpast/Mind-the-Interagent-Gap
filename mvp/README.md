# mvp

The current build, started from zero on 2026-11-12. An earlier exploratory pass established the
ontology and is frozen; this tree carries forward its lessons rather than its structure.

The **input layer** is built. Detection and mapping follow in this same tree until v1.0.

## Run it

```
pip install -r ../requirements.txt

python mvp/pipeline/run.py serve                     # the front end: open http://127.0.0.1:8765/
python mvp/pipeline/run.py update                    # or run it from the terminal
python mvp/pipeline/run.py check                     # must exit 0 before committing
python mvp/pipeline/run.py testrun                   # a dry run on made-up incidents
```

`testrun`, or the page's "Test run" button, runs the real update steps on a small fixed set
of made-up incidents in a scratch folder under the system temp directory. It never fetches
AIID and never writes to the real tree. Where a real run waits for `/classify-incidents` or
for a person, Continue puts sample results in place; Skip shows what skipping costs. The
command answers every prompt itself, takes `--refetch`, `--manual`, `--discover` and
`--skip STEP ...`, and exits 0 only if the run ends `done`. See `testenv/README.md`.

`serve` shows the pipeline map with live numbers and can start a run from the page. It
listens on 127.0.0.1 only. When a step needs a person, the run waits and the page says what
to do. `mvp/out/pipeline_patch.html` also opens from disk, without a server, showing the last
build's numbers.

`update` options:

- no option: refresh the AIID baseline from the snapshot saved in `raw/aiid/`
- `--refetch`: fetch AIID afresh; needs the AIID token (`--token-file F`) and network
- `--manual DIR`: add incidents the curator wrote up by hand, one `.txt` or `.md` per
  incident; they go straight to the ready, in-scope list on the curator's word
- `--discover`: search the discovery sources. A placeholder: not built yet

Reading sources and judging are not in `run.py`. They are the `/classify-incidents` skill,
run in Claude Code. Promotion to a dossier is a person, with `run.py promote` as the start.

## Layout

| path | what | who writes it |
|---|---|---|
| `registry/sources.csv` | the source registry the pipeline reads | hand |
| `taxonomy/` | risks, instances, associations, evidence types | hand |
| `raw/<source>/` | verbatim fetch output; `raw/manual/` holds copies of hand write-ups | `fetch`, `update --manual` |
| `records/<source>.jsonl` | normalised, append-only, content-hashed; `manual.jsonl` for hand-added incidents | `normalise`, `update --manual` |
| `context/<source>.jsonl` | what each source says about the gate facts, with quotes and depth read | the skill; `update --manual` for manual rows |
| `incidents/<ID>.md` | the curated record, one dossier per judged incident: in, out or unclear | hand |
| `proposals/` | classifier verdicts, never authoritative | the skill |
| `prompts/` | versioned prompts: enrichment and the two classifier calls | hand |
| `gold/` | calibration labels | hand |
| `skills/classify-incidents/` | the reader and classifier runner | hand |
| `pipeline/` | `run.py`, the source adapters, the map page template, `testenv.py` | hand |
| `testenv/` | the test run's made-up incidents and stand-ins; never read by a real run | hand |
| `state/` | candidate queue, readiness, work orders, run state | `prefilter`, `readiness`, `discover`, `serve` |
| `out/` | the flat index and the pipeline pages | `index`, `viz` |

## Documentation

- `docs/definitions.md` — what counts as an agent and as a multi-agent incident: the two
  gates, the failure-mode tree, the four evidence types, label provenance
- `docs/input_layer.md` — the schema, the vocabularies, the runbook, manual incidents
- `docs/context_layer.md` — read before you judge: the context layer, readiness, the flag rule
- `docs/classifiers.md` — the two classifier designs and the calibration protocol

## Where it stands

26 dossiers, carried over from the index's earlier holdings and re-judged from the primary
sources: 19 assert `multi_agent: true`, 4 `false`, 3 `unclear`. 1,830 records across four
sources. 347 candidates in the queue. The enrichment prompt and both classifier prompts are
written; none has been run over the queue.

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
