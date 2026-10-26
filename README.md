# Mind the Interagent Gap

An evidence-graded index of multi-agent AI risks: failure modes and risk factors from Hammond et al. (2025), linked to a growing inventory of real-world, experimental and synthetic agent-to-agent incidents.

The project has three layers: an evidence-tiered risk ontology (coverage), an inventory of detection techniques and evals, and a mapping between them that shows which risks are covered and how validly. The ontology is in progress. See `docs/project_outline.md`.

## Outputs
- `out/risk_index.csv`: one row per failure mode or risk factor, with a grounding score from 0 to 1 and associations.
- `out/associations.csv`: failure mode–risk factor links, with the case-study link flag and grounding scores.
- `out/multi_agent_risk_taxonomy.xlsx`: risk index, links, taxonomy, instances, evidence and sources, with live formulas. Its Evidence sheet is the one table of evidence: Hammond case studies and inventory incidents together, told apart by `evidence_class`.

## Build
```
pip install -r requirements.txt
python build/build_xlsx.py
```
Edit `data/*.csv`, never `out/`. Put source documents in `resources/`. See `docs/methodology.md` for definitions and scoring, `RESOURCES.md` for curated links, and `OPEN.md` for open items.

## Data reuse
Incident rows cite their sources. The Agent Incident Registry asks users to contact Enkrypt AI before reusing its dataset.
