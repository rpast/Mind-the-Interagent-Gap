# testenv

The fixtures of the **test run**: a small, fixed world of made-up incidents that the real
update routine runs on, in a scratch folder, so every step, prompt and decision can be
tried without touching the real tree.

```
python mvp/pipeline/run.py testrun [--refetch] [--manual] [--discover] [--skip STEP ...]
```

or the "Test run" button on the page `run.py serve` puts up. The command answers every prompt
with its first action, `skip` at the steps named in `--skip`, and exits 0 only if the run
ends `done`. It is also the regression test of these fixtures.

Nothing here is real. Every title starts `TEST CASE`, every organisation is fictional, the
AIID ids are 9901 to 9906, far above any AIID incident id, and the sources cited are
`example.org` pages. The ids have four digits because `check` accepts `AIID-` with four.

## How a test run works

`mvp/pipeline/testenv.py` makes a fresh folder with `tempfile.mkdtemp`, named
`mig-testrun-*`, and loads a second instance of `run.py` pointed at `<workspace>/mvp`. The
real instance is never re-pointed. The test run refuses to start unless every path of its
instance is inside the workspace.

The workspace holds:

| path | from |
|---|---|
| `mvp/registry/sources.csv` | `testenv/mvp/registry/`: aiid, one fictional discovery source, manual, one reference. There is no `registry/labels/`, so the test world has no Navigator labels |
| `mvp/taxonomy/`, `mvp/docs/`, `mvp/prompts/` | copies of the live tree, so every id is checked against the real taxonomy |
| `mvp/raw/aiid/` | `testenv/aiid/`: the saved snapshot, in the format `fetch_aiid.py` writes |
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
  cannot be judged, no dossier that nothing proposed.

Each waiting or failed prompt in a test run carries `test_note`, a sentence saying what the
answer does in the test run.

A test run's state is persisted only inside its workspace, and it keeps no run log: only
real runs go into `mvp/state/runs/`. The server removes a test workspace when the next test
run starts and when it stops. The command leaves its workspace in place and prints its
path; delete the workspace when done.

## The tree

| path | what |
|---|---|
| `cases.json` | one entry per case: `ref`, `title`, and `shows`, what it demonstrates |
| `aiid/` | the AIID sample: `incidents.jsonl`, `classifications.jsonl`, `FETCHED.md` |
| `manual/` | the hand-written write-up |
| `mvp/registry/sources.csv` | the registry of the test world |
| `standins/read/context/` | the readings `/classify-incidents` step 0 would write |
| `standins/judge/proposals/` | its two classifier calls' proposals, named by run date when put in place |
| `standins/review/incidents/` | the dossiers a person would write; `AIID-9901.md` has a deliberate fault |
| `standins/check/incidents/` | the corrected `AIID-9901.md`, put in place on Try again |

## The cases

| ref | what it needs |
|---|---|
| `aiid:9901` | label arm; a full reading shows two interacting agents: in scope. Its first dossier puts it in scope on AIID's label, which `check` refuses |
| `aiid:9902` | keyword arm; a secondary reading shows one chatbot: dismissed |
| `aiid:9903` | keyword arm; only the record text was read: the flag rule holds it |
| `aiid:9904` | recent, never asked the multi-agent question (`unasked` arm); read in full and silent on agents: unclear |
| `aiid:9905` | not queued by any arm |
| `aiid:9906` | a drone swarm doing what one agent could: a multi-agent setup, out of scope |
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
