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
- `mvp/incidents/<ID>.md` is the curated record: one dossier per judged incident, whatever
  the verdict. Hand-edited.
- `mvp/proposals/` holds classifier output. It is never authoritative; a human promotes.
- `mvp/out/` is generated. Never edit it by hand.
- `mvp/testenv/` holds the test run's fixtures: made-up incidents and the stand-ins for
  skill and human work. `run.py testrun` runs the real steps on them in a temp folder. Never
  put real incidents there. See `mvp/testenv/README.md`.

## Workflow

1. `python mvp/pipeline/run.py update [--refetch] [--manual DIR] [--discover]`, or start the
   same run from the page `python mvp/pipeline/run.py serve` puts on 127.0.0.1. Default: the
   AIID baseline from the saved snapshot. `--discover` is a placeholder, not built yet.
2. Run `/classify-incidents` in Claude Code to read the sources and write proposals. It
   runs `python mvp/pipeline/run.py derive`, which derives the labels by rule
   (`mvp/pipeline/derive.py`) into `mvp/state/verdicts.jsonl`, and assigns instances to the
   records `python mvp/pipeline/run.py instances-due` lists.
3. Review `mvp/proposals/` with `mvp/state/verdicts.jsonl`, promote what passes the
   inclusion test.
4. `python mvp/pipeline/run.py check` — must exit 0.
5. Commit the records, the dossiers and the rebuilt `mvp/out/` together.

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
