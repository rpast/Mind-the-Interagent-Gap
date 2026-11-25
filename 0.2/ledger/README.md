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

`rules_*` and `scope_proposed` are proposals. Only a person's decision puts a record in
scope.
