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
- `mvp/raw/<source>/` is verbatim fetch output. Never hand-edit it.
- `mvp/records/<source>.jsonl` is normalised, append-only and content-hashed. Machine-written.
- `mvp/incidents/<ID>.md` is the curated record: one dossier per incident. Hand-edited.
- `mvp/proposals/` holds classifier output. It is never authoritative; a human promotes.
- `mvp/out/` is generated. Never edit it by hand.

## Workflow

1. `python mvp/pipeline/run.py update --mode <labelled-only|aiid-full|all-sources>`
2. Review `mvp/proposals/`, promote what passes the inclusion test.
3. `python mvp/pipeline/run.py check` — must exit 0.
4. Commit the records, the dossiers and the rebuilt `mvp/out/` together.

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
- One fact per field. Never encode information in parentheses.
- Multi-value fields hold `;`-separated IDs. Dates are ISO, partial allowed (`2026`,
  `2026-06`, `2026-06-18`). Use the event date, or the publication date for studies.
- `evidence_type` is one of: `real_world` · `synthetic` · `lab` · `theoretical`.
- Evidence reaches a risk only through an instance. Never infer an FM–RF link from two tags
  on one row; associations come only from Hammond et al., with `basis` recording which.
- Scoring is parked. No E1–E5 anywhere in `mvp/`.
