# mvp

The current build, started from zero on 2026-11-12. The PoC in `poc/` established the
ontology and is frozen; this tree carries forward its lessons rather than its structure.

The **input layer** is built. Detection and mapping follow in this same tree until v1.0.

## Run it

```
pip install -r ../requirements.txt

python mvp/pipeline/run.py update --mode aiid-full   # fetch, screen, index, render
python mvp/pipeline/run.py check                     # must exit 0 before committing
open mvp/out/input_workflow.html                     # opens from disk, no server
```

Three modes: `labelled-only` (AIID, external labels only, no classifier), `aiid-full`
(AIID with the full prefilter), `all-sources` (plus the discovery sources).

## Layout

| path | what | who writes it |
|---|---|---|
| `registry/sources.csv` | the source registry the pipeline reads | hand |
| `taxonomy/` | risks, instances, associations, evidence types | hand |
| `raw/<source>/` | verbatim fetch output | `fetch` |
| `records/<source>.jsonl` | normalised, append-only, content-hashed | `normalise` |
| `incidents/<ID>.md` | the curated record, one dossier per incident | hand |
| `proposals/` | classifier verdicts, never authoritative | the skill |
| `prompts/` | versioned classifier prompts | hand |
| `gold/` | calibration labels | hand |
| `skills/classify-incidents/` | the classifier runner | hand |
| `pipeline/` | `run.py` and the source adapters | hand |
| `state/` | candidate queue, stage counts, work orders | `prefilter`, `index` |
| `out/` | the flat index and the workflow page | `index`, `viz` |

## Documentation

- `docs/definitions.md` — what counts as a multi-agent incident: the two gates, the
  failure-mode tree, the four evidence types, label provenance
- `docs/input_layer.md` — the schema, the vocabularies and the runbook
- `docs/classifiers.md` — the two classifier designs and the calibration protocol

## Where it stands

27 dossiers, migrated from the PoC inventory. 1,830 records across four sources. 347
candidates in the queue. Both classifiers are designed and their prompts written; neither
has been run, and neither should be until the gold set is reviewed.

**The gold set is under review.** Every PoC label came from AI-assisted sessions and none
was independently checked, so calibrating against it would measure agreement with an earlier
model pass. `mvp/gold/multiagent_gold.csv` holds 60 rows in four strata, all `to_judge`;
work through them with `python mvp/gold/build_review.py` and `mvp/out/gold_review.html`.
See `docs/classifiers.md` → Calibration.

The things to know before extending it:

- **An external or machine label marks a candidate. Only a human verdict puts an incident in
  scope.** `check` fails the build otherwise.
- **Evidence reaches a risk only through an instance.** That is why the classifier assigns
  instance ids and the failure mode is derived, not stated.
- **Scoring is parked.** No E1–E5 anywhere here; it lives in `poc/`.
