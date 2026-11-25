# review

Where a person decides. Two spreadsheets, two logs. Since 0.2 (`../docs/plan.md`, P5); the
code is `../pipeline/decide.py`.

| file | what | who writes it |
|---|---|---|
| `1_records.xlsx` | sheet 1: one row per record awaiting a person: its scope and, if in, whether it is an incident the index already holds | `run.py review`; a person fills it |
| `2_incidents.xlsx` | sheet 2: one row per incident: its labels and facts | `run.py review`; a person fills it |
| `record_decisions_log.csv` | every decision made on sheet 1, one row per label | `run.py review`, when it reads sheet 1 |
| `incident_decisions_log.csv` | every decision made on sheet 2, one row per label or fact | `run.py review`, when it reads sheet 2 |

Both logs have the same columns: `mig_key, label, proposed, decision, final, reason,
decided_on, sheet_generated_on`. `proposed` is what the pipeline proposed, `decision` what
the person wrote (`ok` or a value), `final` the value it settled on. They are append-only;
the newest row per `mig_key` and label wins. The current values are also in the ledger
(`../ledger/ledger.csv`): the record decisions in its `scope_*`, `duplicate_of_*` and
`dossier_*` columns, the incident's in its incident columns.

The sheets are generated and not committed (`.gitignore`). The logs are data and are
committed. Do not edit them by hand.

## Proposal and decision

Every label on both sheets has three columns:

| column | holds |
|---|---|
| `<label>_proposed` | the pipeline's proposal |
| `<label>_why` | why: the rule, the confidence, the evidence |
| `<label>_decision` (yellow) | yours: `ok` to agree with the proposal, or your own value |

- **Blank is never agreement.** A label you leave blank stays undecided.
- For a list (instances), `ok` takes the whole proposed list; your own list replaces it.
- If the proposal changed after the sheet was written (a new prompt, a new reading), an
  `ok` is refused and the row comes back with the new proposal. The log keeps the value
  you agreed to, not just `ok`.

## Sheet 1: decide records

One row per record that has a verdict and is in no incident yet, with no decision. Column
`ask`: `yes` (the rules propose in, or the model's confidence is low: decide it), `check`
(the rules propose out: decide only to sample-check them), `duplicate` (you decided it in;
it still needs `duplicate_of`).

- `scope_decision`: `ok`, `in`, `out` or `unclear`.
  - in: two or more AI agents, and the harm came from them acting on each other;
  - out: one agent, or many doing what one could have done;
  - unclear: the source was read and does not say.
- `duplicate_of_decision`, needed for every record decided in: `ok`, `new`, or the MIG
  key of the incident the record already is. The proposal comes from
  `pipeline/dedupe.py` (same url, or close text and dates).
- `reason`: optional, one line; it goes into the log.

What the next run does: `in` + `new` makes the dossier (its labels proposed from the
record; its scope decided, by you); `in` + a MIG key adds the record to that incident's
sources; `out` and `unclear` are logged and the record leaves the sheet. A row with a value
that is not allowed, or `in` with no `duplicate_of`, is reported and comes back.

Right of the yellow columns: everything extracted for the record (the model's answers
with quotes, the rules' steps, the reading of the source).

## Sheet 2: decide incidents

One row per incident. For `incident_scope` (in, out, unclear), `failure_mode` (FM1, FM2,
FM3, none), `instances` (ids separated by `;`, or none) and `evidence_type` (real_world,
synthetic, lab, theoretical): the proposal, its reason, and your decision. A label you
decided before shows its value in the decision column; change it to change the label.
Column `ask` lists the labels with no decision yet.

Then the facts, filled with their current value: `incident_title`, `occurrence_date`,
`actor_count`, `interaction_kind`, `systems`, `instances_presumed`, `verification`,
`last_verified`. Change a cell to change the fact. `reason` is added to the incident's
scope basis; `verification_note` to `## Verification notes`, dated. Raising `verification`
sets `last_verified` to today unless you set it.

A row is not written when a value is not allowed, when a fact changed after the sheet was
written, or when the result would break a dossier rule (`run.py check`).

## The dossier is written from the ledger

An incident's labels and facts live in the ledger. After every review run the dossier's
frontmatter is written from it. Do not edit them in the dossier: `run.py check` fails on a
dossier whose labels differ from the ledger, and the next review writes them back. The
dossier's prose (its sections, `multi_agent_basis`, `sources`) is written by hand.

## What happens on the next run

Save the files and close them. Then run `python 0.2/pipeline/run.py review`, or press
Continue on the page `run.py serve` puts up (the Review step), or run `update` again. The
run reads sheet 1 and acts on it, places the incidents in the ledger, reads sheet 2,
writes the dossiers from the ledger, proposes duplicates, and writes both sheets again.

Without openpyxl the step says `install openpyxl: pip install -r requirements.txt`, skips
the sheets, and the rest of the run goes on.

## Before 0.2

The three sheets of 0.1 (`1_decide_scope`, `2_promote`, `3_edit_dossiers`) and their logs
were retired on 2026-11-25. `pipeline/migrate_logs_20261125.py` carried every logged
decision into the two logs above: a scope decision as label `scope`; a promote `yes` as
`duplicate_of` `new`; a promote `no` as label `dossier` `no`, as the person wrote it.
