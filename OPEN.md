# Open items

## Layer 1. Ontology (current step)

### Decisions
1. **Evidence tiers.** The project plan names three tiers (manifested, synthetic, theoretical), but `type` has four. Make "Observed in lab" its own tier, or fold it into synthetic?
2. **Synthetic evidence scope.** It now covers the former "Observed in simulation" rows (CS1, CS2, CS3, CS6, CS8, CS9) and AI Village. Should lab probes where agents talk to each other (CS5 steganography) count as synthetic?
3. ~~**Should scored incidents feed grounding?**~~ **Resolved 2026-10-26: yes.** Grounding and every `evidence_score_max` run over the whole evidence inventory. Incidents link directly to failure modes and risk factors; they are deliberately not linked to instances, which are too granular for this scope. See `docs/methodology.md`.
4. **OpenAI swarm granularity.** Record as one campaign or keep separate rows? Rows: AIR-2026-0183, AIR-2026-0219, LW-01, LW-02, LW-03, LW-04.
5. **"See also" references to CS10** (Flash Crash) raise Social Dilemmas, Military Domains and Markets to 9. Split analogy references into their own field?
6. **Rubric.** E1 overlaps `type`. Decide whether to keep it, and whether theoretical rows get their own rubric.
7. **Text-only associations.** Keep the three FM–RF links that have no case study: FM1–RF4, FM2–RF7, FM3–RF2.

### Data tasks
8. ~~Map all AIR, LW and AIV incidents to failure modes and risk factors, and score them on E1–E5.~~ **Done 2026-10-26**, see `docs/mapping_2026-10-26.md`. LW-03 and LW-04 are left unscored pending a scope decision.
9. Check the LW dates against primary sources; they come from forum summaries.
10. ~~Fill the missing `system` for AIR-2024-0043.~~ **Moot 2026-10-26:** the row was removed for failing the inclusion test.
11. Get the full Agent Incident Registry export and screen it beyond the `multi_agent_system` view, which misses the Hugging Face breach. Contact Enkrypt about reuse.
12. Ingest the companyscope register feed with its own ID prefix (add it to `data/id_prefixes.csv`).
13. Check whether the Anthropic CTF incidents and the UK AISI unsanctioned actions involved agent interaction (see `RESOURCES.md`).
14. Re-check AIV-03 and AIV-04 against theaidigest.org and X when they are reachable.
15. Spot-check E5 (venue status) for the Hammond case studies.
16. Add the source documents to `resources/`, starting with the Hammond et al. 2025 PDF.

## Layer 2. Detection
17. Write the one-page coding protocol: the definition of coverage and the 0–3 validity weight.
18. Build `data/evals.csv` (technique, what it measures, method, access, validity note). Seed it from METR, Apollo Research, UK AISI, GovSim, Melting Pot, agent-security benchmarks and steganography evals.

## Layer 3. Mapping
19. Pilot `data/coverage.csv` (risk × technique, coverage, validity) on a subset of risks.
20. Dashboard skeleton: a risk × technique matrix showing grounding, coverage and validity, plus a gap view.

## Watch
21. AI Village Swarm Dynamics Hackathon (Sep 2026) for new synthetic evidence.
22. New Cooperative AI Foundation outputs and forward citations of Hammond et al. 2025.
