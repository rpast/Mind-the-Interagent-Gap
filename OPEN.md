# Open items

## Layer 1. Ontology (current step)

### Decisions
1. **Evidence tiers.** The project plan names three tiers (manifested, synthetic, theoretical), but `type` has four. Make "Observed in lab" its own tier, or fold it into synthetic?
2. **Synthetic evidence scope.** It now covers the former "Observed in simulation" rows (CS1, CS2, CS3, CS6, CS8, CS9) and AI Village. Should lab probes where agents talk to each other (CS5 steganography) count as synthetic?
3. ~~**Should scored incidents feed grounding?**~~ **Resolved 2026-10-26: yes.** Grounding and every `evidence_score_max` run over the whole evidence inventory. Incidents link directly to failure modes and risk factors; they are deliberately not linked to instances, which are too granular for this scope. See `docs/methodology.md`.
4. **OpenAI swarm granularity.** Record as one campaign or keep separate rows? Rows: AIR-2026-0183, AIR-2026-0219, LW-01, LW-02, LW-03, LW-04.
5. ~~**"See also" references to CS10**~~ **Resolved 2026-10-26:** Table 3 is authoritative for a case study's risks, so an evidence→instance link is only valid where the instance's risk is ticked there. The Flash Crash no longer grounds Conflict or Collusion.
6. **Rubric.** E1 overlaps `type`. Decide whether to keep it, and whether theoretical rows get their own rubric.
7. **Prose-only associations.** FM1–RF4 and FM2–RF7 are asserted in the text with nothing evidencing either end-pair. FM3–RF2 is no longer in this set. Keep, or mark provisional? Associations now record `basis`, so the distinction is at least visible.

### Data tasks
8. ~~Map all AIR, LW and AIV incidents to failure modes and risk factors, and score them on E1–E5.~~ **Done 2026-10-26**, see `docs/mapping_2026-10-26.md`. LW-03 and LW-04 are left unscored pending a scope decision.
9. Check the LW dates against primary sources; they come from forum summaries.
10. ~~Fill the missing `system` for AIR-2024-0043.~~ **Moot 2026-10-26:** the row was removed for failing the inclusion test.
11. Get the full Agent Incident Registry export and screen it beyond the `multi_agent_system` view, which misses the Hugging Face breach. Contact Enkrypt about reuse.
12. Ingest the companyscope register feed with its own ID prefix (add it to `data/id_prefixes.csv`).
13. **Anthropic CTF and UK AISI unsanctioned actions.** **Partially resolved 2026-10-26:** the CAIF report *Lessons from Recent Multi-Agent Safety Incidents* surfaced GTG-1002 and UK AISI Mythos 5 as multi-agent candidates, so neither is simply single-agent. Neither has been screened against the inclusion test or added. A third lead, found 2026-11-09: AIID incident 1633, "Anthropic and OpenAI AI Agents Reportedly Took Unsanctioned Actions on the Live Internet" (2026-07-26). Remaining: screen all three and record the verdicts in `docs/sources.txt`.
14. Re-check AIV-03 and AIV-04 against theaidigest.org and X when they are reachable.
15. Spot-check E5 (venue status) for the Hammond case studies.
16. Add the source documents to `resources/`, starting with the Hammond et al. 2025 PDF.
23. **AIID and the MIT AI Risk labels.** Fetched 2026-11-09 with `build/fetch_aiid.py` into `resources/aiid/`: 1,803 incidents and 2,623 classifications (MIT 1,498 · GMF 326 · CSETv1 214 plus 485 per-annotator · CSETv0 100). Established:
    - The MIT labels are reachable through the AIID GraphQL API as `classifications` with `namespace: "MIT"`, carrying `Risk Domain`, `Risk Subdomain`, `Entity`, `Intent` and `Timing`.
    - **Subdomain 7.6 "Multi-agent risks" does not occur in the AIID copy.** 21 distinct subdomains, topping out at 7.4; 7.2, 7.5 and 7.6 never appear. The MIT AI Risk Navigator does use 7.6 — AIID incident 7 (Wikipedia bot loop) is 7.6 there and 7.3 in the AIID copy — so the AIID export is an older classification run.
    - `notes` is empty on all 1,498 MIT rows. The per-decision reasoning is Navigator-only, so label mismatches cannot be adjudicated from AIID data.
    - 305 of 1,803 incidents carry no MIT row at all, and they are the recent ones.
    - The Navigator facet `behaviour=Multi-agent` returns 28 incidents, all matched to AIID ids (`resources/aiid/navigator_multiagent.tsv`). 6 are already in `data/incidents.csv`, 22 are new.
    - Of our 27 incidents, 9 are in AIID. 3 of those are in AIID but untagged by the Navigator (LW-01 Hugging Face swarm, LW-02 Vanderbilt, AIR-2025-0027) — a 33% false-negative rate for that rater. 18 are absent from AIID entirely, including all 7 AI Village rows. The gap is coverage, not classification.

    Remaining: register an AIID prefix in `data/id_prefixes.csv` (see item 12); screen the 22 new Navigator candidates and the keyword-prefilter survivors in `resources/aiid/candidates_multiagent.tsv` against the inclusion test; decide whether a machine-generated label may ever support an E-score, or only flag a candidate.

## Layer 2. Detection
17. Write the one-page coding protocol: the definition of coverage and the 0–3 validity weight.
18. Build `data/evals.csv` (technique, what it measures, method, access, validity note). Seed it from METR, Apollo Research, UK AISI, GovSim, Melting Pot, agent-security benchmarks and steganography evals.

## Layer 3. Mapping
19. Pilot `data/coverage.csv` (risk × technique, coverage, validity) on a subset of risks.
20. Dashboard skeleton: a risk × technique matrix showing grounding, coverage and validity, plus a gap view.

## Watch
21. AI Village Swarm Dynamics Hackathon (Sep 2026) for new synthetic evidence.
22. New Cooperative AI Foundation outputs and forward citations of Hammond et al. 2025.
