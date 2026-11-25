# review

Where a person decides. Three spreadsheets, three logs.

| file | what | who writes it |
|---|---|---|
| `1_decide_scope.xlsx` | sheet 1: every record the rules labelled and every record a dossier cites, one row each; the ones with no scope decision yet take one | `run.py review`; a person fills it |
| `2_promote.xlsx` | sheet 2: records you decided `in` that have no dossier yet | `run.py review`; a person fills it |
| `3_edit_dossiers.xlsx` | sheet 3: every dossier, one row each, with the fields you can set | `run.py review`; a person edits it |
| `scope_decisions_log.csv` | the log of scope decisions: `mig_key, source_id, source_key, decision, reason, decided_on, sheet_generated_on` | `run.py review`, when it reads a filled sheet |
| `promote_decisions_log.csv` | the log of promote decisions: `mig_key, source_id, source_key, decision, note, decided_on, sheet_generated_on` | `run.py review`, when it reads a filled sheet |
| `dossier_edits_log.csv` | the log of dossier fields set on sheet 3: `mig_key, field, old_value, new_value, decided_on, sheet_generated_on` | `run.py review`, when it reads an edited sheet 3 |

Every row of every sheet and log names its record by two keys: `mig_key`, MIG-nnnn, ours,
given in `mvp/registry/mig_keys.csv` when the record first reached sheet 1 and kept by its
dossier; and `source_key`, the key the source uses (with `source_id`), blank when the
source has none. A record a dossier also cites shows under the dossier's `mig_key`.

The sheets are generated, so they are not committed: they are in `.gitignore`. The logs
are data and are committed. They are append-only, and for the two decision logs the newest
row per record wins. Do not edit them by hand, except to take back a decision: delete
its row.

## Sheet 1: decide scope

Open `1_decide_scope.xlsx`. One row is one record. Every record with a verdict is listed,
decided or not, and so is every record a dossier cites. Column `ask` says which ones
need you:

- `yes`: no scope decision yet, and the rules would put the record in, or the model's
  confidence is `low`. These rows come first. Decide them.
- `check`: no scope decision yet, and the rules leave the record out. It is listed so you
  can sample-check the exclusions in case the model got one wrong. Deciding it is
  optional.
- `decided`: you have decided its scope already. Listed for reading only.
- `dossier`: a dossier cites the record. Listed for reading only; change the dossier on
  sheet 3.

On `decided` and `dossier` rows the `decision` cell is not read: a value typed there is
reported and not logged. To take back a decision, delete its row in the log (above).

Read the title and `key_quote`; open `url` when you need more. `rules_say` and
`why_a_person` are the rules' suggestion and the reason it is not settled. Only you put a
record in scope.

Fill the yellow column `decision`, with the drop-down:

- `in`: two or more AI agents, and the harm came from them acting on each other.
- `out`: one agent, or many doing what one could have done.
- `unclear`: the source was read and does not say.

`reason` is optional; a line is worth writing. Leave a row blank to decide later.

Right of `reason` are the rules' intermediate steps (`is_attack`, `presumption_fires`,
`gate1`, `status`, `evidence_type`, `failure_mode`, `instances_presumed`), then every
question the model answered in `extract_gate`, each with its `<field>_quote`. The `Fields`
tab lists every column: who sets it (model, rules, you), what it is, which columns it is
computed from, and the rule. The rules are `mvp/pipeline/derive.py`; the questions are
`mvp/prompts/extract_gate.v4.md` (the `prompt` column names the version a row used).

Further right is everything else extracted for the record: your earlier decision
(`decided`, `decided_on`, `decided_reason`); what the dossier citing it says now
(`dossier_multi_agent`, `dossier_failure_mode`, `dossier_instances`,
`dossier_verification`); the reading of the source from `mvp/context/` (`read_depth`,
`agent_count`, and one `<fact>_reading` column for each of the seven facts, as status,
reading and quote); and the instance proposals from `mvp/proposals/`
(`instances_proposed` with confidence and quote, `instances_rejected` with the reason,
`instances_note`).

## Sheet 2: promote

Open `2_promote.xlsx`. It lists the records you decided `in`. Fill the yellow column
`promote`: `yes` or `no`.

- `yes`: the next run writes a blank dossier in `mvp/incidents/`. Fill it in by hand, or
  ask Claude to fill it from the pipeline's readings (it is then `unverified` until you
  check it; see the Claude-written dossiers rule in `CLAUDE.md`). `run.py check` must
  pass. A record that is not ready to classify is refused and stays on the sheet.
- `no`: the record gets no dossier and does not come back.

Before saying `yes`, check the record is not already an incident: search the existing
dossiers and `OPEN.md`. A duplicate is added to the existing dossier's `sources` instead
of being promoted. Once the dossier cites it, the record drops off the sheet; a `yes`
already typed for it is reported as "not listed" and not logged, which is expected.

## Sheet 3: edit dossiers

Open `3_edit_dossiers.xlsx`. One row is one dossier, filled in with what the dossier says
now. The yellow columns are yours. Change a cell, and the next run writes that field to the
dossier. A cell left as it was is not an edit, so you only touch what you mean to change.

| column | what you can enter | what else the run sets |
|---|---|---|
| `title` | text | |
| `multi_agent` | `true`, `false`, `unclear` | `multi_agent_label_source: ours`; `multi_agent_basis` says you set it, with `scope_reason` |
| `scope_reason` | free text, always blank on a new sheet | added to `multi_agent_basis` |
| `failure_mode` | `FM1`, `FM2`, `FM3`, or empty for none | `failure_mode_source: ours` |
| `instances`, `instances_presumed` | instance ids separated by `;`; presumed is empty or `I28; I29` | |
| `evidence_type` | `real_world`, `synthetic`, `lab`, `theoretical` | |
| `verification`, `last_verified` | `verified`, `partially_verified`, `unverified`; an ISO date | raising verification sets `last_verified` to today, unless you set it |
| `verification_note` | free text, always blank on a new sheet | added to `## Verification notes` as "Curator, <date>: …" |
| `actor_count`, `interaction_kind`, `occurrence_date`, `systems` | a number or `unclear`; the drop-down; an ISO date; names separated by `;` | `occurrence_date_precision` |

**What is recorded.** Every field you change is:

- added to the dossier's `set_by_person` list (a dossier nobody edited here has no such
  key);
- logged in `dossier_edits_log.csv` with its old and new value and the date;
- shown green in `mvp/out/index_report.xlsx`, which also has a `set_by_person` column.

A field you change by editing the dossier's YAML yourself is not tracked; add its name to
`set_by_person` if you want it marked.

**What is refused.** The row is reported by dossier and nothing in it is written when:

- a value is not allowed (not in the drop-down, not an ISO date);
- the edit would break a dossier rule (the same rules as `run.py check`). For example, a
  failure mode on an attack that still carries the presumed `I28; I29`: empty
  `instances_presumed` in the same row;
- the dossier changed after the sheet was written. Your edit is not written over that
  change; enter it again on the new sheet.

The new sheet always shows the dossiers as they are, so a refused edit has to be entered
again.

## What happens on the next run

Save the file and close it. Then either run `python mvp/pipeline/run.py review`, or press
Continue on the page that `run.py serve` puts up (the Review step), or run `update` again.
The run:

1. reads each sheet and checks every filled row; a bad row (a value that is not in the
   drop-down, a record that is not on the sheet) is reported by `mig_key`, left out of
   the log, and comes back on the new sheet;
2. appends the good rows to the logs, dated today;
3. makes the dossier for every promote `yes`;
4. writes the fields changed on sheet 3 into the dossiers and logs them in
   `dossier_edits_log.csv`;
5. writes all three sheets again from what is left, and says how many rows each has.

The map's Decide scope and Human review boxes count what is left on the two sheets.
`run.py derive` does the same, so a fresh verdicts file gives fresh sheets.

Without openpyxl the step says `install openpyxl: pip install -r requirements.txt`, skips
the sheets, and the rest of the run goes on.
