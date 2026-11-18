# Glossary

Every project term in one or two plain sentences, alphabetical. The full walk-through is
[how_it_works.md](how_it_works.md); the authority on definitions is
[definitions.md](definitions.md), and on the labelling rules `mvp/pipeline/derive.py`.

**Agent.** Anything whose behaviour is best explained by giving it a goal: a chatbot, an
autonomous assistant, a scripted bot. A model called once to label a string is not one.
Agents are counted, not systems: one product or operator can hold several.

**AIID.** The AI Incident Database, the project's baseline source of real-world incidents,
built from news reports. Fetched into `mvp/raw/aiid/`.

**Arm.** The name, until 2026-11-16, of one of the three nets of the prefilter: `label`,
`keyword` and `unasked` (`unclassified` before that). Replaced on 2026-11-17 by `basis` and
`flags`; see **Basis**, **Flags** and `input_layer.md`. Also **Unasked**.

**Attack presumption.** The rule that a security record with `multiplicity_role: unreported`
is in scope, because being many is often itself the attack. Since 2026-11-16 it fires only
if the record does not show fewer than two AI agents and the model did not answer `could`.

**Baseline source.** The source the pipeline fetches in full on every update. Only AIID.

**Basis.** The queue row's field saying why a record is queued, one per row: `recent` (an AIID
record dated 2024-01-01 or later), `frozen` (on the frozen list) or `manual` (added by hand).

**Call 1.** The first model call, prompt `extract_gate.v3`: it extracts the gate facts from
a record and its context row. It does not decide labels.

**Call 2.** The second model call, prompt `assign_instances.v2`: it assigns instances, with
a quote for each, to records in scope.

**Candidate.** A record worth a look. An outside label or a model may mark a candidate; only
a person puts it in scope.

**Ceiling.** The precision of the index's earlier hand-curation against the gold set's
re-review: 82.6% (19 of 23). A realistic target for any screen.

**Check.** `run.py check`: validates every dossier and data row. It must exit 0 before a
commit.

**Classification row.** An outside team's answer sheet for one AIID incident, under one
namespace. An incident can have none or many.

**Content hash.** A hash of a record's substance (title, text, date, url, meta, labels).
A re-fetch appends a new record version only when it changes.

**Context row.** One reading of a source, in `mvp/context/<source>.jsonl`: seven facts, each
with a status and a quote, plus the read depth reached. The newest row per record wins.

**Counterfactual.** Call 1's field `single_agent_counterfactual`: could one capable agent,
alone, have produced this same outcome? `could`, `could_not` or `unclear`. The heart of
Gate 1.

**CSETv1.** A namespace of AIID classifications by Georgetown's CSET. Its field "Multiple AI
Interaction" is the only AIID field that asks the multi-agent question; it stopped in
mid-2024.

**Curator.** The person who keeps the index. A curator's hand write-up is a manual incident,
in scope on their word; its read depth is `curator`.

**Decide scope.** The map's box, and the sheet behind it, `mvp/review/1_decide_scope.xlsx`,
where a person says `in`, `out` or `unclear` for each derived record. The rules only
suggest (`rules_say`); a record is in scope only by a person's decision, which goes into the
scope decision log. `in` goes on to Human review; `out` and `unclear` end there.

**Derive.** `run.py derive`: applies `derive.py` to the newest call-1 proposal of every
record and writes `mvp/state/verdicts.jsonl`.

**Discovery source.** Any source other than AIID, searched for incidents AIID lacks. The
discover step is a placeholder, not built yet.

**Dossier.** The curated record of one incident, `mvp/incidents/<ID>.md`, written by a
person: frontmatter plus seven sections. Dossiers exist for in, out and unclear verdicts.

**Evidence type.** What kind of evidence an incident is: `real_world`, `synthetic`, `lab` or
`theoretical`. Derived by rule from setting, stakes and who controlled the environment.

**External label.** A label from someone else's rater, such as CSETv1 or the Navigator. Kept
in `external_labels`, never merged with ours, never enough to put an incident in scope.

**Failure mode.** One of Hammond's three ways agent interaction goes wrong: FM1
Miscoordination, FM2 Conflict, FM3 Collusion. Assigned only by the Gate 2 tree; an in-scope
record may have none.

**Flag rule.** A queued record whose `flags` is not empty (`label` or `keyword`) is *flagged*, and may not be
dismissed as single-agent on its record text alone; a reading of depth `secondary` or
better must confirm it.

**Flags.** The queue row's field saying why a queued record is flagged: `label` (an outside
label calls it multi-agent), `keyword` (a keyword matches its title or text), both separated by
`;`, or empty. A flag never queues a record by itself.

**Frozen list.** `mvp/registry/frozen_pre2024.csv`: the 34 pre-2024 records that were queued
when the prefilter was simplified on 2026-11-17. Kept by hand from then on. A record on it is
queued with basis `frozen`.

**Gate 1.** Is the record in scope: does the harm come from interaction between two or more
AI agents, such that one capable agent could not have produced it?

**Gate 2.** Which failure mode an in-scope record shows: FM3 if cooperation occurred and was
unexpected; otherwise FM1 for identical objectives, FM2 for mixed, none for opposing.

**Gold set.** `mvp/gold/multiagent_gold.csv`: 58 rows judged by a person from primary
sources (22 in, 33 out, 3 unclear), used to measure the classifier.

**Hammond et al. (2025).** *Multi-Agent Risks from Advanced AI*, the source of the failure
modes, risk factors and instances. `resources/multi-agent-risks.pdf`.

**Index.** `mvp/out/incident_index.csv`, one row per dossier, generated by `run.py index`.

**Instance.** A named pattern from Hammond's Table 1, such as I28 Swarm Attacks; 36 in
`mvp/taxonomy/instances.csv`. Descriptive only: it never sets the failure mode.

**Instances-due.** `run.py instances-due`: lists in-scope records, by rule or by a person,
that have no instance proposal yet. Writes `mvp/state/instances_due.jsonl`.

**Interaction.** One agent acting on, messaging, answering or using the output of another.
Agents merely present in the same place do not count.

**Manual incident.** An incident the curator wrote up by hand and added with
`update --manual DIR`. In scope on the curator's word; never `verified` on the write-up alone.

**Multi-agent risk / setup.** A risk is harm that arises from agents interacting and that one
capable agent could not have produced. A setup is many agents running where one agent's worth
of capability did the harm; it stays out.

**Multiplicity role.** Call 1's field `multiplicity_role`, set on security records only:
`load_bearing` (the number or mix did the work), `incidental` (one agent's capability did),
`unreported` (the source does not say). Otherwise `not_applicable`.

**Namespace.** The name of one taxonomy whose classification rows AIID carries: `CSETv1`,
its annotator variants, `CSETv0`, `GMF`, `MIT`.

**Navigator.** The MIT AI Risk Navigator's "Multi-agent" facet, copied by hand on 2026-11-09
into `mvp/registry/labels/navigator_multiagent.tsv` (28 AIID incidents). An external label.

**not_stated / unread.** Two statuses of a fact in a context row. `not_stated`: the source was
read and is silent; the answer becomes `unclear`. `unread`: nobody looked; nothing may be
derived from it.

**Prefilter.** `run.py prefilter`: queues every recent AIID record, every record on the
frozen list and every manual record, and flags the queued records an outside label or a
keyword calls multi-agent.

**Promote.** `run.py promote <record_key>`: scaffolds a dossier from a record for a person to
fill in. Refuses a `not_ready` record unless given `--force`. The review step does the same
for each `yes` on the promote sheet.

**Promote sheet.** `mvp/review/2_promote.xlsx`: the records a person decided `in` that have
no dossier yet. The person fills `promote` with `yes` (the next run scaffolds the dossier)
or `no` (logged in `mvp/review/promote_decisions.csv`; the record does not come back). It is
the map's Human review box.

**Proposal.** A row of model output in `mvp/proposals/`. Never authoritative, and it holds no
derived label.

**Queue.** `mvp/state/queue.jsonl`: the candidates the prefilter queued. 1,133 on 2026-11-18.

**raw_ref.** The pointer in a record to the raw row it was built from: file, id field, id and
fetch date.

**Read depth.** How far a source was read: `unreadable`, `record`, `secondary`, `curator`,
`primary_partial`, `primary_full`, worst to best.

**Readiness.** `run.py readiness`: per record and per decision, whether enough has been read
to classify: `ready`, `provisional`, `not_ready` or `not_needed`.

**Record.** What one source said about one incident when fetched, normalised, in
`mvp/records/<source>.jsonl`. Machine-written and append-only.

**Record pass / source pass.** The two reading passes. The record pass reads only the record
text; the source pass fetches the AIID page and the primary source.

**record_key.** A record's one-string identity, `"<source_id>:<source_record_id>"`, such as
`aiid:1668`. Every file row carries it, and `promote` takes it.

**Review item.** A record whose derived verdict has `status: review`: low confidence, or a
deciding fact unclear. Its labels sit under `labels_if_confirmed` for a person to confirm.

**Risk factor.** One of Hammond's seven properties of a setting that make bad outcomes more
likely, RF1 to RF7, such as RF7 Multi-Agent Security.

**Rules version.** The date stamped on each derived verdict, saying which version of
`derive.py` made it. Currently `2026-11-16`.

**Scope decision log.** `mvp/review/scope_decisions.csv`: a person's scope decisions, one row
per decision (`record_key, decision, reason, decided_on, sheet_generated_on`), append-only,
the newest row per record winning. Written only when `run.py review` reads a filled sheet.
`check` validates it.

**Security record.** A record about an attack, intrusion or abuse campaign: call 1 set
`multiplicity_role` to anything but `not_applicable`.

**Skill.** `/classify-incidents`, run in Claude Code. It does the reading and both model
calls, and writes only to `context/` and `proposals/`.

**Test run.** `run.py testrun`: the real steps on made-up incidents in a temporary folder.
Never touches the real tree.

**Unasked.** The name, until 2026-11-16, of the prefilter arm that queued a recent AIID record
no taxonomy had asked the multi-agent question. Retired on 2026-11-17: every AIID record dated
2024 or later is now queued with basis `recent`.

**Verdict.** Two senses; keep them apart. A *derived verdict* is a row in
`mvp/state/verdicts.jsonl`, made by rule from model facts. A *human verdict* is a person's
decision recorded in a dossier; only it puts an incident in scope.

**Verification.** A dossier field: `verified`, `partially_verified` or `unverified`.
`verified` needs the primary source read in full.

**Work order.** A note per source, in `mvp/state/work_orders.md`, saying what a person must
search and paste back for a source no script can reach.
