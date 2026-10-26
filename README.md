# Mind the Interagent Gap

An evidence-graded index of multi-agent AI risks: failure modes and risk factors from Hammond et al. (2025), linked to a growing inventory of real-world, experimental and synthetic agent-to-agent incidents.

The project has three layers: an evidence-tiered risk ontology (coverage), an inventory of detection techniques and evals, and a mapping between them that shows which risks are covered and how validly. The ontology is in progress. See `docs/project_outline.md`.

## Outputs
- `out/dashboard.html`: self-contained dashboard — the risks, how risk factors link to failure modes, how observed evidence maps onto both, grounding per risk, how evidence accumulates over time, and the methodology. Data is inlined, so it opens straight from disk with no server.
- `out/evidence.csv`: every piece of evidence, case studies and incidents, with its instances, E1–E5 breakdown and score.
- `out/instances.csv`: the link layer — each instance, its parent risk, provenance and the evidence routed through it.
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
