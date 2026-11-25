# Pipeline 0.2: one ledger, two review sheets, proposal and decision for every label

Approved by the curator 2026-11-25. Worked on branch `development/pipeline-0.2`.

Status: all phases done (2026-11-25), P0 to P7 with P3b.

P7 notes: the 0.1 review code is removed from run.py (792 lines); `read_log` stays as the
shape the map and instances_due read, over the record log. Sheet 1 now also lists the
decided records in no incident, with their decision, so a decision can be changed (the
log keeps both rows); this closed a gap found in P5 (aiid:1556, decided out, is the same
incident as MIG-0015; OPEN.md item 64). The docs in `0.2/docs/`, both READMEs, the test
README and OPEN.md describe 0.2; the 26 dossiers whose `multi_agent_basis` cited the scope
log now cite the record log. Still open: the `proposal changed` flag (3.5) and a Dedupe
box on the map.

P6 notes: `run.py index` sets stage, reason and in_index on every ledger row
(`ledger_outcome`); the stage counts equal those of the retired index_report.xlsx. The
report reads the ledger and came out byte-identical. The map keeps its nodes and its
conservation checks (two new ones on the ledger's stage column); the review boxes are
renamed Decide records and New or duplicate, and every box and guide names the 0.2
sheets, logs and ledger columns. index_report.py and index_report.xlsx are removed. Not
built: a separate Dedupe box on the map (dedupe is described in New or duplicate).

P5 notes: the 0.1 logs were carried over by `pipeline/migrate_logs_20261125.py` (132 record
decisions; 0.1's three promote `no` kept as label `dossier` `no`, as written). Not built:
the `proposal changed` flag on a decided label (3.5); a decided label whose proposal
changes keeps its decision silently. A system name holding `;` (six PoC dossiers) is kept
whole while unchanged, since the ledger splits lists on `;`.

P4 result (`run.py dedupe --measure`): on the curator's merges (5 incidents, 12 records)
every record is found; of 64 records not merged, 10 are proposed as duplicates. Run over
the 390 records not in an incident, it proposes 7, three of them true duplicates never
merged: aiid:1015 of MIG-0002 (Xanthorox), aiid:1364 of MIG-0013 (Moltbook database),
aiid:1556 of MIG-0015 (Grok and Bankrbot). The columns built so far are listed in
`0.2/ledger/README.md`.

Change to P3, 2026-11-25: turning the direction (the dossier written from the ledger)
cannot come before sheet 2, since today a person or Claude fills a new dossier's
frontmatter by hand and the test run is built on that. P3 is split: **P3a** (done) puts
the incident columns in the ledger, built from the dossiers, with each label as proposal
and decision; **P3b**, the turn, moves into P5. Column changes against 3.3: `mig_key` is
the record's own key and `incident_key` names its incident.

## 1. Why

Today what the pipeline knows about one record is spread over eight files, one per step
(`records/`, `state/queue.jsonl`, `context/`, `proposals/`, `state/verdicts.jsonl`, the three
decision logs, the dossiers). Where a record stopped, and why, is stored nowhere: it is
recomputed by `index_report.py`. Questions like "everything loaded on 2026-11-15, grouped by
the stage it stopped at" have no single place to be asked.

The person is also asked in three places (scope, promote, edit dossiers), and a machine
label can only be *changed*, never *confirmed*: a failure mode derived by rule and left
untouched stays `classifier:…` forever, with no trace that anyone looked at it.

## 2. Goals

1. **One place, easy to query.** Every record loaded into the pipeline has one row in one
   file, holding the current output of every step, its incident, its stage and the reason.
   Readable in Excel, pandas or DuckDB directly, with no build step in between.
2. **Two review sheets, not three.** Sheet 1 decides records (scope and duplicate together).
   Sheet 2 decides incidents (classification and facts).
3. **Every label is proposed, then decided.** For each label the pipeline writes a proposal
   and a reason, and the person either agrees (`ok`) or gives their own value or values.
4. **Full history stays.** The append-only decision logs remain the history. The ledger is
   the current state.
5. **Built beside mvp/, not in it.** The new pipeline lives in `0.2/`, in step with the
   report's version; `mvp/` is frozen.

Non-goals: no scoring, no new sources, no change to the prompts or the rules in
`derive.py`, no risk-factor classifier (only the columns are reserved for it).

## 3. Design

### 3.1 Trees and branches

- Merge `development/input-layer` into `main` (fast-forward), push.
- Branch `development/pipeline-0.2` from `main`.
- `0.2/` starts as a copy of `mvp/`: code and data. From that commit on, `0.2/` is the live
  build and `mvp/` is frozen like `poc/`: it still runs, gets no new data and no features.
  `CLAUDE.md` says so, with the commit the copy was taken from.
- `run.py` already resolves every path from one root (`MVP`), so the copy runs as is; the
  root constant is renamed and pointed at `0.2/`.
- The report's `VERSION` becomes 0.2; folder, branch and report version move together.

### 3.2 The ledger: one table, the source of truth

`0.2/ledger/ledger.csv`: one row per record ever loaded (about 1,840 today). `mig_key`
names the incident a record belongs to, one incident to many records.

Incident-level labels (failure mode, instances, evidence type, risk factors, verification,
the incident's facts) are held **only on the incident's canonical record row**, marked
`canonical = yes`. The other rows of the incident leave them blank. So:

- questions about incidents filter `canonical = yes` and count each incident once;
- questions about records use every row;
- when an incident's canonical record changes, `ledger.py` moves the incident columns to the
  new row in the same write.

**The ledger is the authority, not a view.** Each step writes its own columns into it, in
the same run that writes its evidence file. Nothing rebuilds it from other files in normal
use. The dossier's frontmatter labels are written **from** the ledger (3.4).

What stays outside it, and why:

| file | role in 0.2 |
|---|---|
| `records/*.jsonl` | the load archive: full text, content hash, raw reference. Append-only, as now. |
| `context/*.jsonl` | evidence: what the source says, with full quotes. The ledger keeps the statuses and depth. |
| `proposals/*.jsonl` | evidence: the model's answers with quotes and reasons. The ledger keeps the values and confidence. |
| `review/*_log.csv` | the history of every human decision. Append-only, as now. |
| `incidents/MIG-nnnn.md` | the readable incident: prose, plus the labels copied from the ledger. |
| `state/queue.jsonl`, `state/verdicts.jsonl` | removed: their content becomes ledger columns. |

Writing rules, enforced by one module, `ledger.py`:

- every column has exactly one owner step; a step writing a column it does not own fails;
- writes are atomic (temp file and rename), one writer at a time;
- no newlines and no long text in a cell; anything longer than a short reason lives in the
  evidence files, referenced by a `*_ref` column (file and line);
- `run.py check` verifies that each ledger value matches the evidence row its `*_ref`
  names, and that every dossier's frontmatter labels equal its ledger row.

### 3.3 Columns

Grouped by the step that owns them, in pipeline order. **R** = on every record row;
**I** = incident level, on the canonical row only.

| group (owner) | | columns |
|---|---|---|
| identity (load) | R | `record_key`, `source_id`, `source_key`, `title`, `date`, `url`, `loaded_on`, `fetched_at`, `content_hash`, `external_ma_label` |
| prefilter | R | `queued`, `queue_basis`, `flags`, `keyword_terms`, `label_values` |
| reading (readiness, from what enrich_context wrote) | R | `read_depth`, `agent_count`, `<fact>_status` ×7, `context_ref` |
| model (derive, from what extract_gate wrote) | R | `gate_prompt`, `gate_run_date`, the 12 answers, `confidence`, `gate_ref` |
| rules (derive) | R | `rules_version`, `is_attack`, `presumption_fires`, `counterfactual`, `by_presumption`, `gate1`, `rules_status`, `why_a_person`, `labels_settled`, and the record-level labels the rules derive: `rules_multi_agent`, `rules_evidence_type`, `rules_failure_mode`, `rules_instances_presumed`. `scope_proposed` and `scope_why` are written here too. |
| record scope label | R | `scope_proposed`, `scope_why`, `scope_decision`, `scope_final`, `scope_decided_on` |
| duplicate label | R | `duplicate_of_proposed`, `duplicate_of_why`, `duplicate_of_decision`, `duplicate_of_final`, `duplicate_of_decided_on` |
| incident key (sheet 1) | R | `mig_key`, `canonical` |
| incident facts | I | `incident_title`, `occurrence_date`, `occurrence_date_precision`, `actor_count`, `interaction_kind`, `systems` |
| incident scope label | I | `incident_scope_proposed`, `_why`, `_decision`, `_final` |
| failure_mode label | I | `failure_mode_proposed`, `_why`, `_decision`, `_final` |
| instances label | I | `instances_proposed`, `_why`, `_decision`, `_final`, `instances_presumed` |
| evidence_type label | I | `evidence_type_proposed`, `_why`, `_decision`, `_final` |
| risk_factors label | I | the same four, reserved, empty until a classifier exists |
| verification | I | `verification`, `last_verified` |
| outcome (index) | R | `stage`, `reason`, `in_index` |

`loaded_on` is new: the date the record was first written to `records/`, never changed.
Existing records are backfilled from `fetched_at`, the closest date on file.

An incident's proposals come from its canonical record's proposals; the other records'
proposals are named in `*_why` when they differ.

`record_key` (`aiid:794`) is the internal join key and appears in the ledger. CLAUDE.md's
rule "no sheet, log, dossier or report shows it" is extended to name the ledger as an
internal file that may.

### 3.4 Dossiers

The ledger is the source; the dossier is the readable copy plus the prose.

- After every `review`, the pipeline writes each incident's labels and facts from the
  ledger into its dossier's frontmatter. They are never edited by hand there; a change
  goes through sheet 2.
- The prose (what happened, verification notes, sources described) stays the dossier's own,
  edited by hand or written by Claude on request, as now.
- `set_by_person`, `failure_mode_source` and `multi_agent_label_source` are replaced by
  the decision columns: a decided label is ours, an undecided one is a proposal. The
  frontmatter shows for each label whether it is decided.

### 3.5 Proposal and decision

Every label, on both sheets, has the same three columns:

| column | written by | holds |
|---|---|---|
| `<label>_proposed` | pipeline | the proposal; `;`-separated ids for a multi-value label |
| `<label>_why` | pipeline | a short reason: the rule, the confidence, the matched evidence |
| `<label>_decision` | person | `ok` = agree; any other value = the person's own; blank = not decided |

- Blank is never agreement. Only `ok` or a value decides.
- For a multi-value label, `ok` takes the whole proposed set; a value replaces it whole.
- `<label>_final` is written by the review run: the proposal if `ok`, the value otherwise.
  The log stores the concrete value agreed to, never just `ok`.
- If the proposal changed after the sheet was written (a new prompt version, a re-read), an
  `ok` is refused and the row comes back with the new proposal.
- If a new proposal arrives for a label already decided, the decision stands, and the sheet
  marks the row `proposal changed` so the person can look again.

### 3.6 The two sheets

**Sheet 1, `1_records.xlsx`.** One row per record with a proposal and no decision yet, then
the decided ones for reading. Labels: `scope` (`in` / `out` / `unclear`) and `duplicate_of`
(`new` or `MIG-nnnn`), each proposed with a reason. The evidence columns of today's sheet 1
stay on the right.

- `in` + `new`: a dossier is made, its labels proposed from the record.
- `in` + `MIG-nnnn`: the record joins that incident (`mig_key`) and the dossier's sources.
- `out` or `unclear`: no dossier; `duplicate_of` is not asked.
- `in` with no `duplicate_of` decision: refused, the row comes back.

**Sheet 2, `2_incidents.xlsx`.** One row per incident. Labels: `incident_scope`,
`failure_mode`, `instances`, `evidence_type` (and `risk_factors` when it exists), each
proposed with a reason. Then the facts, `verification` and `verification_note`. Column `ask`
says which labels have no decision yet.

The promote sheet and the edit-dossiers sheet are retired.

### 3.7 The logs

Two logs replace three, with one schema: one row per label decision.

    key, label, proposed, decision, final, decided_on, sheet_generated_on

- `review/record_decisions_log.csv`: `key` is the record's `mig_key`; labels `scope`,
  `duplicate_of`.
- `review/incident_decisions_log.csv`: `key` is the incident's `mig_key`; labels and facts
  from sheet 2.

The three existing logs are converted once, keeping their dates. A past promote `yes` becomes
`duplicate_of = new`; a past `no` becomes a recorded decision not to dossier.

### 3.8 Duplicate proposals (new step)

`dedupe` compares each record decided or proposed `in` with the existing incidents and
proposes `duplicate_of`:

- same URL, or a record already cited by a dossier: that `MIG-nnnn`, high;
- title similarity above a threshold and dates within 90 days, or shared system names:
  that `MIG-nnnn`, with the matches named in `duplicate_of_why`;
- otherwise `new`.

Rules only, no model. The 7 records today merged into existing dossiers (59 records, 52
dossiers) are the test set: the proposer is measured on them before it is used.

### 3.9 Stage and reason

`index` reads the ledger and sets `stage`, `reason` and `in_index` on every row, from the
columns of all the steps. One function, one place. The stages are those of today's index
report, with the promote stage folded into the scope decision.

### 3.10 What else changes

- **`pipeline_flow.html` and its map.** The Promote and Edit dossiers boxes become
  "Decide records" and "Decide incidents"; a Dedupe box is added; the ledger is shown as the
  store every step writes to. The map's counts come from the ledger's `stage` column, so the
  conservation checks become sums over one column.
- **The report (`index_report.html`).** Reads the ledger. Shows each incident's
  `failure_mode_final`, or `failure_mode_proposed` where no decision exists yet, the same
  way. Version 0.2.
- **`index_report.xlsx` and `index_report.py` are removed.** Every sheet in it is a filter
  of the ledger or a copy of the taxonomy. The column descriptions move to the ledger's
  schema doc, `0.2/ledger/README.md`.
- **Docs.** `0.2/README.md`, `docs/` (how_it_works, glossary, definitions, input_layer,
  context_layer), `review/README.md`, `CLAUDE.md` (three trees, ledger, two sheets),
  `OPEN.md`.
- **The skill.** `.claude/skills/classify-incidents` points at `0.2/` and never writes the
  ledger itself; it calls `run.py`.
- **Test run.** `testenv/` gets new stand-ins for the two sheets; `testrun` checks the
  ledger after every step.

## 4. Adversarial review

Each objection raised against the drafts, and what was changed.

| # | objection | resolution |
|---|---|---|
| 1 | Repeating incident labels on every record row double counts incidents and lets copies drift. | Incident labels only on the canonical row, `canonical` flag (3.2). The curator chose one table over two. |
| 2 | Labels in both the ledger and the dossier frontmatter are two sources of truth. | The ledger is the source; the frontmatter is written from it, never by hand; `check` compares them (3.4). |
| 3 | The ledger and the evidence files can disagree, so the ledger is not really the authority. | One writer module; each step writes both in the same run; `check` verifies every `*_ref` (3.2). |
| 4 | Several steps rewriting one CSV can corrupt it or overwrite each other's columns. | Column ownership enforced, atomic writes, one writer (3.2). |
| 5 | `ok` is ambiguous when the proposal later changes: what was agreed to? | The log stores the concrete value; a changed proposal refuses a stale `ok` and flags decided rows (3.5). |
| 6 | Blank meaning "agree" would let unreviewed labels through. | Blank is never agreement (3.5). |
| 7 | Merging scope and promote loses the duplicate check that promote carried. | `duplicate_of` is its own label, proposed by a new step and required for every `in` (3.6, 3.8). |
| 8 | A rule-based duplicate finder will miss some duplicates, making two dossiers for one incident. | Measured on the 7 known merges first; `check` warns on near-identical dossiers. |
| 9 | Long quotes and newlines break CSV in Excel and make diffs unreadable. | No long text in the ledger; evidence stays in jsonl, referenced (3.2). |
| 10 | `loaded_on` backfilled from `fetched_at` is not a load date. | Documented as backfilled; exact from 0.2 on. |
| 11 | Copying `mvp/` to `0.2/` leaves two copies of the data; someone will update the wrong one. | `mvp/` frozen at a named commit; CLAUDE.md and both READMEs say so. |
| 12 | Retiring three logs loses history. | They are converted once into the new logs, dates kept; the old files stay in git history. |
| 13 | `record_key` was never to be shown. | The ledger is internal, like the jsonl files; the rule is extended to say so (3.3). |
| 14 | Existing machine labels (Claude-written dossiers) would count as decided. | They migrate as proposals with no decision, so they show on sheet 2 as unconfirmed. Existing person-set fields (`set_by_person`, `ours`) migrate as decisions. |
| 15 | A big-bang rewrite breaks the pipeline for days. | Phased (section 5); every phase ends with `check` and `testrun` green and a commit. |
| 16 | A canonical-record change could strand incident labels on the old row. | `ledger.py` moves them in the same write; `check` fails on incident columns set on a non-canonical row. |

## 5. Phases

Each phase ends with `run.py check` exit 0, `run.py testrun` passing, and a commit.

| phase | work | done when |
|---|---|---|
| P0 | Merge `development/input-layer` into `main`, push; branch `development/pipeline-0.2`. | `main` = current branch head on origin. |
| P1 | Copy `mvp/` to `0.2/`, repoint the root, freeze `mvp/` in CLAUDE.md and its README; report `VERSION` 0.2. | `check`, `index`, `report` in `0.2/` give the same outputs as `mvp/`. |
| P2 | `ledger.py`; ledger record columns written by load, prefilter, reading, model, rules; `loaded_on` backfilled; queue and verdicts removed. | Ledger counts equal today's: 45 in, 1,792 not, same stage counts. |
| P3 | Incident columns on canonical rows; dossier frontmatter written from the ledger; migration; `check` rules moved. | Every dossier's old labels equal its ledger row. |
| P4 | `dedupe` step; measure on the 7 known merges. | Result reported to the curator before P5. |
| P5 | Sheets 1 and 2 with proposal and decision; new logs; old logs converted; promote and edit sheets retired. | `testrun` exercises `ok`, own value, stale `ok`, missing `duplicate_of`. |
| P6 | `index` sets stage and reason; map, `pipeline_flow.html`, report from the ledger; `index_report.xlsx` removed. | Map checks pass from the ledger; report unchanged in content. |
| P7 | Docs, skill, CLAUDE.md, memory. | No reference to retired files outside `mvp/` and `poc/`. |
