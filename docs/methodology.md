# Methodology

## Geometry
- **Risks** are failure modes (FM1–FM3: Miscoordination, Conflict, Collusion) and risk factors (RF1–RF7), from Hammond et al. (2025), *Multi-Agent Risks from Advanced AI*, arXiv:2502.14143.
- The **risk index** (`out/risk_index.csv`) is flat. Each row is one FM or one RF with a single `grounding_score`.
- **Associations** (`data/associations.csv`) are FM–RF links. Each is either co-tagged by a case study (`case_study_link = TRUE`) or only cross-referenced in the paper's text (`FALSE`).
- A risk signal feeds a risk factor and, through its associations, a failure mode. Use only `TRUE` links for evidence-only routing; under that rule Network Effects has no failure mode.
- **Instances** (`data/risk_instances.csv`) are the paper's Table 1 sub-topics of each risk. **Directions** are its research directions.

## Inclusion test for incidents
An event is in scope if the behaviour arises from interaction between two or more AI agents, including one agent acting on another (injection, recruitment, deception). One agent misbehaving while others happen to be present is out of scope.

## `type` (evidence class)
| Class | Definition |
|---|---|
| Observed in real world | Deployed systems acting on real stakes, outside experimenter control |
| Synthetic evidence | Agents interacting in a simulated or researcher-built environment: modelled worlds such as markets, commons and wargames, and open-ended agent environments such as AI Village |
| Observed in lab | Controlled experiment on real models in a narrow task probe, with no environment |
| Theoretical | Argument, formal model or non-AI analogue only |

- Multi-source cases are classified by their strongest evidence, with the source used named in `type_note`.
- CS8 assumption: the Gu et al. (2024) million-agent network is treated as a simulated environment.
- Agent Incident Registry mapping: In the wild and Safety failure → Observed in real world. Research demo and Disclosed vulnerability → Observed in lab.

## `system_basis`
- Advanced AI agents: LLM or foundation-model agents.
- Simple systems: RL, rule-based or algorithmic systems.
- Agent-agnostic: theory about rational agents in general.

## Evidence score
Each empirical case is scored 0–2 on five criteria, summed to 0–10.

| Criterion | 2 | 1 | 0 |
|---|---|---|---|
| E1 ecological validity | Real world | Synthetic evidence | Lab |
| E2 causal attribution | Controlled comparison isolating the multi-agent mechanism | Quasi-experimental, correlational or contributing factor | Anecdotal or inferred |
| E3 scale and precision | Large n or multiple models/seeds, quantified effect | Small n, single model or few seeds | Qualitative only |
| E4 independent corroboration | Two or more independent sources agree | One corroborating source | None |
| E5 source vetting | Peer-reviewed or official investigation | Preprint, book, journalism, operator blog | Unreviewed, including the report's own experiments |

**Bands:** Strong 9–10 · Moderate 6–8 · Limited 3–5 · Weak 0–2. Theoretical rows are not scored.

## Aggregation
- `grounding_score` of a risk = max `evidence_score` / 10 over case studies tagged with it.
- `evidence_score_max` of an FM–RF link or an instance = max over its case studies.
- Max is used because corroboration is already scored inside each case (E4), and summing would let many weak studies outrank one strong one.
- Case studies tagged only with a risk factor (CS7, CS8, CS10, CS12, CS13) count towards that risk factor only.

## Instance evidence basis
- **Case study:** at least one linked case study. `case_studies_explicit` means the paper cross-references it in that paragraph; `case_studies_placement` means the box sits in that discussion without an explicit reference.
- **Cited empirical work:** no case study, but the paper cites empirical studies.
- **Theoretical:** argument, formal model or non-AI analogue only.

## Verification
- Check claims against the primary source.
- Record "Verified" or "Partially verified", with the reason, in `notes`.
- Where a summary and a primary source disagree, use the primary and note the conflict.
