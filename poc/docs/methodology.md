# Methodology

## Geometry
- **Risks** are failure modes (FM1–FM3: Miscoordination, Conflict, Collusion) and risk factors (RF1–RF7), from Hammond et al. (2025), *Multi-Agent Risks from Advanced AI*, arXiv:2502.14143.
- The **risk index** (`out/risk_index.csv`) is flat. Each row is one FM or one RF with a single `grounding_score`.
- **Associations** (`data/associations.csv`) are FM–RF links, and they come **only from the authors**. `basis` is either `Paper prose`, where Hammond et al. argue the link in the text, or `Paper Table 3 co-tag`, where one of their own case studies sits under both ends. A link is never inferred from our tags co-occurring: two tags on one event are a conjunction, not a connection. The build requires every risk factor to reach at least one failure mode.
- Hammond et al. state the FM–RF categories are "neither exhaustive nor mutually exclusive" (p. 20) and that for some factors, multi-agent security especially, the agents' objectives "may be largely irrelevant". 9 of the 21 possible pairs are never asserted; a missing pair carries no information.
- Evidence routes to a risk through an instance, and no further. Risk-factor grounding is reported against a failure mode as an amplification figure along author-asserted links only.
- **Instances** (`data/risk_instances.csv`) are sub-topics of a single risk, and they are **the link layer between evidence and risk**. Each instance belongs to exactly one risk, so a piece of evidence reaching both a failure mode and a risk factor does so through two separate instances: two independent claims, never evidence that the two risks are related.
- Instances carry a `provenance`: `Hammond Table 1`, or `Ours` where the inventory found behaviour the paper does not instantiate. **Directions** are the paper's research directions.
- **Failure modes are autonomous.** A failure mode is grounded only by evidence of that failure occurring. A linked risk factor's grounding is *routed* to it as an amplification figure and reported separately; the two are never summed.

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
- The evidence inventory is one table: Hammond case studies and incidents, distinguished by `evidence_class`.
- `grounding_score` of a risk = max `evidence_score` / 10 over **all** evidence tagged with it, case studies and incidents alike.
- `amplification` of an FM–RF link = the risk factor's own grounding, routed along the link. It is a mechanism the authors claim, not a measurement of that pair.
- `instance_grounding` = max `evidence_score` / 10 over the evidence assigned to that instance.
- Every scored piece of evidence must carry at least one instance, and its `failure_modes` / `risk_factors` must be exactly the risks its instances reach. The build derives them and fails on any disagreement.
- **Analogy references do not carry evidence.** The paper cites the 2010 Flash Crash when discussing social dilemmas, military domains and markets, but Table 3 does not tick those risks for it. An evidence→instance link is only valid where the instance's risk is among the evidence's Table 3 risks, so the Flash Crash does not ground Conflict or Collusion.
- Max is used because corroboration is already scored inside each row (E4), and summing would let many weak rows outrank one strong one.
- `evidence_n` reports how many rows sit behind a score. Read it with the score: a 0.9 on one row is not a well-studied risk.
- Evidence tagged only with a risk factor counts towards that risk factor only.
- Rows with blank E1–E5 are unscored and ignored by the aggregation.

## Instance evidence basis
- **Case study:** at least one linked case study. `case_studies_explicit` means the paper cross-references it in that paragraph; `case_studies_placement` means the box sits in that discussion without an explicit reference.
- **Cited empirical work:** no case study, but the paper cites empirical studies.
- **Theoretical:** argument, formal model or non-AI analogue only.

## Verification
- Check claims against the primary source.
- Record "Verified" or "Partially verified", with the reason, in `notes`.
- Where a summary and a primary source disagree, use the primary and note the conflict.
