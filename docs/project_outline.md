# Project outline: Mind the Interagent Gap

**Owner:** Rafał · **Budget:** 12 hours (ML4Good project) · **Current step:** Layer 1, ontology

## Problem and theory of change
- **Worry:** multi-agent AI risks (collusion, miscoordination, cascading failures, emergent conflict) go undetected as deployment shifts to agents interacting with other agents.
- **Why it happens:** evaluations are overwhelmingly single-agent. Labs, funders and regulators have no clear picture of which multi-agent risks are covered, how validly they are measured, or where the gaps are.
- **Intervention:** an evidence-tiered risk ontology, with existing evals and techniques (METR, Apollo, UK AISI, benchmarks) mapped onto it with validity weighting. The gaps are published as a living dashboard with prioritised eval specs for funders and evaluators.
- **Relevance:** directly actionable for funders and evaluators; links to EU AI Act systemic-risk evaluation obligations; a base for further multi-agent eval research.

## Success criterion
A reviewer opens the dashboard, sees how evaluation methods address each risk and with what validity, and can identify manifested risks that nothing covers.

## Three layers

### Layer 1. Ontology (coverage layer): *in progress*
What multi-agent risks exist, and how well is each one evidenced?
- **Structure:** Hammond et al. (2025) failure modes and risk factors, flattened into one risk index with FM–RF associations. Instances from the paper's Table 1 sit below each risk.
- **Evidence tiers:** each piece of evidence has a `type`: Observed in real world, Synthetic evidence, Observed in lab, or Theoretical. It is scored 0–10 on the evidence rubric in `docs/methodology.md`.
- **Grounding score:** per risk, the strongest case-study evidence (max), on a 0–1 scale.
- **Incident inventory:** real-world, synthetic and lab events that can extend the ontology's evidence beyond the paper.
- **Outputs:** `out/risk_index.csv`, `out/associations.csv`, `out/multi_agent_risk_taxonomy.xlsx`. Case studies and incidents share one Evidence sheet in that workbook.
- **Done:** taxonomy, instances, 13 scored case studies, grounding scores, inventory of 28 events plus the 13 case studies, build pipeline.
- **Remaining:** map and score the inventory events and decide whether they feed grounding (see `OPEN.md`).

### Layer 2. Detection (eval techniques): *not started*
How can each risk be detected or measured today?
- **Eval inventory:** multi-agent evals and techniques, e.g. METR, Apollo Research and UK AISI evaluations, GovSim, Melting Pot, agent-security benchmarks and steganography evals. For each: what it measures, method, access (open, gated, internal) and a validity note.
- **Coding protocol:** one page defining "coverage" and a validity weight from 0 to 3. This weight is separate from the evidence score: the evidence score says how well a *risk* is shown to occur; the validity weight says how well a *technique* measures it.
- **Planned data:** `data/evals.csv`.

### Layer 3. Layer mapping: *not started*
Which risks does each technique cover, and how validly?
- **Coverage map:** risk × technique pairs, each with coverage and an end-to-end construct-validity score. Pilot it on a subset first.
- **Gap view:** risks with high grounding but low or no valid coverage, especially manifested (real-world) ones.
- **Dashboard skeleton:** a risk × technique matrix showing grounding, coverage and validity.
- **Planned data:** `data/coverage.csv`.

## Expected outputs of the first 12 hours
| # | Output | Layer | Status |
|---|---|---|---|
| 1 | Evidence-tiered risk ontology | 1 | Largely done |
| 2 | Eval inventory with validity notes | 2 | To do |
| 3 | One-page coding protocol for coverage and validity (0–3) | 2–3 | To do |
| 4 | Pilot coverage map with end-to-end construct-validity scores | 3 | To do |
| 5 | Dashboard skeleton: risk × technique matrix | 3 | To do |

## Open alignment question
The original plan names three evidence tiers: manifested, synthetic and theoretical. The ontology currently uses four `type` classes, with "Observed in lab" as a separate tier. Decide whether lab evidence becomes its own tier or is folded into synthetic (see `OPEN.md`).
