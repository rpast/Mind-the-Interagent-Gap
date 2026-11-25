# Mind the Interagent Gap

Evidence-graded index of multi-agent AI risks (Hammond et al. 2025 failure modes and risk
factors) and an inventory of agent-to-agent incidents.

Read `docs/project_outline.md` first: it gives the goal and the three layers (ontology,
detection, mapping).

## Three trees — do not mix them

- **`poc/` is frozen.** Reference only. It still builds, but it gets no new data and no new
  features. Do not add incidents, columns or files to it. See `poc/README.md`.
- **`mvp/` is frozen** since 2026-11-25, at commit 61aaa9f. It was copied whole to `0.2/`,
  which carries its data on. It still runs, but gets no new data and no new features. Do
  not write to it. See `mvp/README.md`.
- **`0.2/` is the live build.** Everything new goes here. It continues `mvp/` and is being
  rebuilt around one ledger and two review sheets: `0.2/docs/plan.md`. Its name matches
  the report's version. Work on it happens on branch `development/pipeline-0.2`.

Project-level files stay at the root: `resources/` (source documents),
`docs/project_outline.md`, `docs/sources.txt`, `RESOURCES.md`, `OPEN.md`.

## Layout

- `resources/` holds the source documents (papers, reports), starting with Hammond et al.
  2025. Ground every classification and incident claim in these files and cite file and page.
- **Two keys name every incident and every record a person reviews.** `mig_key`, MIG-nnnn,
  is ours: unique, given once in `0.2/registry/mig_keys.csv` when a record first reaches the
  decide-scope sheet, kept by its dossier (`0.2/incidents/<mig_key>.md`), never changed or
  reused. `source_key` is the key the source itself uses (AIID's `794`), blank when it has
  none. Never name an incident by its source (no `AIID-nnnn` ids). `record_key`
  (`aiid:794`) is only the pipeline's internal join key on its own files, the ledger
  among them; no sheet, log, dossier or report shows it.
- `0.2/ledger/ledger.csv` is the ledger: one row per record ever loaded, one column per
  value a step produced for it (loaded, queued, read, the model's answers, the rules'
  labels). It is the source of truth for those columns. Only `run.py` writes it, each step
  its own columns (`0.2/pipeline/ledger.py`); never edit it by hand. Query it directly. See
  `0.2/ledger/README.md`.
- `0.2/registry/sources.csv` is the source registry: the machine-readable spine the pipeline
  reads. `RESOURCES.md` is the human lead list. `docs/sources.txt` is the per-row audit
  trail. A source may appear in all three, but each note belongs to exactly one.
- `0.2/taxonomy/` holds risks, the instance repository, FM–RF associations and the evidence
  types. The pipeline and the classifiers read it; it is hand-curated.
- `0.2/raw/<source>/` is verbatim fetch output. Never hand-edit it. `0.2/raw/manual/` holds
  machine-made copies of the curator's hand write-ups.
- `0.2/records/<source>.jsonl` is normalised, append-only and content-hashed. Machine-written.
  `0.2/records/manual.jsonl` holds the incidents added by hand.
- `0.2/context/<source>.jsonl` is what each source says about the facts the gates need: a
  reading, with quotes and the depth read. Machine-written. See `0.2/docs/context_layer.md`.
- `0.2/review/` holds the two sheets a person fills in (`1_records.xlsx`: scope and
  duplicate_of per record; `2_incidents.xlsx`: each incident's labels and facts;
  generated, gitignored) and their logs (`record_decisions_log.csv`,
  `incident_decisions_log.csv`; data, committed, append-only, written only by
  `run.py review` when it reads a filled sheet). Every label has a proposal and a
  decision: `ok` agrees, any other value replaces it, blank is never agreement. See
  `0.2/review/README.md`.
- `0.2/incidents/<ID>.md` is the incident's dossier: one per incident. Its prose (the
  sections, `multi_agent_basis`, `sources`) is written by hand, or by Claude when the
  curator asks (see Rules). Its labels and facts (scope, failure mode, instances,
  evidence type, title, date, actors, systems, verification) are a copy written from the
  ledger by `run.py review`: never edit them in the dossier, change them on sheet 2.
  `check` fails on a dossier whose labels differ from the ledger.
- `0.2/proposals/` holds classifier output. It is never authoritative; a human promotes.
- `0.2/out/` is generated. Never edit it by hand. Where every record stopped, and why, is
  the ledger's `stage` and `reason` (set by `run.py index`); there is no separate index
  workbook since 0.2. `0.2/out/index_report.html` is the published report for readers, built by
  `run.py report` from `0.2/pipeline/report/`.
- `0.2/testenv/` holds the test run's fixtures: made-up incidents and the stand-ins for
  skill and human work. `run.py testrun` runs the real steps on them in a temp folder. Never
  put real incidents there. See `0.2/testenv/README.md`.

## Workflow

Where system Python lacks openpyxl (as on the Raspberry Pi host), run every command below
with `.venv/bin/python` instead of `python`.

1. `python 0.2/pipeline/run.py update [--refetch] [--manual DIR] [--discover]`, or start the
   same run from the page `python 0.2/pipeline/run.py serve` puts on 127.0.0.1. Default: the
   AIID baseline from the saved snapshot. `--discover` is a placeholder, not built yet.
2. Run `/classify-incidents` in Claude Code to read the sources and write proposals. It
   runs `python 0.2/pipeline/run.py derive`, which derives the labels by rule
   (`0.2/pipeline/derive.py`) into the ledger, and assigns instances to the
   records `python 0.2/pipeline/run.py instances-due` lists.
3. Decide records on `0.2/review/1_records.xlsx` (`python 0.2/pipeline/run.py review`
   writes it): `scope_decision` (ok, in, out, unclear) and, for every record decided in,
   `duplicate_of_decision` (ok, `new`, or the MIG key of the incident it already is; the
   pipeline proposes one from `pipeline/dedupe.py`, and `OPEN.md` lists known overlaps).
   Run `review`: `in` + `new` makes the dossier, with its labels proposed from the
   record; `in` + a MIG key adds the record to that incident's sources.
4. Write each new dossier's prose by hand, or ask Claude to (see Rules). Decide each
   incident's labels and facts on `0.2/review/2_incidents.xlsx` (ok or your value) and
   run `review`: they go into the ledger and the incident log, and the dossier's
   frontmatter is written from the ledger.
5. `python 0.2/pipeline/run.py check` — must exit 0.
6. `python 0.2/pipeline/run.py index` (the ledger's stage and reason, the index table)
   and `viz` (the map).
7. When the index is worth reporting: `python 0.2/pipeline/run.py report` builds the
   published report, `0.2/out/index_report.html`. It is a step of its own, never
   part of `update`, and so is publishing it to its claude.ai page. See
   `0.2/pipeline/report/README.md`.
8. Commit the records, the dossiers and the rebuilt `0.2/out/` together.

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
- **Claude-written dossiers.** Claude writes a dossier's prose only when the curator asks,
  and only from what the pipeline holds: the record decisions, the ledger, the
  `extract_gate` facts, the context reading and the `assign_instances` proposal. Claude
  never writes a dossier's labels or facts: they come from the ledger, proposed by the
  pipeline and decided by a person on sheet 2. Its `## Verification notes` open with
  "Written by Claude", and it stays `unverified` until a person checks it against the
  primary source.
- For file changes, use the Edit tool, not python/sed/heredoc scripts. If you need a script,
  write it to a file first, then run it.
- One fact per field. Never encode information in parentheses.
- Multi-value fields hold `;`-separated IDs. Dates are ISO, partial allowed (`2026`,
  `2026-06`, `2026-06-18`). Use the event date, or the publication date for studies.
- `evidence_type` is one of: `real_world` · `synthetic` · `lab` · `theoretical`.
- The failure mode comes only from the Gate 2 tree. Instances are descriptive and assigned
  independently; neither is derived from the other (`0.2/docs/definitions.md` § Instances).
- Never infer an FM–RF link from two tags on one row; associations come only from Hammond
  et al., with `basis` recording which.
- Scoring is parked. No E1–E5 anywhere in `0.2/`.
- Never read `0.2/pipeline/pipeline_flow.html` whole: it is about 140 KB.
  Search it (`grep -n`), or read only the lines you need with an offset
  and limit.
