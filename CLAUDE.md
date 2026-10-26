# Mind the Interagent Gap

Evidence-graded index of multi-agent AI risks (Hammond et al. 2025 failure modes and risk factors) and an inventory of agent-to-agent incidents.

Read `docs/project_outline.md` first: it gives the goal, the three layers (ontology, detection, mapping) and the current step.

## Layout
- `resources/` holds the source documents (papers, reports), starting with Hammond et al. 2025. Ground classification and incident claims in these files and cite file and page.
- `data/*.csv` is the source of truth. Edit only these.
- `build/build_xlsx.py` validates the data and writes `out/`: one workbook, `risk_index.csv` and `associations.csv`. Never edit `out/` by hand.
- Case studies and incidents share the workbook's Evidence sheet, told apart by `evidence_class`. Every score runs over the whole inventory.
- `docs/methodology.md` holds the definitions, evidence rubric and scoring rules. Read it before classifying or scoring.
- `RESOURCES.md` lists curated sources. `OPEN.md` lists open decisions and next tasks.

## Workflow
1. Edit `data/*.csv`.
2. Run `python build/build_xlsx.py`. It must pass validation.
3. Commit the data and the rebuilt `out/` together.

## Rules
- Add an incident only if the behaviour arises from interaction between two or more AI agents (one agent acting on another counts).
- Verify every claim against the primary source before adding it. Record "Verified" or "Partially verified" and the reason in `notes`. A primary source beats a summary.
- One fact per field. Never encode information in parentheses.
- Multi-value fields hold `;`-separated IDs (`FM2;RF5`, `CS1;CS10`).
- Dates are ISO, partial allowed (`2025`, `2025-06`, `2025-06-18`). Use the event date, or the publication date for studies.
- IDs must match a prefix in `data/id_prefixes.csv`. To add a new source collection, add its prefix there first.
- `type` is one of: Observed in real world · Synthetic evidence · Observed in lab · Theoretical.
- Grounding score = highest `evidence_score` / 10 across all evidence tagged with the risk, case studies and incidents alike. Do not sum or average.
