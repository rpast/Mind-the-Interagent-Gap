# Mind the Interagent Gap

Evidence-graded index of multi-agent AI risks (Hammond et al. 2025 failure modes and risk
factors) and an inventory of agent-to-agent incidents.

Read `docs/project_outline.md` first: it gives the goal and the three layers (ontology,
detection, mapping).

## Two trees — do not mix them

- **`poc/` is frozen.** Reference only. It still builds, but it gets no new data and no new
  features. Do not add incidents, columns or files to it. See `poc/README.md`.
- **`mvp/` is the live build.** Everything new goes here. It was started from zero on
  2026-11-12 and does not preserve the PoC's structure. See `mvp/README.md`.

Project-level files stay at the root: `resources/` (source documents),
`docs/project_outline.md`, `docs/sources.txt`, `RESOURCES.md`, `OPEN.md`.

## Layout

- `resources/` holds the source documents (papers, reports), starting with Hammond et al.
  2025. Ground every classification and incident claim in these files and cite file and page.
- **Two keys name every incident and every record a person reviews.** `mig_key`, MIG-nnnn,
  is ours: unique, given once in `mvp/registry/mig_keys.csv` when a record first reaches the
  decide-scope sheet, kept by its dossier (`mvp/incidents/<mig_key>.md`), never changed or
  reused. `source_key` is the key the source itself uses (AIID's `794`), blank when it has
  none. Never name an incident by its source (no `AIID-nnnn` ids). `record_key`
  (`aiid:794`) is only the pipeline's internal join key on its own files; no sheet, log,
  dossier or report shows it.
- `mvp/registry/sources.csv` is the source registry: the machine-readable spine the pipeline
  reads. `RESOURCES.md` is the human lead list. `docs/sources.txt` is the per-row audit
  trail. A source may appear in all three, but each note belongs to exactly one.
- `mvp/taxonomy/` holds risks, the instance repository, FM–RF associations and the evidence
  types. The pipeline and the classifiers read it; it is hand-curated.
- `mvp/raw/<source>/` is verbatim fetch output. Never hand-edit it. `mvp/raw/manual/` holds
  machine-made copies of the curator's hand write-ups.
- `mvp/records/<source>.jsonl` is normalised, append-only and content-hashed. Machine-written.
  `mvp/records/manual.jsonl` holds the incidents added by hand.
- `mvp/context/<source>.jsonl` is what each source says about the facts the gates need: a
  reading, with quotes and the depth read. Machine-written. See `mvp/docs/context_layer.md`.
- `mvp/review/` holds the three sheets a person fills in (`1_decide_scope.xlsx`,
  `2_promote.xlsx`, `3_edit_dossiers.xlsx`; generated, gitignored) and their logs
  (`scope_decisions.csv`, `promote_decisions.csv`, `dossier_edits.csv`; data, committed,
  written only by `run.py review` when it reads a filled sheet). See `mvp/review/README.md`.
- `mvp/incidents/<ID>.md` is the curated record: one dossier per incident a person
  promotes. Scope decisions that are not promoted live in `mvp/review/scope_decisions.csv`.
  Hand-edited, or filled by Claude when the curator asks (see Rules).
- `mvp/proposals/` holds classifier output. It is never authoritative; a human promotes.
- `mvp/out/` is generated. Never edit it by hand. `mvp/out/index_report.xlsx` is the index
  report: every incident in the index, and every record that is not, with the reason.
  `mvp/out/index_report.html` is the published report for readers, built by
  `run.py report` from `mvp/pipeline/report/`.
- `mvp/testenv/` holds the test run's fixtures: made-up incidents and the stand-ins for
  skill and human work. `run.py testrun` runs the real steps on them in a temp folder. Never
  put real incidents there. See `mvp/testenv/README.md`.

## Workflow

Where system Python lacks openpyxl (as on the Raspberry Pi host), run every command below
with `.venv/bin/python` instead of `python`.

1. `python mvp/pipeline/run.py update [--refetch] [--manual DIR] [--discover]`, or start the
   same run from the page `python mvp/pipeline/run.py serve` puts on 127.0.0.1. Default: the
   AIID baseline from the saved snapshot. `--discover` is a placeholder, not built yet.
2. Run `/classify-incidents` in Claude Code to read the sources and write proposals. It
   runs `python mvp/pipeline/run.py derive`, which derives the labels by rule
   (`mvp/pipeline/derive.py`) into `mvp/state/verdicts.jsonl`, and assigns instances to the
   records `python mvp/pipeline/run.py instances-due` lists.
3. Decide on the sheets in `mvp/review/` (`python mvp/pipeline/run.py review` writes
   them): fill `decision` in `1_decide_scope.xlsx` (in, out, unclear), run `review`, then
   fill `promote` in `2_promote.xlsx` (yes makes the blank dossier). Check against
   `mvp/proposals/` and `mvp/state/verdicts.jsonl`; promote what passes the
   inclusion test. Before promoting, check each record against the existing dossiers and
   `OPEN.md` for duplicates: a record that is already an incident is added to that
   dossier's `sources`, not promoted. The dossier keeps its `mig_key`; if AIID becomes
   the canonical source, `source_key` changes to AIID's key.
4. Fill each new dossier by hand, or ask Claude to fill it from the readings (see Rules).
   To set or correct a dossier's labels, scope, verification or facts, change the cells
   of `3_edit_dossiers.xlsx` and run `review`: each field changed there is named in the
   dossier's `set_by_person` and logged in `mvp/review/dossier_edits.csv`. Never remove
   a field from `set_by_person`, and never overwrite a field it names without the
   curator's say.
5. `python mvp/pipeline/run.py check` — must exit 0.
6. `python mvp/pipeline/run.py index`, `viz`, then `python mvp/pipeline/index_report.py`
   for `mvp/out/index_report.xlsx`.
7. When the index is worth reporting: `python mvp/pipeline/run.py report` builds the
   published report, `mvp/out/index_report.html`. It is a step of its own, never
   part of `update`, and so is publishing it to its claude.ai page. See
   `mvp/pipeline/report/README.md`.
8. Commit the records, the dossiers and the rebuilt `mvp/out/` together.

## Rules

- Add an incident only if the behaviour arises from interaction between two or more AI
  agents (one agent acting on another counts). A swarm doing what one capable agent could
  have done is a multi-agent *setup*, not a multi-agent *risk*.
- Verify every claim against the primary source before adding it. Record the verdict in
  `verification` and the reason in `## Verification notes`. A primary source beats a summary.
- **An external or machine label may mark a candidate. It may never, by itself, put an
  incident in scope.** Only a human verdict sets `multi_agent: true` with
  `multi_agent_label_source: ours`. Inherited labels go in `external_labels`, never
  overwritten and never merged with ours.
- **Read before you judge.** No label is derived from a fact nobody looked for. A source that
  was read and is silent is `not_stated` and yields `unclear`; a fact not looked for is
  `unread` and yields nothing. `run.py readiness` says which records can be classified.
- **Count agents, not systems.** One product, platform or operator can hold several agents.
  A record that shows one agent only, or none, is out of scope.
- **The flag rule.** A record queued by the `label` or `keyword` prefilter arm is never
  dismissed as single-agent on its record text alone; a `secondary` or better reading must
  confirm it.
- **Manual incidents**, added with `update --manual DIR`, are in scope on the curator's word, which is a
  human verdict. Their failure mode, evidence type and instances are still judged, and a
  dossier resting only on the write-up is never `verified`.
- **Claude-written dossiers.** Claude fills a promoted dossier only when the curator asks,
  and only from what the pipeline holds: the scope and promote decisions, the verdict, the
  `extract_gate` facts, the context reading and the `assign_instances` proposal. Such a
  dossier is always `unverified` until a person checks it against the primary source, and
  its `## Verification notes` open with "Written by Claude". Scope stays the person's
  decision. A failure mode derived by rule carries `failure_mode_source:
  classifier:<prompt>@<version>`, never `ours`. Instances quoted at `high` or `medium` are
  adopted; `low` ones are listed in the notes only. An evidence type that cannot be derived
  is not guessed: the setting is read first.
- For file changes, use the Edit tool, not python/sed/heredoc scripts. If you need a script,
  write it to a file first, then run it.
- One fact per field. Never encode information in parentheses.
- Multi-value fields hold `;`-separated IDs. Dates are ISO, partial allowed (`2026`,
  `2026-06`, `2026-06-18`). Use the event date, or the publication date for studies.
- `evidence_type` is one of: `real_world` · `synthetic` · `lab` · `theoretical`.
- The failure mode comes only from the Gate 2 tree. Instances are descriptive and assigned
  independently; neither is derived from the other (`mvp/docs/definitions.md` § Instances).
- Never infer an FM–RF link from two tags on one row; associations come only from Hammond
  et al., with `basis` recording which.
- Scoring is parked. No E1–E5 anywhere in `mvp/`.
- Never read `mvp/pipeline/pipeline_flow.html` whole: it is about 140 KB.
  Search it (`grep -n`), or read only the lines you need with an offset
  and limit.
