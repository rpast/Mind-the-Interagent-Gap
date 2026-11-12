# Open items

## Layer 1. Ontology (current step)

### Decisions
1. ~~**Evidence tiers.**~~ **Resolved 2026-11-12:** four labels, lab kept separate — `real_world` · `synthetic` · `lab` · `theoretical`, defined with decision criteria in `mvp/taxonomy/evidence_types.csv`. A narrow probe on real models with no environment is different evidence from a researcher-built world, and folding them loses the distinction that matters for ecological validity. `poc/` keeps its four display names.
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
11. Get the full Agent Incident Registry export and screen it beyond the `multi_agent_system` view, which misses the Hugging Face breach. Contact Enkrypt about reuse. **2026-11-12:** registered as `air_enkrypt` in `mvp/registry/sources.csv` with `reuse_status: permission_needed`; it is browser-gated, so `run.py fetch` emits a work order rather than failing.
12. Ingest the companyscope register feed. **2026-11-12:** registered as `companyscope` in `mvp/registry/sources.csv`, `access_method: json_feed`, status `fetchable`; its own ids also use the `AIR-` prefix, which the `source_id` namespace now keeps apart without needing a prefix table. The adapter is not written.
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

    **Correction of 2026-11-12.** The item above is built on the MIT namespace, and that was the wrong place to look. **AIID's usable multi-agent label is the `CSETv1` namespace attribute `Multiple AI Interaction`**, a purpose-built field with a `yes`/`no`/`maybe` vocabulary: 195 `no`, 12 blank, **5 `yes` — incidents 7, 19, 25, 44, 125** — and 1 `maybe` (47). The three `CSETv1_Annotator-*` namespaces carry the same attribute, so rater disagreement is recoverable. Its limit is coverage: CSETv1 classifies only 214 of 1,803 incidents, so its `no` is weak evidence of absence. Everything said above about the MIT namespace stands; it simply is not where the multi-agent signal lives. The labels are now harvested into `mvp/records/aiid.jsonl` as `external_labels`.

    **The closing question is answered: no.** A machine or external label may mark a candidate and may never, by itself, put an incident in scope. Two measured reasons: the Navigator's rater has a 33% false-negative rate on our own incidents, and CSETv1 means something different from what we mean — its positives include "Sexist and Racist Google Adsense Advertisements" and "Amazon's Robotic Fulfillment Centers Have Higher Serious Injury Rates", neither of which obviously passes Gate 1. `mvp/pipeline/run.py check` enforces this: a dossier with `multi_agent: true` whose `multi_agent_label_source` is not `ours` fails.

    Remaining: screen the 22 new Navigator candidates and the 347 queued prefilter survivors against the two gates.

### New, 2026-11-12 (input layer)

24. **Write the ForumMagnum adapter.** LessWrong, the Alignment Forum and the EA Forum all expose a GraphQL endpoint and are registered as `discovery` sources, but `run.py discover` currently emits a work order for them. This is the main route to incidents AIID does not carry, and 18 of our 27 are in that category.
25. **Link the 27 migrated dossiers to AIID records where they exist.** The migration deliberately does not auto-merge: it looked for close title matches and found none above threshold. OPEN item 23 says 9 of our 27 are in AIID, so the links exist and have to be made by hand. Once a dossier cites AIID, `check` requires AIID to be its canonical source, which renames it from `MIG-nnnn` to `AIID-nnnn`.
26. **Rename four truncated dossier titles.** The migration derived titles from long summary sentences; the dossiers for AIR-2026-0101, AIR-2026-0219, AIR-2026-0194 and AIR-2026-0183 want real names.
27. **Fill `actor_count` and `interaction_kind`** on the 27 migrated dossiers. Both are `unclear` because the PoC never captured them, and the second feeds Gate 2.
28. **Run the calibration set before any bulk classification.** `mvp/gold/multiagent_gold.csv` holds 33 rows: the 27 positives plus AIID's 6 CSETv1 verdicts, which are marked `to_judge` rather than assumed. Baselines to beat are measured: the keyword arm alone gets 78% recall on our positives, the Navigator's rater 67%.
29. **Reconcile the candidate-count discrepancy.** `mvp/raw/aiid/candidates_multiagent.tsv` holds 229 rows (11 strong, 218 weak) where `FETCHED.md` records 11 + 214, and no committed code produces that file. The prefilter now regenerates the queue from committed code; the old TSV should be retired or explained.

## Layer 2. Detection
17. Write the one-page coding protocol: the definition of coverage and the 0–3 validity weight.
18. Build `data/evals.csv` (technique, what it measures, method, access, validity note). Seed it from METR, Apollo Research, UK AISI, GovSim, Melting Pot, agent-security benchmarks and steganography evals.

## Layer 3. Mapping
19. Pilot `data/coverage.csv` (risk × technique, coverage, validity) on a subset of risks.
20. Dashboard skeleton: a risk × technique matrix showing grounding, coverage and validity, plus a gap view.

## Watch
21. AI Village Swarm Dynamics Hackathon (Sep 2026) for new synthetic evidence.
22. New Cooperative AI Foundation outputs and forward citations of Hammond et al. 2025.
