# review

Where a person decides. Two spreadsheets, two logs.

| file | what | who writes it |
|---|---|---|
| `1_decide_scope.xlsx` | sheet 1: records the rules labelled, with no scope decision yet. One row each | `run.py review`; a person fills it |
| `2_promote.xlsx` | sheet 2: records you decided `in` that have no dossier yet | `run.py review`; a person fills it |
| `scope_decisions.csv` | the log of scope decisions: `record_key, decision, reason, decided_on, sheet_generated_on` | `run.py review`, when it reads a filled sheet |
| `promote_decisions.csv` | the log of promote decisions: `record_key, decision, note, decided_on, sheet_generated_on` | `run.py review`, when it reads a filled sheet |

The sheets are generated, so they are not committed: they are in `.gitignore`. The two logs
are data and are committed. They are append-only, and the newest row per `record_key` wins.
Do not edit them by hand, except to take back a decision: delete its row.

## Sheet 1: decide scope

Open `1_decide_scope.xlsx`. One row is one record. Every record with no scope decision is
listed, but column `ask` says which ones need you:

- `yes`: the rules would put the record in, or the model's confidence is `low`. These
  rows come first. Decide them.
- `check`: the rules leave the record out. It is listed so you can sample-check the
  exclusions in case the model got one wrong. Deciding it is optional.

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

## Sheet 2: promote

Open `2_promote.xlsx`. It lists the records you decided `in`. Fill the yellow column
`promote`: `yes` or `no`.

- `yes`: the next run writes a blank dossier in `mvp/incidents/`. Fill it in by hand, as
  before, and `run.py check` must pass. A record that is not ready to classify is refused
  and stays on the sheet.
- `no`: the record gets no dossier and does not come back.

## What happens on the next run

Save the file and close it. Then either run `python mvp/pipeline/run.py review`, or press
Continue on the page that `run.py serve` puts up (the Review step), or run `update` again.
The run:

1. reads each sheet and checks every filled row; a bad row (a value that is not in the
   drop-down, a record that is not on the sheet) is reported by `record_key`, left out of
   the log, and comes back on the new sheet;
2. appends the good rows to the logs, dated today;
3. makes the dossier for every promote `yes`;
4. writes both sheets again from what is left, and says how many rows each has.

The map's Decide scope and Human review boxes count what is left on the two sheets.
`run.py derive` does the same, so a fresh verdicts file gives fresh sheets.

Without openpyxl the step says `install openpyxl: pip install -r requirements.txt`, skips
the sheets, and the rest of the run goes on.
