# testenv

The fixtures of the **test run**: a small, fixed world of made-up incidents that the real
update routine runs on, in a scratch folder, so every step, prompt and decision can be
tried without touching the real tree.

```
python 0.2/pipeline/run.py testrun [--refetch] [--manual] [--discover] [--skip STEP ...]
```

or the "Test run" button on the page `run.py serve` puts up. The command answers every prompt
with its first action, `skip` at the steps named in `--skip`, and exits 0 only if the run
ends `done`. It is also the regression test of these fixtures.

Nothing here is real. Every title starts `TEST CASE`, every organisation is fictional, the
AIID ids are 9901 to 9906, far above any AIID incident id, and the sources cited are
`example.org` pages. The ids have four digits because `check` accepts `AIID-` with four.

## How a test run works

`0.2/pipeline/testenv.py` makes a fresh folder with `tempfile.mkdtemp`, named
`mig-testrun-*`, and loads a second instance of `run.py` pointed at `<workspace>/0.2`. The
real instance is never re-pointed. The test run refuses to start unless every path of its
instance is inside the workspace.

The workspace holds:

| path | from |
|---|---|
| `0.2/registry/sources.csv` | `testenv/0.2/registry/`: aiid, one fictional discovery source, manual, one reference. There is no `registry/labels/`, so the test world has no Navigator labels |
| `0.2/taxonomy/`, `0.2/docs/`, `0.2/prompts/` | copies of the live tree, so every id is checked against the real taxonomy |
| `0.2/raw/aiid/` | `testenv/aiid/`: the saved snapshot, in the format `fetch_aiid.py` writes |
| `writeups/` | `testenv/manual/`: the curator's directory, ingested only with `--manual` |

Then the real steps run. Three things differ from a real run:

- **fetch** never contacts AIID. Without `--refetch` it finds the snapshot, as a real run
  does. With `--refetch` the first attempt fails on purpose, so the "Try again / Use the
  snapshot" decision can be tried; both answers work.
- **manual** ingests `writeups/` through the real `ingest_manual` when `--manual` is on.
- **Stand-ins.** Where a real run waits for `/classify-incidents` or for a person, the
  answer `continue`, or `retry` on a failed check, puts the files in `standins/<step>/` in
  place, as that work would have, and logs each one. `skip` puts nothing in place, and the
  later steps show the consequence. A stand-in puts in place only what the workspace
  allows: no reading for a record that is not queued, no proposal for a record that
  cannot be judged, no dossier that no promote decision made.
- **The review stand-in works the real sheets.** The run writes `0.2/review/1_decide_scope.xlsx`
  in the workspace. On Continue the stand-in opens it with openpyxl and types the decisions
  of `standins/review/decisions.json` into it (9901 `in`, 9906 `out`, 9904 a wrong value),
  and the real `stage_review` reads it: it logs two decisions, reports the wrong one by
  its MIG key and writes sheet 2. The stand-in finds each record's row by its MIG key: the
  run gives aiid:9901 MIG-0001 and aiid:9904 MIG-0002, and with `--manual` the hand-added
  record MIG-0003. The stand-in fills that too (9901 `yes`, and the manual
  record `yes` with `--manual`), the real step reads it and makes the blank dossiers, and the
  stand-in puts the filled-in sample dossiers over them. 9906 is stopped by its `out`: it has
  no dossier. Then it edits sheet 3 in two rounds, each read by the real step: round 1 types
  an evidence type that does not exist on MIG-0001, which is reported and not written;
  round 2 changes its instances and verification and adds a verification note, which are
  written, named in `set_by_person` and logged in `0.2/review/dossier_edits_log.csv`. The check
  stand-in later puts the corrected MIG-0001 over it, so those edits do not survive to
  the index. Without openpyxl the stand-in says so and decides nothing.

Each waiting or failed prompt in a test run carries `test_note`, a sentence saying what the
answer does in the test run.

A test run's state is persisted only inside its workspace, and it keeps no run log: only
real runs go into `0.2/state/runs/`. The server removes a test workspace when the next test
run starts and when it stops. The command leaves its workspace in place and prints its
path; delete the workspace when done.

## The tree

| path | what |
|---|---|
| `cases.json` | one entry per case: `ref`, `title`, and `shows`, what it demonstrates |
| `aiid/` | the AIID sample: `incidents.jsonl`, `classifications.jsonl`, `FETCHED.md` |
| `manual/` | the hand-written write-up |
| `0.2/registry/sources.csv` | the registry of the test world |
| `standins/read/context/` | the readings `/classify-incidents` step 0 would write |
| `standins/judge/proposals/` | its two classifier calls' proposals, named by run date when put in place |
| `standins/review/decisions.json` | what a person would type into the two review sheets |
| `standins/review/incidents/` | the dossiers a person would write over the blank ones the promote step makes, put over the one of the same record only; `MIG-0001.md` (aiid:9901) has a deliberate fault; `MIG-0003.md` is the hand-added record |
| `standins/check/incidents/` | the corrected `MIG-0001.md`, put in place on Try again |

## The cases

| ref | what it needs |
|---|---|
| `aiid:9901` | recent, flagged by an external label; a full reading shows two interacting agents: in scope. Its first dossier puts it in scope on AIID's label, which `check` refuses |
| `aiid:9902` | recent, flagged by a keyword; a secondary reading shows one chatbot: dismissed |
| `aiid:9903` | dated before 2024, queued as frozen (it is on the test's own frozen list) and flagged by a keyword; only the record text was read: the flag rule holds it |
| `aiid:9904` | recent, no flag; read in full and silent on agents: unclear. On sheet 1 its stand-in decision is a wrong value, which the run reports and does not log, so it stays left to decide |
| `aiid:9905` | dated before 2024 and not on the frozen list: not queued |
| `aiid:9906` | recent, although a CSETv1 label answers "no" (an outside label never keeps a record out); a drone swarm doing what one agent could: a multi-agent setup, out of scope. Decided `out` on sheet 1: the decision stops it, and it gets no dossier |
| `manual:test-case-relay-agents` | hand-added: in scope on the curator's word, never verified |

## Limits

- The records' `url` is `https://incidentdatabase.ai/cite/99nn`, because `normalise_aiid`
  builds it from the id. Those pages do not exist; the sources the readings cite are
  `example.org` pages.
- The stand-in proposals hold model output only, as real ones do. The labels come from the
  real Derive step, which runs `derive.py` on them and writes the workspace's
  `state/verdicts.jsonl`: 9901 in scope, 9906 out of scope, 9904 and the manual record for
  review.
- The workspace has no gold set or accuracy scores, so the map shows none.
- The map's record counts are small and many are 0. They obey the same rule as a real
  run's: every box's incoming records equal what goes on, stops or waits there, and the
  `checks` that `run.py` computes must all hold. A failed one shows as a warning above the
  map.
