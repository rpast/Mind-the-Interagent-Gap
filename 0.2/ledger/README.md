# ledger

`ledger.csv`: one row per record the pipeline has ever loaded, one column per value a step
produced for it. It is the source of truth for every column it holds. The design is
`../docs/plan.md`, section 3; the code that reads and writes it is `../pipeline/ledger.py`.

- **Query it directly**: a filter in Excel, `pandas.read_csv`, or DuckDB
  (`SELECT queue_basis, count(*) FROM 'ledger.csv' GROUP BY 1`). No build step.
- **Never edit it by hand.** Each column has one owner, the step that writes it; a step
  writes only its own columns, and replaces them on every row each time it runs.
- **Values are short.** Lists are `;`-separated, booleans `true` / `false`, missing values
  empty. Quotes, readings and reasons stay in the evidence files the `*_ref` columns name.
- One row per record, keyed by `record_key` (`aiid:794`), the pipeline's internal key.

## Columns, by owner

Built so far: P2 of the plan. The incident, decision and outcome columns come in later
phases.

| owner (step) | column | what it holds |
|---|---|---|
| load (`normalise`) | `record_key` | `<source_id>:<source_record_id>` |
| | `source_id`, `source_key` | the source, and the key it uses (blank for a hand-added record) |
| | `title`, `date`, `url` | the record as the source gives it |
| | `loaded_on` | when the record first reached the pipeline; never changes. Backfilled from `fetched_at` for records loaded before 2026-11-25 |
| | `fetched_at` | when its newest version was fetched |
| | `content_hash` | the hash of its newest version (`records/<source>.jsonl`) |
| | `external_ma_label` | outside raters' answers to the multi-agent question, `rater=value` |
| prefilter | `queued` | `true` if a prefilter rule queued it for reading |
| | `queue_basis` | the rule: `recent`, `frozen` or `manual` |
| | `flags` | `label` (an outside rater said yes or maybe), `keyword`, or both |
| | `keyword_terms`, `label_values` | what set the flags |
| readiness | `read_depth` | how far the source was read: `record` … `primary_full`, `curator`, `unreadable` |
| | `agent_count` | `none`, `one`, `several`, `unknown` |
| | `<fact>_status` | for each of the seven facts: `stated`, `not_stated`, `not_applicable`, `unread` |
| | `context_ref` | the context file holding the reading and its quotes |
| derive | `gate_prompt`, `gate_run_date`, `gate_ref` | which extract_gate proposal the answers come from |
| | `n_ai_agents` … `confidence` | the model's extract_gate answers (quotes stay in `gate_ref`) |
| | `rules_version` | the version of `pipeline/derive.py` that derived the rest |
| | `is_attack`, `presumption_fires`, `counterfactual`, `by_presumption` | the rules' intermediate steps |
| | `gate1`, `rules_status`, `why_a_person` | the Gate 1 verdict, the overall status, and why a person must look |
| | `labels_settled` | `false` for a review item: its labels hold only if a person confirms the facts |
| | `rules_multi_agent`, `rules_evidence_type`, `rules_failure_mode`, `rules_instances_presumed` | the labels the rules derive |
| | `scope_proposed`, `scope_why` | the scope the rules propose (`in`, `out`, `unclear`) and why |

| dedupe (`review`, `dedupe`) | `duplicate_of_proposed` | for a record that could be decided in and is in no incident yet: the existing incident it most likely reports, or `new` (`pipeline/dedupe.py`) |
| | `duplicate_of_why` | the evidence: same url, or how close the text is and how far apart the dates |
| incidents (`review`, `index`) | `mig_key` | the record's own key, MIG-nnnn, as the sheets show it; blank until it reaches the decide-scope sheet |
| | `incident_key` | the incident (dossier) the record belongs to; one incident, many records |
| | `canonical` | `true` on the one record that carries the incident's columns |
| *incident level, canonical row only* | `incident_title`, `occurrence_date`, `occurrence_date_precision`, `actor_count`, `interaction_kind`, `systems` | the incident's facts |
| | `<label>_proposed`, `_why`, `_decision`, `_final` | for `incident_scope`, `failure_mode`, `instances`, `evidence_type`, `risk_factors` (reserved): the proposal and its reason, the person's decision, and the value it settles on |
| | `instances_presumed`, `verification`, `last_verified` | as in the dossier |

`rules_*` and `scope_proposed` are proposals. Only a person's decision puts a record in
scope.

**Counting incidents**: filter `canonical = true`; each incident is counted once. A label
is decided when `<label>_decision` is filled (`final` then holds its value); otherwise
`<label>_proposed` is what the incident currently shows. `none` is an explicit empty
answer (no failure mode, no instances); blank means no value.

**Until P5** a dossier's frontmatter still holds its labels, and the incident columns are
rebuilt from it on every `review` and `index`. A label counts as decided when the dossier
says a person set it (`multi_agent_label_source` or `failure_mode_source` `ours`, or the
field in `set_by_person`). The PoC's instances and evidence types, which carry no such
mark, are proposals to confirm (the curator's choice, 2026-11-25). In P5 the direction
turns: the ledger becomes the source and the frontmatter is written from it.
