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
    **Partly done 2026-11-23:** five dossiers linked and renamed, from records a person decided `in` on sheet 1: MIG-0003 → AIID-1054, MIG-0016 → AIID-1668 (also cites aiid:1800), MIG-0017 → AIID-1797, MIG-0019 → AIID-1646, MIG-0020 → AIID-1604. `mvp/gold/multiagent_gold.csv` carries the new ids; the archived review rounds keep the old ones. Still to link: 1556 → MIG-0015 (item 63), and the rest of the nine AIID matches item 23 counts.
    **Changed later on 2026-11-23 (item 51):** linking no longer renames. A dossier keeps its `mig_key`; linking AIID changes `canonical_source` and `source_key` only. The five got their MIG keys back.
26. **Rename four truncated dossier titles.** The migration derived titles from long summary sentences; the dossiers for AIR-2026-0101, AIR-2026-0219, AIR-2026-0194 and AIR-2026-0183 want real names.
27. **Fill `actor_count` and `interaction_kind`** on the 27 migrated dossiers. Both are `unclear` because the PoC never captured them, and the second feeds Gate 2.
28. **Review the gold set before any calibration. Blocking.** Every PoC label came from AI-assisted sessions — all 8 commits carry a Claude co-author trailer — and none was independently checked, so calibrating against it would measure agreement with an earlier model pass rather than accuracy. The PoC's own verification rule was also not met: of 27 incidents, 6 are explicitly *Verified*, 6 *Partially verified*, 8 have notes with no verdict and **7 have no verification record at all**; 14 rest on a single source. Separately and structurally, the set had **no negatives**, so precision could not be measured at all.

    `mvp/gold/multiagent_gold.csv` now holds 60 rows in four strata, all `to_judge`: 27 `poc_positive` being re-verified, 6 `aiid_csetv1`, 18 `queue_boundary` and 9 `queue_base_rate`. The 27 negative candidates come from the prefilter queue, 2025–2026, excluding anything AIID marks multi-agent — **unscreened, not negative**, since AIID applies no multi-agent label in that window. The draw oversamples the keyword arm on purpose, so precision measured against it is pessimistic and describes the boundary, not the population.

    Review with `python mvp/gold/build_review.py` → `mvp/out/gold_review.html`, which hides the prior label behind a toggle so the verdict is formed first. Export and fold back with `--merge`. Only the two measured baselines survive the review unchanged: the Navigator rater's 33% false-negative rate, and the keyword arm's 78% recall (itself provisional, since it is measured against the positives under review).
29. ~~**Reconcile the candidate-count discrepancy.**~~ **Retired 2026-11-16:** the file was read by no code and was removed with `git rm`; the prefilter regenerates the queue from committed code. Original note: `mvp/raw/aiid/candidates_multiagent.tsv` holds 229 rows (11 strong, 218 weak) where `FETCHED.md` records 11 + 214, and no committed code produces that file. The prefilter now regenerates the queue from committed code; the old TSV should be retired or explained.

### New, 2026-11-13 (grey zone: multi-agent attacks)

30. ~~**Do multi-agent attacks pass Gate 1?**~~ **Resolved 2026-11-13: yes, by presumption.**
    Gate 1's worked example ("a swarm of agents breaking into a company's servers does not
    pass") contradicted the paper's own account of RF7: I28 Swarm Attacks turns on "it is the
    number of them that defeats the defence" and I29 Heterogeneous Attacks on combined
    affordances defeating a safeguard none could defeat alone. Both passages apply the
    counterfactual to a different unit — the example to the *class* of event, the instances
    to the *realised outcome*. The instances have it right, and the example is removed.

    The rule: **multi-agent attacks pass Gate 1 unless the source carries positive evidence
    that the multiplicity played no role in the attack's success.** Carried by one extracted
    fact, `multiplicity_role` ∈ `load_bearing` · `incidental` · `unreported`, where
    `load_bearing` and `unreported` both resolve to `could_not` and only `incidental` puts a
    record out. Applied in code, as with Gate 2 and `evidence_type`. Written up in
    `mvp/docs/definitions.md` § "The security branch" and `mvp/docs/classifiers.md`.

    Two things it settles. **Intent does not enter Gate 1** — Hammond p.20, for multi-agent
    security the agents' objectives "may be largely irrelevant"; and unintended harm is not
    miscoordination, which needs agents failing to align *with each other*. **No failure
    mode attaches** — an attacker fleet executing its operator's plan is not misaligned with
    itself, not in mixed-motive interaction with its target, and not colluding against its
    own principal. The brake on scope creep is the failure-mode definitions themselves:
    nothing about a fleet attack satisfies any of the three, so admitting these incidents
    cannot inflate the FM evidence base however many arrive. They accumulate against RF7.

    Known cost, declared rather than hidden: the presumption is recall-favouring on this
    branch. It is there because incident reporting states that a fleet was involved and
    almost never states whether the fleet was why the attack worked, so a proof requirement
    would route nearly every real-world security incident to `unclear` and leave RF7
    grounded in lab work alone.

31. **Re-verdict the security rows in the gold set under the new rule. Blocks calibration.**
    `mvp/out/gold_reviewed_20261113.csv` was reviewed before the rule existed, and seven of
    its 60 rows are security-flavoured: G-016, G-017, G-020, G-047, G-048, G-059, G-060. Two
    are currently inconsistent with each other — G-047 (Canada federal archives, `in`) and
    G-060 (attacker used AI agents to breach an analytics firm, `out`) are substantively the
    same claim with opposite verdicts, which is the grey zone surfacing as rater
    disagreement. Under the presumption G-060 flips to `in` unless its source shows
    `incidental`. G-048 (OpenAI training agent retrieved credentials) describes one agent and
    is unaffected. Set `multiplicity_role` on all seven from their primary sources, then
    recompute Gate 1 accuracy — the `could_not` count moves, so the accuracy figure moves
    with it.

32. ~~**Gate 2 appeared to overrule Gate 1.**~~ **Resolved 2026-11-13.** Gate 2's `opposing`
    branch read "out of scope", so a coordinated attack passed Gate 1 and was then thrown
    out by Gate 2 for the very polarity that makes it an attack. The two gates were doing
    the same job in the documentation and contradicting each other. They are now separated
    explicitly: **Gate 1 alone decides scope; Gate 2 only picks the failure mode and cannot
    send a record back.** `opposing` now yields *no failure mode*, which is already a
    legitimate outcome — most in-scope security incidents carry risk factors only. Changed in
    `definitions.md` (gate preamble, the tree, the `opposing` paragraph), in
    `classifiers.md` (the `failure_mode` code rule), in `extract_gate.v2.md`, and in
    `mvp/gold/gold_review_template.html`, which displayed "out of scope" to the reviewer.

33. **Instances no longer route to failure modes.** **Decided 2026-11-13.** The earlier
    design derived an incident's failure mode and risk factors from `instances.risk_id` and
    cross-checked that against the Gate 2 tree. Dropped: the failure mode is now assigned
    **only** by the Gate 2 tree, working from the FM definitions directly, and instances are
    assigned independently as descriptive detail — useful before any risk is assigned, and
    not causally linked to one. Consequences, documented in `definitions.md` § Instances and
    `classifiers.md`: call 2 emits instance ids and quotes only, the FM cross-check is gone,
    and `no_failure_mode` is no longer a field. `assign_instances.v1.md` still needs
    checking for language that implies the old routing.

34. **Rename the `poc_positive` stratum.** It is a literal value in
    `mvp/gold/multiagent_gold.csv` and in `build_review.py`, and the docs now avoid
    explaining it, so the identifier is the last place the old tree leaks into
    reader-facing material. Suggest `carried_over`. Data change, so it is not done
    unilaterally.

35. **Add `multiplicity_role` to the dossier schema and to `run.py check`.** The field is
    documented but not yet enforced: `check` should require it on any record carrying an RF7
    instance, and reject a blank where the record describes an attack.

### New, 2026-11-13 (gold-set source context)

36. **Gold rows were judged on one-line text.** **Addressed 2026-11-13.** Every row carried
    only its inventory headline: 70–261 characters for the carried-over rows, 335–500 for the
    AIID ones. Facts the gates require — agent count, whether the agents interacted, who
    controlled the environment, what multiplicity contributed — were absent from the text being
    judged. 41 of 60 rows are now enriched from source in `mvp/gold/context/`, field by field
    in the shape the gates ask for. The 19 not enriched are all reviewed `out` and all
    single-system: G-034, G-035, G-036, G-037, G-039, G-040, G-041, G-042, G-043, G-044,
    G-045, G-046, G-050, G-051, G-052, G-053, G-054, G-055, G-057. Their AIID description is
    the full record. Fetch them too if precision needs to rest on more than that.

37. ~~**Two confirmed duplicate pairs in the gold set.**~~ **Resolved 2026-11-13.** Handled
    with a `duplicate_of` column rather than by deleting rows: each pair keeps both rows, since
    a classifier meets them as two separate records and should label both, but they name one
    incident and must be counted once in any inventory or evidence claim.
    - **G-018 and G-049** → canonical **G-049** (`aiid:1800`). Same Vanderbilt link-shortener
      event, same researcher as primary source. AIID is canonical where a record exists.
    - **G-020 and G-024** → canonical **G-020** (the OpenAI technical report). The report
      describes the Artifactory message board and the 4 July outage as one continuous chain from
      May to July 2026, which is what AIR-2026-0183 records from a secondary source.
    - **G-016 (DSEWiki) is not a duplicate.** The registry states it is a second breakout
      distinct from the Hugging Face swarm, so the earlier suspicion is withdrawn.
    - Any metric must therefore report both the row count and the distinct-incident count.
      Currently 23 in-scope rows, 21 distinct incidents.
38. ~~**Rows where the source does not support the verdict.**~~ **Applied 2026-11-13** as
    round 2 of the gold review. Five verdicts flipped, fourteen more rows had their basis
    recorded without a change. Output: `mvp/out/gold_reviewed_20261113_r2.csv`, merged into
    `mvp/gold/multiagent_gold.csv`; per-row reasoning is in `review_note` and in each row's
    `caveat` in `mvp/gold/context/`.
    - **Flipped:** G-005 in→out (one agent, no second actor) · G-059 in→out
      (`multiplicity_role: incidental`, the operator's own review found no coordination) ·
      G-025 in→unclear (sole source a conference schedule entry) · G-031 in→unclear (page
      states no interaction, mechanism, cause or goals) · G-007 in→unclear (source mismatch,
      item 39).
    - **Held, with an explicit human ruling:** G-003 stays in scope. The source does not say
      the 100+ bot personas are themselves AI agents, and the ruling is that it does not
      matter — agenthood here is functional, not architectural. That ruling also resolved
      item 41 and is written up in `definitions.md` § "What counts as an agent".
    - **Held, basis recorded:** G-012 (verification downgraded), G-017 (in by the presumption,
      not by evidence of coordination), G-047, G-060, G-019, G-016, G-038, G-048.
    - `multiplicity_role` is now set on the 12 security rows: 3 `load_bearing`,
      5 `unreported`, 2 `incidental`, 2 `not_applicable`.
    - **The set now reads: 23 in, 33 out, 4 unclear — 23 in-scope rows covering 21 distinct
      incidents.** These are the numbers accuracy must be computed against, and they supersede
      the first-round counts.
39. **G-007 cites a source that does not contain its episode.** The recorded episode is
    game-choice herding with a no-group-chat comparison; the cited LessWrong post describes
    neither. That material is on the AI Village 2025 lessons post (the AIV-02 source) instead.
    Either re-point the row or rewrite it to the copying this page does document (Grok 4
    copying GPT-5), which is thinner and has no stated mechanism.

40. **G-022 (LW-04) cannot be verified with current tooling.** Reuters refuses automated
    fetches at the proxy, not with an HTTP status, so the sole source is unreadable. It stays
    `unclear`. Obtain the article another way or drop the row. Check also that it is not the
    same July 2026 OpenAI episode the Hugging Face report already covers.

41. ~~**Is a rule-based bot an AI agent?**~~ **Resolved 2026-11-13: yes.** Raised because
    AIID's page for incident 7, the Wikipedia bot loop, says it is unclear whether any of the
    bots uses machine learning and thinks it unlikely — and that row is both a gold positive
    (G-033) and the designated end-to-end test in `classifiers.md`. The question was settled
    by the same human ruling that kept G-003 in scope, where the acting parts are 100+
    scripted social-media personas rather than models: **agenthood is functional, not
    architectural.** A thing is an agent when attributing it a goal explains its behaviour
    better than treating it as a mechanism — the intentional stance, after Dennett (1971),
    which the instance repository already applies to I27 Emergent Goals. Written up in
    `definitions.md` § "What counts as an agent". The threshold is deliberately generous and
    does little work on its own; Gate 1 is what keeps cases out. Consequences: G-033 and
    G-003 both stand, and no row in the set turns on how sophisticated its agents were.

42. ~~**`evidence_type` is wrong on the carried-over security rows.**~~ **Corrected
    2026-11-13, but not as stated.** The original claim here — that these rows were labelled
    `real_world` — was wrong and was asserted without checking the dossiers. All seven were
    already `lab`. The real mismatch is `lab` against `synthetic`: `lab` is defined as a narrow
    task probe "with no environment for the agents to act in" and explicitly excludes "anything
    with a persistent environment, which is synthetic". Six of the seven have one — demo
    multi-agent systems, a shared developer workspace, a sales workflow, a ServiceNow instance,
    a simulated six-agent collaboration, connected systems with merged identities — so they are
    now `synthetic`: MIG-0005, MIG-0006, MIG-0008, MIG-0009, MIG-0010, MIG-0026.
    - **MIG-0023 (AIR-2026-0180, adk-python CI) is left as `lab` and is a genuine gap in the
      vocabulary.** Researchers injected into the *live* CI of a public repository. The
      environment is persistent, so not `lab`; it was not researcher-built, so not `synthetic`;
      the experimenter triggered it, so not `real_world`, which excludes "anything an
      experimenter set up". A researcher-run test inside someone else's production system fits
      none of the four labels. Decide whether that case needs its own criterion.

43. **New leads found while enriching.** None screened.
    - AIID 1710, "AI Agent Appearing to Originate from OpenAI Reportedly Attempted to Hack
      U.S. Department of Education Civil Rights Website" (Sep 2026), listed as related to 1731.
    - AIID 1797, "OpenAI AI Agents Reportedly Flooded RubyGems Software Registry with Malicious
      Packages" — the AIID record for the event behind G-017, not yet linked to our dossier
      (OPEN item 25).
    - AIID 1668, the DSEWiki campaign (see item 37).

### New, 2026-11-13 (first accuracy run)

44. ~~**Compute Gate 1 accuracy.**~~ **Done 2026-11-13.** Write-up in
    `mvp/docs/gate1_accuracy.md`, figures in `mvp/out/gate1_accuracy_20261113.json`. Gold set
    after the drops: 57 rows, 21 in / 33 out / 3 unclear, 54 scorable. **The classifier itself
    has never been run** — `mvp/proposals/` does not exist — so only the existing predictors
    could be scored. The carried-over inventory's own labels reach 81.8% precision (18 of 22);
    AIID's CSETv1 human annotators reach 20% (1 of 5).

45. **The gold sample cannot score the keyword prefilter, and the recorded 78% recall is
    withdrawn.** All 18 `queue_boundary` rows tripped the keyword arm, because the stratum was
    defined that way, so the arm is the sampling frame and its precision on those rows is just
    the stratum's base rate — circular. Its recall rests on 3 positives in total. The earlier
    78% figure was measured against unreviewed positives, and 22 of 54 scorable rows have no
    prefilter queue row at all: the keyword net runs over AIID, and most of the index's
    positives are not in AIID. **The keyword arm's recall is unmeasured.** To measure any
    screen honestly, draw the negatives independently of the predictor being scored — a random
    sample of the AIID window, hand-screened, with the arm scored afterwards.

46. **19% of the positives rest on the attack presumption alone.** Four of 21: G-017, G-019,
    G-047, G-049, all `multiplicity_role: unreported`. Two rest on stated evidence (G-020,
    G-016) and 15 are non-security rows passing Gate 1 on interaction. Any claim built on this
    inventory should carry that split, since reversing one rule moves a fifth of the positives.

47. **`build_review.py --merge` silently dropped two columns.** Fixed 2026-11-13. The row
    rebuild copied only columns whose name starts with `review`, so `multiplicity_role` and
    `duplicate_of` were written as empty on every merge even though they were in `REVIEW_COLS`.
    Now keyed off `REVIEW_COLS` itself. Any merge run before this fix lost those two fields;
    `mvp/out/gold_reviewed_20261113_r2.csv` is the authority and was re-merged.

### New, 2026-11-13 (documentation and spillover purge)

48. ~~**Document the gold set and the ceiling.**~~ **Done 2026-11-13.** `mvp/docs/gold_set.md`
    covers what the set is for, the four strata and how each was drawn, the declared sampling
    bias, the two review rounds and why independence mattered, the set as it stands, and the
    ceiling calculation in full — method, why only precision is meaningful, the numbers, the
    four rejected rows, how to read 81.8% and what the ceiling is not. The calculation is now a
    committed tool, `mvp/gold/score_gate1.py`, rather than an ad-hoc script.

49. ~~**Purge earlier-classification spillover from `mvp/`.**~~ **Done 2026-11-13** for
    everything that is a live reference. Changed: the five `prior_*` columns moved out of
    `multiagent_gold.csv` into `mvp/gold/archive/` (they are the ceiling's input, so deleting
    them would make a published number unreproducible); stratum `poc_positive` renamed
    `carried_over`; `prior_basis` on the drawn rows renamed `draw_note`, since it records
    sampling provenance rather than a classification; `legacy_id` removed from all 27 dossiers
    and from the schema in `run.py`; the inherited `multi_agent_basis` string replaced on all
    27 with the actual basis, which is now the 2026-11-13 human review; the "not captured in
    the PoC row" body placeholders rewritten; prose cleaned in `README.md`, `classifiers.md`,
    `input_layer.md`, `definitions.md`, `fetch_aiid.md`, `build_taxonomy_seed.py` and the
    `check` message in `run.py`; the two review exports moved from `mvp/out/` to
    `mvp/gold/archive/` as `review_round1/2_20261113.csv`.

50. **Three places still carry earlier-classification traces, each for a reason. Decide.**
    - **`mvp/gold/archive/`** holds the earlier labels verbatim, including the inherited basis
      text. This is deliberate: it is the audit trail for the 81.8% ceiling, and a measurement
      nobody can recompute is not a measurement. The archive README states that nothing in the
      pipeline reads it and that no label there may put an incident in scope. If the preference
      is for no trace at all, the ceiling has to be treated as a one-off figure recorded in
      prose only, and the archive deleted.
    - **`mvp/records/*.jsonl` carry `meta.poc_event_id`, `meta.poc_source_class` and
      `meta.poc_system`.** Not renamed, because `content_hash` is computed over the whole
      record body: renaming the keys invalidates every hash, and recomputing them would
      falsify the chain whose job is to detect upstream change. Renaming needs a migration that
      rewrites records and hashes together, with the reason recorded.
    - **`mvp/taxonomy/build_taxonomy_seed.py` reads `poc/data/`** as its seed tables. This is a
      genuine build-time dependency on the frozen tree, not a stale reference. The variable is
      now `SEED_TABLES`. It only runs when the taxonomy is re-seeded.

51. **Dossier ids still read `MIG-nnnn`, which stands for the migration.** Renaming is a data
    migration, not a text fix: the ids are referenced by the gold set's `dossier` column, by
    `mvp/out/`, and `check` ties a dossier's id to its canonical source, so a row citing AIID
    is meant to become `AIID-nnnn` (item 25). Do the renaming as one migration, together with
    item 25, rather than piecemeal.
    **Settled 2026-11-23, the other way round.** The curator ruled that two keys name every
    incident: `mig_key`, MIG-nnnn, ours and unique, and `source_key`, the source's own key,
    blank when it has none. MIG no longer stands for the migration: it is the project's key.
    Every record gets one when it first reaches the decide-scope sheet
    (`mvp/registry/mig_keys.csv`, 442 keys), and its dossier keeps it.
    `mvp/pipeline/migrate_mig_keys_20261123.py` renamed the 31 `AIID-nnnn` dossiers: the five
    renamed from MIG earlier that day got their old keys back (MIG-0003, 0016, 0017, 0019,
    0020), the other 26 got MIG-0028 to MIG-0053 in AIID order. Each renamed dossier says so
    in its Verification notes. The decision logs and the gold set were rekeyed. The archived
    review rounds and `poc/` keep the old ids.

52. **Seven dossiers no longer assert `multi_agent: true`.** Set on 2026-11-13 from the review:
    `false` on MIG-0002, MIG-0005, MIG-0013, MIG-0014 (reviewed out) and `unclear` on
    MIG-0007, MIG-0022, MIG-0025. They are retained as screened negatives with the reason in
    `multi_agent_basis`, and `check` passes. Decide whether a dossier that fails Gate 1 should
    stay in `mvp/incidents/` at all or move to a separate screened-out set — keeping them
    inflates "27 dossiers" as a headline count, since only 20 of the 27 are in scope.

### New, 2026-11-14 (open question, not yet designed)

53. ~~**Where does the text the classifiers read come from?**~~ **Decided 2026-11-14: a
    context layer, gated by readiness.** `mvp/context/<source>.jsonl` holds what each source
    says about the seven gate facts, each `stated`, `not_stated` or `unread`, with the depth
    read. `run.py readiness` says per record whether each decision can be made; the
    classifier, `promote` and `check` enforce it. Enrichment runs in two passes — the record
    text for everything, the fetched source only for records not settled as single-system.
    Design, rationale and the alternatives rejected: `mvp/docs/context_layer.md`. Baseline:
    333 of 347 queued records are not ready; 13 of 27 dossier sources are ready, 13
    provisional. The original note follows for the record.

    Still to do: (a) measure the record pass on the gold rows — no `in` row may come out
    single-system; (b) run the record pass over the queue; (c) run the source pass on what
    survives, which needs fetch access the sandbox does not give the pipeline; (d) read the
    primary sources behind the 11 dossiers that rest on a registry entry alone.

    **(a) done 2026-11-15** with `enrich_context.v2`, record text only, on the 22 gold rows
    reviewed `in`: 21 `several`, 1 `unknown` (G-017 / LW-03, whose text names no agent), 0
    `one` or `none`. The pass may run over the queue. The output was a measurement only and
    was not written to `mvp/context/`.

    *Original note.* Raised 2026-11-14 and logged without a design.

    The premise to clear up first: **dossiers are not classifier input.** The flow is
    `raw/` → `records/` → `state/queue.jsonl` → classifier → `proposals/` → human promotes →
    `incidents/`. `SKILL.md` has the classifier read the queue and then the full record from
    `mvp/records/<source_id>.jsonl`, and it never writes a dossier field. A dossier exists only
    after promotion, so there is by construction no dossier for an unclassified incident, and
    there should not be.

    **The problem is what it reads instead.** All 347 queued records are under 600 characters;
    median 406, minimum 70. That is the thinness the gold review just showed to be
    insufficient: the facts the gates require — agent count, whether the agents interacted, who
    controlled the environment, what multiplicity contributed — are usually absent from text
    that short. `extract_gate.v2.md` now asks for `multiplicity_role` and a verbatim quote per
    fact, and records this thin frequently cannot supply either, so the run would yield mostly
    review items rather than labels. `mvp/gold/context/` solves this for 41 rows out of 1,830.

    **Sketched, not decided:** generalise `mvp/gold/context/` into a pipeline layer, e.g.
    `mvp/context/<source>.jsonl`, keyed by `(source_id, source_record_id)` as records are,
    written by a new `enrich` stage between `prefilter` and classification, holding the same
    fields the gold context files already use. It is neither `raw/` (not verbatim) nor
    `records/` (not content-hashed normalisation) but a third machine-written layer: sourced
    facts with quotes, assembled for judgement. The classifier would read record plus context,
    and the gold context files would become its first 41 rows.

    **Open sub-questions.**
    - Enrich the whole queue, or only records the classifier cannot settle? Enriching
      everything is thorough but mostly wasted on clear negatives; enriching on demand is
      cheaper but needs two passes. The gold review suggests the unsettled fraction is large
      but not total.
    - Fetching is partly blocked and rate-limited. Reuters refuses automated fetches outright,
      and the Agent Incident Registry asks to be contacted before reuse, so `reuse_status` in
      the registry has to gate what may be stored rather than merely read.
    - Enrichment is an inference step over fetched text, so it needs a proposal's provenance
      discipline: `prompt_id`, `prompt_version`, `model`, `run_date`, and a quote per field.
    - Does `check` validate the context layer, and does a dossier have to cite it?

54. **Multi-agent attacks carry presumed instances I28 and I29.** **Decided 2026-11-14.**
    G-017, G-019, G-047 and G-049 are confirmed as multi-agent attack cases under the special
    rule: in scope by the presumption, no failure mode, and presumed to show I28 Swarm Attacks
    or I29 Heterogeneous Attacks until the source states otherwise. Written up in
    `definitions.md` § "The presumed instances" and `classifiers.md`. Two consequences fixed
    in the same edit: presumed instances live in `instances_presumed`, apart from quoted ones,
    and Gate 1 no longer requires `interaction_present` on the security branch — the old rule
    would have rejected all four rows, whose sources describe no interaction.

    **Done 2026-11-14:** `instances_presumed` is a required dossier key, empty on all 27;
    `run.py check` accepts it only as empty or exactly I28 and I29, on an in-scope dossier
    with no failure mode and neither id also in `instances`; `SKILL.md` is synced.

    Not yet done: set it on the in-scope security dossiers. MIG-0019 lists I28 as an
    ordinary instance though its source is `unreported`; MIG-0016, MIG-0018 and MIG-0020
    list I28 too and each needs its quote confirmed or the id moved. `check` cannot yet tie
    the field to `multiplicity_role`, which is not in the schema (item 35).

55. ~~**The Gate 2 tree labelled competition as collusion.**~~ **Fixed 2026-11-14.** The
    tree sent every case where cooperation was unexpected to FM3, so two rival agents that
    never cooperated came out as colluding. FM3 now needs two facts: cooperation occurred
    and it was not expected. Everything else goes to the objectives branch. Adds the
    extracted fact `cooperation_occurred` ∈ yes / no / unclear. Changed in
    `definitions.md` (tree and the paragraph under it), `classifiers.md`, `SKILL.md`, a new
    `extract_gate.v3.md` (v2 frozen, never run), and the review worksheet, which gains a
    "Cooperated" question and the gold column `review_gate2_cooperated`, empty on all 57
    rows. No existing gold verdict changed.

    **Dossiers re-checked 2026-11-14 against the primary sources**, with quotes in each
    dossier's verification notes. Read: collusion.wiki in full, OpenAI's technical report
    pp. 1-20 of 32, the METR investigation, both Hugging Face posts, the Nextgov article,
    kennethdegraff.com/swarm (first 85 per cent verbatim), swarmtraces.org, AIID 1668 and 1800.
    - FM3 stands on MIG-0016, MIG-0020 and MIG-0024, each on a quoted instance of one agent
      acting on another's message.
    - FM3 and I35 are withdrawn on MIG-0018 (Vanderbilt): the source shows agents writing to
      a shared place and no agent acting on another's entry. No failure mode; I28 and I29
      presumed.
    - I28: kept on MIG-0016, now quoted (page creation outran the moderator's deletions);
      replaced by a quoted I29 on MIG-0020; removed from MIG-0024.
    - Corrected: MIG-0016's "more than 15,000 edits" is not in the report (it gives ~17,000
      DSEWiki edits and ~18,000 posts); MIG-0020's date is 2026-07-08; MIG-0024's date was
      the disclosure date and is now 2026-05. Two truncated titles renamed (item 26).
      MIG-0020 and MIG-0024 are now `verified`.

    Follow-ups this raised:
    - **MIG-0024 and MIG-0020 are two events in one chain, not duplicates.** OpenAI's report
      separates the May-July Artifactory activity from the Hugging Face intrusion of 8-13
      July. `mvp/gold/dropped.csv` dropped G-024 as a duplicate of G-020 (item 37); revisit.
    - **MIG-0018 may be one operation with MIG-0016** (391 Vanderbilt log addresses appear
      verbatim in the DSEWiki posts). Decide under item 4; if merged, FM3 rests on the wiki.
    - swarmtraces.org does not cover Vanderbilt; the earlier note preferring it was wrong.
    - Not read: OpenAI report pp. 21-32, the last 15 per cent of the DeGraff page, the
      OpenAI blog posts (403), OpenAI's X statement on DSEWiki. `mvp/gold/context/` was not
      updated with these readings.
    - Answer the new "Cooperated" question on the gold rows whenever Gate 2 is reviewed.
      MIG-0019 still lists an unquoted I28 (item 54).

56. **Gold set and dossier changes of 2026-11-14.**
    - **G-024 restored** to the gold set (item 37 reversed for that pair): 58 rows, 22 in,
      33 out, 3 unclear, 55 scorable, 21 distinct incidents. The ceiling is now 19 of 23,
      82.6%. `score_gate1.py` reads a restored row's earlier assertion from the dropped
      archive.
    - **MIG-0018 merged into MIG-0016** (decides item 4 for this pair): one dossier for the
      DSEWiki and Vanderbilt activity, on the 391 shared addresses. G-049 is marked one
      incident with G-016. The primary source calls them "two operations", so the merge is a
      curatorial judgement and says so in the dossier. 26 dossiers.
    - **Gold ids are now permanent** (`mvp/gold/gold_ids.csv`). They were dealt out by
      position, so removing any dossier would have renumbered every later row.
    - MIG-0019 lowered to `partially_verified`: its verdict rests on a registry entry.

57. **Pipeline decisions of 2026-11-14.** **Decided 2026-11-14** with the user.
    - **The record pass counts agents, not systems.** v1 asked how many "AI systems" acted,
      while Gate 1 counts agents, so a product or operator running several agents could be
      dismissed as single-agent. `enrich_context.v2.md` (v1 kept) counts agents: one
      principal is not one agent, a named system with undescribed insides is `unknown`, and
      `one` needs the text to show a single-agent kind of event. A one-agent record is out of
      scope and is not counted among those that can be judged.
    - **The flag rule.** A record the `label` or `keyword` arm queued is never dismissed on
      its record text alone: if the record pass says `one` or `none`, the source pass still
      runs, and the shortcut holds only once a `secondary` or better reading confirms it.
      Dossier sources with no queue row count as flagged.
    - **`update` modes replaced.** `labelled-only`, `aiid-full` and `all-sources` are gone.
      `update` refreshes the AIID baseline from the saved snapshot; `--refetch`,
      `--manual DIR` and `--discover` add to it.
    - **Discover is a placeholder.** Searching the discovery sources is not being built now;
      `--discover` reports "not built yet" and the run continues. Work orders, one note per
      source, become a sub-step of discover; `run.py discover` still writes them.
    - **Manual incidents.** The curator can add incidents by hand from a directory of
      write-ups. They go straight to the ready, in-scope list on the curator's word, with a
      new read depth `curator` between `secondary` and `primary_partial`. Gate 2, evidence
      type and instances are still judged from the write-up, as provisional; a dossier
      resting on it may not be `verified`.
    - **The map page is the front end.** `run.py serve` serves it on 127.0.0.1 with live
      numbers, starts runs, and waits for a person at the steps that need one.
    Documented in `context_layer.md`, `input_layer.md`, `SKILL.md`, `mvp/README.md` and
    `CLAUDE.md`. Also fixed there: the stale claim that evidence reaches a risk only through
    an instance (item 33).

    Still to do: design the discover module. (Item 53a, measuring v2's record pass on the
    gold rows, was done 2026-11-15.)

### New, 2026-11-15 (pipeline map readability)

58. **Make the map's node counts readable.** Parked until after the inventory update. On the
    update of 2026-11-15 the counts could not be followed. One cause is that the nodes count
    different populations without saying so:
    - Normalise counted all sources (1,844 = 1,817 AIID + 27 others), while Fetch and the
      queue were AIID only.
    - Read the source (41) counted readings for existing dossiers (27) together with readings
      of new candidates (14).
    - Ready? (11 of 358) used a total, 361 queued − 3 out of scope, that appears on no other
      node.
    Agreed direction:
    - **One population everywhere.** If the run uses all sources, every node counts all
      sources.
    - **A breakdown on click for every node**, like the Normalise node has now: by source and
      by sub-group, so each figure can be traced to the node before it.

59. **`extract_gate.v3` measured on gold, 2026-11-15. The attack presumption is the weak
    rule.** Blind run on the 55 scorable gold rows, each with its record and its
    `mvp/context/` row, and the labels derived by the SKILL.md rules. Output and per-row
    scores in `mvp/out/calibration/extract_gate_v3_gold_20261115.*`.
    - Overall: 20 TP, 6 FP, 2 FN, 27 TN. Precision 76.9%, recall 90.9%. The hand-curation
      ceiling is 82.6% precision (19 of 23, after the second review round; the 81.8% in
      item 44 is the first round's figure).
    - 49 of 55 rows are review items: confidence below high, or a gate field unclear. Under
      the skill those derive nothing and go to a person. The 6 rows the rules would settle
      on their own are all correct.
    - **5 of the 6 false positives come from the attack presumption**: G-002, G-005, G-013,
      G-056 and G-058, all with `multiplicity_role: unreported`. On three of them (G-005,
      G-013 and G-058) the model answered the counterfactual `could`, and the presumption
      overrode it. G-013 (Moltbook) is people breaching a platform that hosts agents, with
      no AI agent on the attacking side. The sixth, G-014 (sabotage game), is a
      counterfactual call.
    - The 2 false negatives, G-011 and G-012, are low-confidence `unclear` counterfactuals
      on non-attack rows.
    - **Caveat:** the gold rows' readings were written during the review, and some carry
      judgement wording such as "NOT LOAD-BEARING". This measures the gate given good
      readings, not end to end.

    To decide:
    - **Should the presumption need two or more AI agents on the attacking side?** Today
      `unreported` overrides even a `could`. Making it require attacking agents would
      remove G-013. Should it also yield to an explicit `could`? That would remove G-005
      and G-058, at a cost to recall that is not measured.
    - **A `could_not` that the presumption manufactures still has to clear review.** That is
      true now only because the confidence on those rows was below high.

    **Interim instruction, 2026-11-15:** queue gate runs tell the model that
    `multiplicity_role` concerns agents on the acting side. That is consistent with the
    prompt's own definition of `unreported` ("the record describes multiple agents").

    **Decided 2026-11-16: both changes adopted.** `unreported` now resolves to `could_not`
    only if the record does not show fewer than two AI agents (`n_ai_agents` null or 2+)
    and the model's own counterfactual is not `could`. Re-scored on the same 55 gold rows
    with no model call: 20 TP, 3 FP, 2 FN, 30 TN. Precision 76.9% → 87.0%, recall unchanged
    at 90.9%. The three rows removed are G-005, G-013 and G-058, all reviewed `out`. The
    rules now live in `mvp/pipeline/derive.py`; `run.py derive` writes
    `mvp/state/verdicts.jsonl`, and proposals hold model output only.

    Still open: the attacking-side condition rests on `n_ai_agents`, which the prompt asks
    for all agents in the record, not for the attacking side. A prompt v4 with an explicit
    "agents on the attacking side" field would make the rule exact. It needs a gold run.
    Two more changes belong in the same v4:
    - `extract_gate.v3.md` tells the model to count "AI systems, not humans or
      organisations" for `n_ai_agents`. The project rule is to count agents, not systems,
      and the presumption now reads this field.
    - v3 tells the model that "an `unclear` here alongside `unreported` there still
      resolves to in-scope". Since 2026-11-16 that is false when the record shows fewer
      than two AI agents or the model answers `could`. Harmless to the model's output,
      since it only describes code, but the prompt now misdescribes the rule.

60. **The third prefilter arm missed incidents MIT or GMF had classified. Widened
    2026-11-16.** AIID's only multi-agent field, CSETv1 `Multiple AI Interaction`, is on
    313 of 1,817 incidents and on none dated 2025 or later; CSET's annotation is
    discontinued. The third arm, then called `unclassified`, caught only incidents with no classification at
    all, so 772 incidents from 2024 on (282 / 398 / 92 by year) that MIT or GMF had
    classified were screened by the keyword net alone. A random sample of 100, stratified
    by year (seed 20261116), read from record text with `enrich_context.v2`: 74 `one`,
    4 `none`, 18 `unknown`, 4 `several`. Candidates the keyword net missed include AIID 881
    (a Waymo robotaxi and a Serve delivery robot collide), 1412 (an autonomous agent breaks
    into an AI platform) and 1163 (face-swap output defeats AI face recognition). The arm is
    now `unasked`: dated 2024-01-01 or later, and no taxonomy asked the multi-agent
    question. Queue 361 → 1,133. Background in `mvp/docs/aiid_background.md`.

    Still open: incidents before 2024 with no CSETv1 row (386 classified by MIT or GMF
    only, 19 unclassified) are still screened by keyword alone. The keyword arm's recall
    stays unmeasured (item 45).

61. **Data-layer fixes of 2026-11-16.** Done; recorded here because they change how to read
    earlier figures.
    - **A re-fetch created 313 fake versions.** The fetch date inside each external label
      was part of the content hash, so the update of 2026-11-15 reported "327 new or
      changed" where 14 incidents were new and 313 had not changed. The hash now covers
      substance only; `mvp/pipeline/migrate_keys_20261116.py` removed the 313 rows.
      `mvp/records/aiid.jsonl` is back to one row per incident, 1,817.
    - **One key.** Every row of records, queue, readiness, context and proposals carries
      `record_key`, `<source_id>:<source_record_id>`, for example `aiid:1604`.
    - **Provenance.** Every record carries `raw_ref`: the raw file, the source's internal
      id and the fetch date.
    - The hand-copied Navigator list moved from `mvp/raw/aiid/` to `mvp/registry/labels/`,
      because `raw/` is verbatim fetch output.

62. **Instances follow the person's scope decision.** Until 2026-11-16 call 2 ran only on
    records the rules settled in scope without review: 1 of 103 in the first run. A record
    a person put in scope at review got no instance proposal. `run.py instances-due` now
    lists every in-scope record without one, and the skill runs call 2 on that list.

63. **First classifier run over the AIID queue, 2026-11-15/16.** 361 queued records: 258 out
    of scope on a reading (one agent or none), 103 through the gates, of which 102 are
    review items. Six AIID records duplicate existing dossiers and should be linked as
    sources, not promoted (this is item 25 in practice): 1556 → MIG-0015, 1668 and 1800 →
    MIG-0016, 1797 → MIG-0017, 1646 → MIG-0019, 1604 → MIG-0020. Source-pass quotes came
    through WebFetch's summariser and must be checked against the page before they enter a
    dossier. To do: review the 103 proposals; promote the new candidates (strongest: AIID
    7, 1263, 28, 528, 794, 1633, 1794, 1796, 1766).
    **Done 2026-11-23**, except 1556: the 103 were reviewed (35 in, 61 out, 7 unclear), the
    other five duplicates were linked (item 25), and 26 new dossiers were promoted. 1263 was
    not promoted. 1054 turned out to be a sixth duplicate, of MIG-0003.

64. **Review is two spreadsheets, 2026-11-18.** `mvp/review/1_decide_scope.xlsx` (scope:
    in, out, unclear) and `2_promote.xlsx` (yes, no), with the logs `scope_decisions.csv`
    and `promote_decisions.csv`. Left open:
    - *Settled 2026-11-18:* *Name the pattern* takes every record in scope once Gate 1 is
      complete: the rules' `in_scope` unless a person decided `out` or `unclear`, a scope
      decision `in` on sheet 1 (promoted or not), and dossiers with `multi_agent: true`, ours.
    - A scope decision `in` that a dossier later contradicts with `multi_agent: false` only
      warns in `check`; the dossier is the later judgement. `out` against `multi_agent: true`
      fails.
    - A promote `no` is final: the record does not return to sheet 2. To reverse it, delete
      its row from `promote_decisions.csv`. There is no sheet column for that.
    - Reversing a scope decision (a record decided `out` then thought `in`) is the same:
      delete or append a row by hand in `scope_decisions.csv`; sheet 1 does not list a
      decided record.
    - The sheets are generated and gitignored. `review` and `derive` read a sheet before
      they replace it, so filled rows are kept; an invalid row is reported by record_key and
      comes back blank, so what was typed in it is lost. A sheet that cannot be read is left
      in place and not rewritten.

65. **TODO: simplify the pipeline around multi-agent attacks, 2026-11-23.** The project is
    interested only in multi-agent attacks, but attack-ness is not a field of its own: the
    rules infer it from `multiplicity_role` (anything but `not_applicable` or empty,
    `derive.is_security`), and the prompt uses `not_applicable` both for a non-attack and for
    an attack where multiplicity plays no part, so an attack can be read as a non-attack.
    The chain multiplicity_role → presumption → counterfactual → rules_say is also hard to
    follow on the sheet. Decide what the scope question should be for attacks only, and
    cut the prompt fields and rules that do not serve it. Sheet 1 now shows every model
    answer, the rules' intermediate steps and a `Fields` tab with the lineage, as a stopgap.
    - **Consider a direct model scope suggestion.** Add a final `extract_gate` field,
      `scope_suggestion` (in / out / unclear) with a one-line reason and a quote, and show
      it on sheet 1 beside `rules_say`. It stays a suggestion: only a human verdict sets
      scope. Before trusting it, measure it against the 103 human scope decisions of
      2026-11-23 in `mvp/review/scope_decisions.csv`. Watch for anchoring: the gold review
      hides prior labels for that reason (item 28), so the sheet may need to do the same.
    - **Simplify the data flow map, after the first full run cycle.** In
      `mvp/out/pipeline_patch.html` the step names do not match the sheets and the CLI
      ("Decide scope" is `review` on the CLI; "Human review" is the promote sheet), the
      same records appear in several boxes as if they were separate counts, and rule
      outcomes and human decisions are mixed (records out by the rules gather in one box,
      while a person's `out` stops at Decide scope). Use one name per step across sheet,
      CLI and map, and show human decisions apart from rule outcomes.
    - **Find duplicates by code before sheet 2.** On 2026-11-23 six records decided `in`
      were duplicates of existing dossiers, found by hand. `review` could flag a record whose
      title or date matches a dossier's, or that `OPEN.md` names against a dossier.
    - **Rename `status = in_scope` on the sheet.** It reads like a decision but is only the
      rules' settled suggestion; `ask = yes` on an `in_scope` row looks contradictory.

66. **Verify the 26 Claude-written dossiers, 2026-11-23.** At the curator's request Claude
    filled the 26 dossiers promoted on 2026-11-23 from the pipeline's readings (rule in
    `CLAUDE.md`: Claude-written dossiers). All are `unverified`; their failure modes are
    `classifier:` labels, not `ours`; 12 rest on a secondary or partial reading. Each needs a
    person to read the primary source, confirm or correct the failure mode, instances and
    evidence type, and set `verification`. Readings to re-check: aiid:1734 and aiid:1799
    were re-read as exposures, not attacks, so the attack presumption no longer applies to
    them; aiid:1794's quoted I29 is low and was not adopted. Also open from this round: a
    new instance for cross-agent collaboration through public artefacts or shared boards
    (aiid:1633, 1766, 1781 fit none of the 36).

## Layer 2. Detection
17. Write the one-page coding protocol: the definition of coverage and the 0–3 validity weight.
18. Build `data/evals.csv` (technique, what it measures, method, access, validity note). Seed it from METR, Apollo Research, UK AISI, GovSim, Melting Pot, agent-security benchmarks and steganography evals.

## Layer 3. Mapping
19. Pilot `data/coverage.csv` (risk × technique, coverage, validity) on a subset of risks.
20. Dashboard skeleton: a risk × technique matrix showing grounding, coverage and validity, plus a gap view.

## Watch
21. AI Village Swarm Dynamics Hackathon (Sep 2026) for new synthetic evidence.
22. New Cooperative AI Foundation outputs and forward citations of Hammond et al. 2025.
