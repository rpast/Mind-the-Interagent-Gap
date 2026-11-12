# Mind the Interagent Gap

An evidence-graded index of multi-agent AI risks: failure modes and risk factors from
Hammond et al. (2025), linked to a growing inventory of real-world, experimental and
synthetic agent-to-agent incidents.

The project has three layers: an evidence-tiered risk ontology (coverage), an inventory of
detection techniques and evals, and a mapping between them that shows which risks are
covered and how validly. See `docs/project_outline.md`.

## Two trees

| | |
|---|---|
| **`poc/`** | The proof of concept, **frozen**. It established the ontology and scoring and still builds, but receives no new data. See `poc/README.md`. |
| **`mvp/`** | The current build, started from zero on 2026-11-12. The input layer comes first; detection and mapping follow in the same tree until v1.0. See `mvp/README.md`. |

They share no files. `resources/` (source documents), `docs/project_outline.md`,
`docs/sources.txt`, `RESOURCES.md` and `OPEN.md` are project-level and sit at the root.

## Running

```
pip install -r requirements.txt

python poc/build/build_xlsx.py                      # rebuild the frozen PoC outputs
python mvp/pipeline/run.py update --mode aiid-full  # fetch, screen and index incidents
```

`poc/out/dashboard.html` opens straight from disk with no server; its data is inlined.

## Where things live

- `mvp/incidents/` — one Markdown dossier per incident, the curated record
- `mvp/registry/sources.csv` — the machine-readable source registry the pipeline reads
- `mvp/taxonomy/` — risks, the instance repository, associations, evidence types
- `RESOURCES.md` — the human lead list: what is worth reading and what blocks reading it
- `docs/sources.txt` — the audit trail: which source backs which row, and what was screened
  and rejected
- `OPEN.md` — open decisions and next tasks

## Data reuse

Incident rows cite their sources. The Agent Incident Registry asks users to contact Enkrypt
AI before reusing its dataset. The MIT AI Risk Navigator is a research prototype,
"preliminary and not yet validated", and asks that its visualizations not be redistributed.
`mvp/registry/sources.csv` records the reuse status of every source.
