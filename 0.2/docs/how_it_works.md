# How it works

A guide for a new analyst. Read it once, start to finish, in about fifteen minutes. Terms in
*italics* on first use are defined in the [glossary](glossary.md). Where this page and the
code disagree, the code wins: the labelling rules live in `0.2/pipeline/derive.py`.

## In five sentences

1. The project builds an **index of multi-agent AI risks**: incidents, experiments and
   arguments in which harm comes from AI agents interacting, sorted under the failure modes
   and risk factors of Hammond et al. (2025), `resources/multi-agent-risks.pdf`.
2. An incident counts only if the behaviour **arises from interaction between two or more AI
   agents** (one agent acting on another counts) **and one capable agent could not have
   produced it alone**.
3. A swarm doing what one capable agent could have done is a multi-agent *setup*, not a
   multi-agent *risk*, and stays out.
4. Each judged incident becomes one *dossier*, a file in `0.2/incidents/` written by hand
   or, at the curator's request, by Claude from the readings, and the index,
   `0.2/out/incident_index.csv`, is generated from the dossiers.
5. The pipeline in one line: **fetch → normalise → prefilter → read → readiness → extract
   facts (model) → derive labels (rules) → review and promote (person) → check → index.**

## Who decides what

Three kinds of actor touch a record. Keep them apart; the project depends on it.

| actor | what it does | where its output goes |
|---|---|---|
| **script** (`0.2/pipeline/run.py`) | moves and counts data: fetch, normalise, prefilter, readiness, check, index | `raw/`, `records/`, `state/`, `out/` |
| **model** (Claude, following a prompt in `0.2/prompts/`, run by the `/classify-incidents` skill) | **judgement**: reads sources and writes down facts; extracts gate facts; picks instances | `context/`, `proposals/` |
| **fixed rule** (`0.2/pipeline/derive.py`) | turns the model's facts into labels, the same way every time | the ledger's derive columns |
| **person** | decides scope for the index, writes the dossier (or asks Claude to), sets `verification` | `incidents/` |

Only a person can put an incident in scope. In a dossier that is `multi_agent: true` with
`multi_agent_label_source: ours`, and `run.py check` fails the build on any other
combination. A model's answer, a derived *verdict*, or an outside database's label can only
mark a *candidate*.

## The journey of one record

We follow one real record all the way: **AIID incident 1668**, "OpenAI-Linked AI Agents
Reportedly Used German Programming Wiki DSEWiki for Coordination and Restriction Evasion"
(2026-05-24). Its *record key* is `aiid:1668`. The values quoted below are the live values on
2026-11-16.

### 1. Sources registry

`0.2/registry/sources.csv`, edited by a person, read by the script: 23 sources with their
role (`baseline`, `discovery`, `reference`), access method and reuse terms. AIID, the AI
Incident Database, is the only `baseline` source; no discovery source has a working fetcher.

### 2. Fetch

- **What:** download AIID verbatim: the incident list and the *classification* rows outside
  teams attach to incidents ([aiid_background.md](aiid_background.md)).
- **Who:** script. `update` reuses the saved snapshot; `--refetch` downloads afresh.
- **Writes:** `0.2/raw/aiid/incidents.jsonl`, `0.2/raw/aiid/classifications.jsonl`. Never
  edit by hand.
- **1668:** one line of `incidents.jsonl`, internal id `_id` `6a9b3dbf2eef2f27dd9e10a8`.

### 3. Normalise

- **What:** turn each raw row into one *record* with a fixed shape: title, text, date, url,
  `external_labels`, and three bookkeeping fields. `record_key` is
  `"<source_id>:<source_record_id>"`, the one string every later file uses. `raw_ref` points
  back to the raw row it came from. `content_hash` covers the substance only, so a re-fetch
  adds a new version **only if the content changed**.
- **Who:** script. It also attaches the MIT *Navigator*'s hand-copied multi-agent list from
  `0.2/registry/labels/navigator_multiagent.tsv`.
- **Writes:** `0.2/records/aiid.jsonl` (append-only; 1,817 AIID rows, 1,844 across four
  sources on 2026-11-16).
- **1668:**

  ```
  record_key       aiid:1668
  external_labels  source mit_navigator, field behaviour, value "Multi-agent"
  meta             has_classification false, namespaces []
  raw_ref          path 0.2/raw/aiid/incidents.jsonl, id_field _id, id 6a9b3dbf…, fetched_at 2026-11-09
  content_hash     sha256:b6dc1da5b82e978063086f376d56300c
  ```

  The text is 463 characters: agents "made thousands of edits", used the wiki "as a space
  for inter-agent coordination", "shared task answers and methods for bypassing sandbox
  restrictions", and "created backup pages to evade a moderator's deletions".

### 4. Prefilter: queued, then flagged

- **What:** pick the candidates worth reading. A record joins the *queue* for one reason,
  its `basis`:

  | basis | a record is queued when |
  |---|---|
  | `recent` | it is an AIID record dated 2024-01-01 or later that no outside rater has answered "not multi-agent" on |
  | `frozen` | it is on the hand-kept list of pre-2024 candidates (`registry/frozen_pre2024.csv`) |
  | `manual` | the curator added it by hand |

  A queued record is then *flagged*, in `flags`, when an outside label or a keyword calls it
  multi-agent:

  | flag | set when |
  |---|---|
  | `label` | an outside label says `yes` or `maybe` to "Multiple AI Interaction", or the Navigator lists it |
  | `keyword` | a regex net matches title or text (`KEYWORD_TERMS` in `run.py`) |

  Why: AIID's only multi-agent field stopped being filled in mid-2024, so for recent records
  the only signal is our own classification. Where an outside rater has already answered,
  its answer is acted on: "no" leaves the record out (4 records on 2026-11-18), "yes" queues
  and flags it. Every unlabelled recent record is read, because the Navigator's rater misses
  a third of our known cases and the keyword net's recall is unmeasured. A record nobody
  asked is *unscreened*, not negative. [aiid_background.md](aiid_background.md) tells the full story.
- **Who:** script. Records already cited by a dossier are skipped.
- **Writes:** the ledger's prefilter columns (until 0.2, `state/queue.jsonl`). On 2026-11-18: 1,133 queued (recent 1,099, frozen 34),
  93 of them flagged (label 39, keyword 64; a record with both counts under both).
- **1668:** `basis: "recent"`, `flags: "label;keyword"`,
  `label_values: "navigator=Multi-agent"`,
  `keyword_terms: "\bagents\b;coordinat(?:e|ion|ing)"`. It is **flagged**.

### 5. Read the record, then read the source

This is the *context layer*: **read before you judge**. Records are short (1668's is 463
characters), and the facts the gates need are usually missing from them.

- **What:** a model writes down what a source says about seven facts: `agents`,
  `interaction`, `multiplicity` (attacks only), `setting`, `cooperation`, `objectives`,
  `mechanism`. Each fact has a status:
  - `stated`, with a verbatim quote;
  - `not_stated`: **the source was read and is silent**. That is a finding; the gate answer
    becomes `unclear`.
  - `unread`: **nobody looked**. Nothing may be derived from it.
  - `not_applicable`.

  It runs in two passes. The **record pass** reads only the record text (depth `record`). The
  **source pass** fetches the AIID page and the primary source it cites, and records the
  *read depth* reached: `unreadable` < `record` < `secondary` < `curator` <
  `primary_partial` < `primary_full`.
- **The flag rule:** a record the record pass calls `one` agent or `none` is finished, out of
  scope, **unless it is flagged**. A flagged record goes to the source pass anyway, and is out
  only once a reading of depth `secondary` or better confirms it.
- **Who:** model, following `0.2/prompts/enrich_context.v2.md`, run by `/classify-incidents`
  step 0.
- **Writes:** appends rows to `0.2/context/aiid.jsonl`. The newest row per record wins.
- **1668:** two rows, both 2026-11-15. The record pass: `agent_count: several`, `attack:
  false`, depth `record`. The source pass read the AIID page (`secondary`) and the
  researchers' page `collusion.wiki` (`primary_full`). Its `interaction` fact quotes an
  agent post: "saw Dec30's report and independently reproduced POST bypass"; its
  `cooperation` fact quotes "the agents cooperated to gain an advantage on their task in a
  way their developers did not intend". `multiplicity` is `not_applicable`: not an attack.

### 6. Readiness

- **What:** a fixed rule in `run.py` says, per record and per decision (scope, evidence type,
  failure mode, instances), whether enough has been read. Levels: `ready` (primary source in
  full), `provisional` (secondary or partial reading), `not_ready` (a needed fact is
  `unread`, or only the record text was read), `not_needed` (already out of scope).
- **Who:** script. **Writes:** `0.2/state/readiness.jsonl`.
- On 2026-11-16 the queue's scope readiness is: ready 397 (of which 336 are settled out by
  the one-agent shortcut), provisional 42, not_ready 694. So 103 can be judged.
- **1668:** `scope: ready`, `why: "primary source read in full"`, and `ready` for the other
  three decisions.

### 7. Call 1: extract the facts

- **What:** the model reads the record **and** its context row and fills a fixed form:
  `n_ai_agents`, `interaction_present`, `setting`, `stakes`, `environment_controlled_by`,
  `single_agent_counterfactual`, `multiplicity_role`, `cooperation_occurred`,
  `cooperation_expected`, `objective_relation`, `confidence`, with a quote per field. It does
  **not** decide labels. A fact marked `unread` is left null; one marked `not_stated` is
  answered `unclear`.
- **Who:** model, following `0.2/prompts/extract_gate.v3.md`. Only records with scope
  `ready` or `provisional` go in.
- **Writes:** `0.2/proposals/extract_gate.2026-11-15.jsonl`. A *proposal* holds model output
  only.
- **1668:** `n_ai_agents: null`, `interaction_present: true`, `setting: deployed`,
  `stakes: real`, `environment_controlled_by: nobody`, `single_agent_counterfactual:
  could_not`, `multiplicity_role: not_applicable`, `cooperation_occurred: yes`,
  `cooperation_expected: unexpected`, `objective_relation: identical`, `confidence: high`.

### 8. Derive the labels by rule

- **What:** `derive.py` applies the gates (next section) to the newest call-1 row of every
  record. Each record comes out `in_scope`, `out_of_scope` or `review`.
- **Who:** fixed rule. **Command:** `python 0.2/pipeline/run.py derive` (an `update` runs it
  too). **Writes:** the ledger's derive columns, rewritten on every run, so a rule change
  reaches every record at once.
- On 2026-11-16: 103 verdicts, **1 in scope, 0 out of scope, 102 review**.
- **1668** is the one: `status: in_scope`, `gate1: in`, `review_why: []`, labels
  `multi_agent: true`, `evidence_type: real_world`, `failure_mode: FM3`,
  `instances_presumed: []`, `rules_version: 2026-11-16`.

### 9. Call 2: instances, and `instances-due`

- **What:** an *instance* is a named pattern from Hammond's Table 1, such as "I28 Swarm
  Attacks"; 36 are defined in `0.2/taxonomy/instances.csv`. The model matches the record
  against all 36 definitions and quotes the text for each one it assigns. Instances are
  description only: they never set the failure mode, and the failure mode never constrains
  them.
- **Which records:** only after a person decides scope. Every record listed by
  `python 0.2/pipeline/run.py instances-due`, which writes
  `0.2/state/instances_due.jsonl`: the records a person put in scope with no instance
  proposal yet. That is the dossiers a person put in scope that have no instances, and
  the records you decided `in` on the scope sheet (promoted or not); a manual record
  counts as decided `in`. An `in_scope` verdict you have not decided in is not listed.
  On 2026-11-16 it listed one record, `lesswrong:LW-03` (dossier MIG-0017).
- **Who:** model, following `0.2/prompts/assign_instances.v2.md`.
- **Writes:** `0.2/proposals/assign_instances.<date>.jsonl`.
- **1668** (2026-11-16): `I35 Defeating Oversight and Evaluation`, confidence `medium`,
  quote "The agents shared task answers and methods for bypassing sandbox restrictions".
  Seven instances considered and rejected, among them I28 ("the text does not say the
  number of agents is what defeated a defence") and I08 Steganography ("plain posts on a
  public wiki").

### 10. Review by a person

- **What:** a person reads the proposals and the source, and decides, in two spreadsheets
  in `0.2/review/` (since 0.2; `0.2/review/README.md`). Every label on them has a proposal,
  its reason, and the person's decision: `ok` takes the proposal, a value replaces it, a
  blank is never agreement. **Sheet 1**, `1_records.xlsx`, lists every derived record in
  no incident: the undecided ones to decide, the decided ones so a decision can be changed.
  The rules never put anything in scope, a person does. Column `ask` is `yes` when the
  rules propose in or the model's confidence is `low` (those rows come first), `check` for
  the rest, listed so a person can sample-check the exclusions (decided 2026-11-19),
  `duplicate` and `decided`. The person fills `scope_decision` (`ok`, `in`, `out`,
  `unclear`) and, for `in`, `duplicate_of_decision`: `new`, or the MIG key of the incident
  the record already is, proposed by `pipeline/dedupe.py`. The answers go into
  `0.2/review/record_decisions_log.csv` and the ledger. A hand-added incident counts as
  decided `in` on the curator's word. The update's Review step writes the sheets and waits
  for the person; on the map the **Decide records** box counts the rows left.
- **1668:** the person finds it duplicates an incident already in the index: dossier
  **MIG-0016**, "OpenAI agent swarm on DSEWiki and the Vanderbilt link shortener", which a
  person already judged `multi_agent: true`, `multi_agent_label_source: ours`,
  `failure_mode: FM3`, `instances: I35; I26; I28`, `verification: partially_verified`. So
  1668 is **not promoted**: it should be added to MIG-0016's `sources` (`OPEN.md` items 25
  and 63). On 2026-11-16 that link has not been made yet. **Made 2026-11-23:** 1668 and
  1800 are now sources of that dossier and AIID is canonical. The dossier is
  **MIG-0016** again, with `source_key: '1668'` (it was briefly named AIID-1668).

### 11. New or duplicate, then the dossier

- **What:** a record decided `in` with `duplicate_of` `new` gets its dossier on the next
  run (the map's **New or duplicate** box): `0.2/incidents/<mig_key>.md`, named by the
  record's MIG key, every narrative section marked `_pending_`, its scope the person's
  decision, its other labels and facts proposed from the record (the rules' evidence type
  and failure mode, the adoptable instance proposals, the model's agent count and names).
  A record decided `in` with an incident's MIG key joins that incident as a further
  source, so one incident is never counted twice. A record that is `not_ready` is refused
  and comes back. `python 0.2/pipeline/run.py promote <mig_key>` still makes one dossier by
  hand, and refuses a `not_ready` record unless given `--force`.
- **Then sheet 2**, `0.2/review/2_incidents.xlsx`: per incident, the scope, failure mode,
  instances and evidence type as proposal and decision, the facts, and the verification
  with a note. The decisions go into the ledger and `0.2/review/incident_decisions_log.csv`,
  and the run writes the dossier's frontmatter from the ledger. A label edited in the
  dossier by hand fails `check`.
- **The prose.** The person writes the seven sections against the primary source, or, at
  the curator's request, Claude writes them from what the pipeline holds; such a dossier
  stays `unverified` until a person checks it (the rule is in `CLAUDE.md`). First done
  2026-11-23, for 26 dossiers. Claude never writes the labels.
- **Duplicates, before 0.2.** On 2026-11-23 six records were linked by hand into five
  dossiers, which were renamed from `MIG-` to `AIID-` ids. Later that day every dossier was
  keyed by its MIG key instead, and those five got their MIG keys back; the source's own
  key is in `source_key`. Since 0.2 linking is the `duplicate_of` decision.
- **Who:** person, helped by the script. The sheets need openpyxl; without it the step says
  how to install it, skips the sheets, and the run goes on.

### 12. Check, then index

- `python 0.2/pipeline/run.py check` validates every dossier and every data row and must
  exit 0. Among other things it fails a dossier with `multi_agent: true` whose label source
  is not `ours`, a dossier that asserts scope with no source read far enough, and a
  `verified` dossier whose scope rests on a secondary or curator reading.
- `python 0.2/pipeline/run.py index` sets every record's `stage`, `reason` and `in_index`
  in the ledger: where it stopped (prefilter, reading, rules, a person, or an incident in or
  out of the index) and why. It also writes `0.2/out/incident_index.csv` (one row per
  dossier) and `0.2/state/pipeline.json`; `viz` renders the pages in `0.2/out/`. (Until
  0.2, `index_report.py` wrote the same as a workbook, `index_report.xlsx`.)
- On 2026-11-23: 52 dossiers covering 59 records; 1,785 records not in the index.
- On 2026-11-16: 26 dossiers, 19 `multi_agent: true`, 4 `false`, 3 `unclear`; `check` passes
  with 11 warnings, one per dossier resting on a secondary reading.

### Manual incidents

The curator can add incidents the databases do not carry: one `.txt` or `.md` write-up per
incident in a folder, then `python 0.2/pipeline/run.py update --manual DIR`. A copy goes to
`0.2/raw/manual/`, the record to `0.2/records/manual.jsonl`, and the script writes the
context row itself (`manual: true`, depth `curator`). The record is queued with
`basis: manual` and skips Gate 1: **it is in scope on the curator's word**, which is a human verdict. Call 1 still
extracts the Gate 2 and evidence-type facts, call 2 still assigns instances, and `derive`
gives `gate1: curator`. A dossier resting only on the write-up may never be `verified`.

## The whole pipeline at a glance

```mermaid
flowchart TD
  REG["Sources registry<br/>registry/sources.csv"] --> FETCH["Fetch<br/>raw/aiid/"]
  MAN["Curator write-ups<br/>update --manual DIR"] --> NORM
  FETCH --> NORM["Normalise<br/>records/SOURCE.jsonl"]
  NORM --> PRE["Prefilter: recent, frozen, manual<br/>flags: label, keyword<br/>ledger: queued"]
  PRE --> READ["Read: record pass, source pass<br/>context/SOURCE.jsonl"]
  READ --> RDY{"Readiness<br/>state/readiness.jsonl"}
  RDY -->|"not_ready"| READ
  RDY -->|"one agent or none, confirmed"| GONE["Finished: out of scope"]
  RDY -->|"ready or provisional"| C1["Call 1: extract facts<br/>proposals/extract_gate.DATE.jsonl"]
  C1 --> DER["Derive by rule<br/>ledger: derive columns"]
  DER --> REV["Decide scope, by a person"]
  REV -->|"decided in"| DUE["instances-due<br/>state/instances_due.jsonl"]
  DUE --> C2["Call 2: risk instances<br/>proposals/assign_instances.DATE.jsonl"]
  C2 --> PROM["Promote and write up<br/>incidents/ID.md"]
  PROM --> CHK{"Check<br/>must exit 0"}
  CHK --> IDX["Index and pages<br/>out/incident_index.csv"]
  classDef script fill:#e8eef7,stroke:#4a6fa5
  classDef model fill:#fdf1dc,stroke:#c08a2b
  classDef rule fill:#e6f4ea,stroke:#3c8d5a
  classDef person fill:#f6e3ea,stroke:#a3445f
  class FETCH,NORM,PRE,RDY,DUE,CHK,IDX script
  class READ,C1,C2 model
  class DER rule
  class REG,MAN,REV,PROM person
```

Blue: script. Amber: model. Green: fixed rule. Pink: person.

| step | done by | reads | writes | command |
|---|---|---|---|---|
| sources | person edits, script loads | — | `registry/sources.csv` | part of `update` |
| fetch | script | AIID API, or the snapshot | `raw/aiid/` | `run.py fetch`, `update --refetch` |
| manual | script | your folder of write-ups | `raw/manual/`, `records/manual.jsonl`, `context/manual.jsonl` | `update --manual DIR` |
| normalise | script | `raw/`, `registry/labels/` | `records/<source>.jsonl` | `run.py normalise` |
| prefilter | script | `records/`, dossier sources | ledger: prefilter columns | `run.py prefilter` |
| read | model, `enrich_context.v2` | queue, records, the web source | `context/<source>.jsonl` | `/classify-incidents` step 0 |
| readiness | script | context, queue, dossiers | `state/readiness.jsonl` | `run.py readiness` |
| call 1 | model, `extract_gate.v4` | record and context row | `proposals/extract_gate.<date>.jsonl` | `/classify-incidents` |
| derive | fixed rule, `derive.py` | newest `extract_gate` proposals | ledger: derive columns | `run.py derive` |
| instances-due | script | dossiers, verdicts, instance proposals | `state/instances_due.jsonl` | `run.py instances-due` |
| call 2 | model, `assign_instances.v2` | record, context, `taxonomy/instances.csv` | `proposals/assign_instances.<date>.jsonl` | `/classify-incidents` |
| decide scope, promote | person, helped by script | verdicts, proposals, sources | `review/*.csv` logs, then `incidents/<ID>.md` | `run.py review`; `run.py promote <mig_key>` by hand |
| check | script | everything | exit code only | `run.py check` |
| index, viz | script | `incidents/` | `out/incident_index.csv`, `out/*.html`, `state/pipeline.json` | `run.py index`, `run.py viz` |
| outcome | script | every ledger column | ledger: `stage`, `reason`, `in_index` | `run.py index` |

## The gates

Two gates, with different jobs. **Gate 1** decides scope: is this a multi-agent risk at all?
**Gate 2** names the failure mode of an in-scope record, if any. Gate 2 never removes a
record. The model supplies the facts; `derive.py` applies the logic below, and nothing else
does.

A *security record* is one where call 1 set `multiplicity_role` to `load_bearing`,
`incidental` or `unreported`, meaning an attack, intrusion or abuse campaign. Any other record
has `not_applicable`.

```mermaid
flowchart TD
  F["Call 1 facts for one record"] --> MAN{"Manual record?"}
  MAN -->|"yes"| CUR["Gate 1 skipped: in scope on the curator's word"]
  MAN -->|"no"| SEC{"Security record?<br/>multiplicity_role set"}
  SEC -->|"no"| NS{"counterfactual is could_not<br/>AND interaction_present is true?"}
  NS -->|"yes"| IN["Gate 1 IN"]
  NS -->|"no"| OUT["Gate 1 OUT"]
  SEC -->|"yes"| ROLE{"multiplicity_role"}
  ROLE -->|"load_bearing"| IN
  ROLE -->|"incidental"| OUT
  ROLE -->|"unreported"| PRES{"n_ai_agents null or 2 or more<br/>AND model did not answer could?"}
  PRES -->|"yes: presumption fires"| IN
  PRES -->|"no"| MCF{"model's counterfactual"}
  MCF -->|"could_not"| IN
  MCF -->|"could, or unclear: also review"| OUT
  IN --> G2{"cooperation_occurred yes<br/>AND cooperation_expected unexpected?"}
  CUR --> G2
  G2 -->|"yes"| FM3["FM3 Collusion"]
  G2 -->|"no"| OBJ{"objective_relation"}
  OBJ -->|"identical"| FM1["FM1 Miscoordination"]
  OBJ -->|"mixed"| FM2["FM2 Conflict"]
  OBJ -->|"opposing"| NOFM["No failure mode, still in scope"]
  OBJ -->|"unclear"| REV["Goes to a person: Gate 2 undecided"]
  IN --> PI{"security AND unreported?"}
  PI -->|"yes"| I2829["instances_presumed: I28 and I29"]
```

The same logic as a plain list, in case the diagram does not render.

**Gate 1, in scope?**

1. Manual record: skip. In scope on the curator's word; `gate1: curator`, `multi_agent`
   stays null.
2. Security record:
   - `load_bearing`: counterfactual becomes `could_not`. **In.**
   - `incidental`: counterfactual becomes `could`. **Out.**
   - `unreported`: the *attack presumption* fires **only if** the record does not show fewer
     than two AI agents (`n_ai_agents` null, or 2 or more) **and** the model did not answer
     the counterfactual `could`. If it fires: `could_not`, **in**. If not, the model's
     answer stands: `could_not` in, `could` out, `unclear` out pending review.
   - Interaction is not required on this branch: being many stands in for it.
3. Any other record: **in** only if the counterfactual is `could_not` **and**
   `interaction_present` is `true`. Otherwise **out**.

**Review routing.** The record goes to a person (`status: review`) if any of these holds.
Its labels are then stored under `labels_if_confirmed`, never as settled.

- `confidence` is not `high`;
- non-security record: `interaction_present` is `unclear` or null;
- the counterfactual is `unclear` or null, unless the presumption fired;
- in scope, and `cooperation_occurred` is `unclear` or null;
- in scope, cooperation occurred, and `cooperation_expected` is `unclear` or null;
- in scope, not on the FM3 branch, and `objective_relation` is `unclear` or null;
- in scope, and the evidence type cannot be derived.

**Gate 2, what failed?** Only for records in scope.

1. Cooperation occurred **and** was unexpected: **FM3 Collusion**, "undesired (often covert)
   cooperation between AI systems at the expense of third parties".
2. Otherwise, by `objective_relation`: `identical` gives **FM1 Miscoordination** ("agents
   share a clear common objective but fail to align behaviour"); `mixed` gives **FM2
   Conflict** ("mixed-motive interaction ends in an outcome off the Pareto frontier");
   `opposing` gives **no failure mode**. The record stays in scope with risk factors only.
   This is where most attacks land.

**Evidence type.** Computed for every record from three facts
(`0.2/taxonomy/evidence_types.csv`):

| setting | stakes | environment controlled by | evidence type |
|---|---|---|---|
| `none` | any | any | `theoretical`: no AI system was run |
| `narrow_probe` | any | any | `lab`: a controlled probe with no environment |
| `researcher_built` | any | any | `synthetic`: a built world, market or game |
| `deployed` | `real` | `nobody` or `operator` | `real_world` |
| anything else | | | not derivable: review, if in scope |

**Presumed instances.** An in-scope security record with `multiplicity_role: unreported`
gets `instances_presumed: I28; I29` (Swarm Attacks, Heterogeneous Attacks), set by code, not
by the model. Call 2 still runs; a quoted I28 or I29 replaces the presumed pair, and the two
kinds are never stored in the same field.

### Three worked examples

All three are real call-1 rows from `0.2/proposals/extract_gate.2026-11-15.jsonl`, derived
under rules version 2026-11-16.

**aiid:528: Amazon pricing bots push a book to millions. Not an attack.** Two sellers'
pricing services "based their product's pricing on one another's as competitors".
`multiplicity_role: not_applicable` sends it down the non-security branch.
`single_agent_counterfactual: could_not` and `interaction_present: true`: **Gate 1 in**.
Gate 2: `cooperation_occurred: no`, so not FM3, although `cooperation_expected: unexpected`.
Competition is not collusion. `objective_relation: mixed`: **FM2 Conflict**. Evidence:
`deployed`, `real`, `nobody`: **real_world**. But `confidence: medium` (the primary blog
post was unreadable; only the AIID page was read), so `status: review`,
`review_why: ["confidence medium"]`, and FM2 sits under `labels_if_confirmed`.

**aiid:1796: attacker uses a two-agent Claude Code workflow against Argentine hospitals.
Decided by the presumption.** Security record, `multiplicity_role: unreported`: the source
describes a "Supervisor" and an "Executor" agent but not what having two contributed.
`n_ai_agents: 2` (not fewer than two) and the model's counterfactual is `unclear` (not
`could`), so **the presumption fires**: `counterfactual_resolved: could_not`, **Gate 1 in**,
`by_presumption: true`. The unclear counterfactual is excused because the presumption
resolved it. Gate 2: `cooperation_occurred: yes` but `expected`, so not FM3;
`objective_relation: opposing`: **no failure mode**. Evidence: `deployed`, `real`,
`operator`: **real_world**. `instances_presumed: I28, I29`. Still `status: review`, for
`confidence medium`.

**aiid:1774: agents under evaluation read confidential records in India. The presumption
does not fire.** Security record, `multiplicity_role: unreported`, `n_ai_agents: null`. Under
the rule before 2026-11-16 this would have been in by presumption. But the model answered
`single_agent_counterfactual: could`: "the mechanism (exposed credentials, no active
hacking) reads as each agent acting alone". Condition (b) fails, so the model's answer
stands: `counterfactual_resolved: could`, **Gate 1 out**, no instances presumed. Evidence
would be `synthetic` (`setting: researcher_built`). `confidence: low` sends it to review all
the same, with `gate1: out` as the label if a person confirms the facts.

### Judgement, rule, decision

- **The model's judgement:** every fact in `context/` and every field of a call-1 or call-2
  proposal, including the hard one, `single_agent_counterfactual`, and the instance picks.
- **Fixed rules:** why a record is queued, the flag rule, readiness, and everything in
  `derive.py`: the presumption, Gate 1, review routing, Gate 2, evidence type, presumed
  instances. Same facts in, same labels out.
- **Only a person:** whether an incident enters the index (`multi_agent: true`,
  `multi_agent_label_source: ours` in a dossier), the dossier's final failure mode, instances
  and evidence type, its `verification`, and whether a curator's write-up is added at all.

## How good is it?

The *gold set*, `0.2/gold/multiagent_gold.csv`, is 58 rows a person judged from the primary
sources: 22 `in`, 33 `out`, 3 `unclear`. The 3 unclear rows are left out, so 55 are scored.
It mixes the index's earlier holdings, AIID's own multi-agent positives, keyword-flagged
candidates and a control group with no signal; it oversamples hard cases on purpose, so its
precision is pessimistic. The *ceiling* is how often the index's earlier hand-curation agreed
with the careful re-review: 19 of 23, **82.6% precision**. That is what a careful person
achieved, not a trivial bar. See [gold_set.md](gold_set.md).

Call 1 plus `derive.py` on the 55 rows, with the 2026-11-16 rule: **precision 87.0%, recall
90.9%** (20 true positives, 3 false positives, 2 false negatives, 30 true negatives), from
[gate1_accuracy.md](gate1_accuracy.md). Two caveats. First, **49 of the 55 rows went to
review**; the figure scores the labels the rules would give if a person confirmed the facts.
The 6 rows settled without review were all correct, too few to quote as a rate. Second, the
gold rows' readings were written during the review, by a person, so the figure measures the
gates given good readings, not the pipeline end to end. What this means for you: a derived
verdict is a well-founded **suggestion**. It tells you where to look and what the facts imply.
It is not a verdict for the index until a person has read the source.

## Running it

### The five steps

1. **Update.** `python 0.2/pipeline/run.py update`. It walks `sources -> discover -> fetch
   -> manual -> normalise -> prefilter -> read -> ready -> judge -> derive -> review -> check
   -> index`, printing `[step]` and `ok` lines. At `read`, `judge` and `review` it prints a
   `note` saying what a person or the skill must do (at `review`: write the two sheets in
   `0.2/review/` and ask for them to be filled in), then "Not waiting: the run goes on
   without it." It ends `done.` and the path of its log, `0.2/state/runs/<run id>.json`;
   `python 0.2/pipeline/run.py runs` lists past runs.
   Options: `--refetch` (fresh AIID download), `--manual DIR`, `--discover` (a placeholder:
   not built yet).
2. **Classify.** In Claude Code, run `/classify-incidents`. It reads sources (step 0),
   writes proposals for call 1, runs `run.py derive`, then call 2 for what is due. It asks
   before long runs and before fetching. It writes only to `context/` and `proposals/`; the `run.py derive` it runs also writes
the ledger's derive columns and refreshes the review sheets in `review/`.
3. **Review.** Open `0.2/review/1_records.xlsx` and fill `scope_decision` (ok, in, out,
   unclear) for each record, checking it against the source, and for each `in` its
   `duplicate_of_decision` (ok, new, or an incident's MIG key). Run `python
   0.2/pipeline/run.py review` (or press Continue on the page): the decisions are logged,
   `new` makes the dossier, a MIG key joins the record to that incident. Write the new
   dossier's prose, then decide its labels on `0.2/review/2_incidents.xlsx` and run
   `review` again. `0.2/review/README.md` has the details.
4. **Check.** `python 0.2/pipeline/run.py check` must end `ok check: N dossiers, no
   problems` and exit 0. `warn` lines do not fail it; `FAIL` lines do.
5. **Commit** the records, the dossiers and the rebuilt `0.2/out/` together.

### The map page

`python 0.2/pipeline/run.py serve` and open `http://127.0.0.1:8765/`. It shows the pipeline
as a map of boxes with live numbers, and can start an update. Unlike the terminal, the page
**waits** at a step that needs a person and offers buttons: "Done, continue", "Skip for
now", "Try again", "Use the snapshot". It listens on 127.0.0.1 only. `0.2/out/pipeline_flow.html`
opens from disk too, with the last build's numbers, but cannot run anything.

### The test run

`python 0.2/pipeline/run.py testrun`, or the page's "Test run" button, runs the real steps on
seven made-up incidents (`aiid:9901` to `9906` and one manual record) in a temporary folder.
It never fetches, never touches the real tree, and answers every prompt itself. Use it to
learn the steps or to check a change. See [`0.2/testenv/README.md`](../testenv/README.md).

### What to do when…

- **The fetch fails.** `--refetch` needs the AIID token (`--token-file F`,
  `~/.config/aiid/token` or `$AIID_API_TOKEN`) and network. In the terminal the run stops at
  fetch; run `update` again without `--refetch` to use the snapshot. On the page, choose
  "Try again" or "Use the snapshot".
- **A source cannot be read.** The reading records depth `unreadable`, with the error in
  `read.note`. Never fill a fact in from memory. If the AIID page could be read, the record
  can still be `provisional`; if not, it stays `not_ready` and `promote` refuses it without
  `--force`. Some sites refuse automated fetches (Reuters, `OPEN.md` item 40).
- **A proposal duplicates an existing dossier.** Do not promote it; `promote` would create a
  second dossier for the same incident. Add the record to the existing dossier's `sources`
  by hand. If it is an AIID record, `check` then requires `canonical_source: aiid`. Once a
  dossier cites a record, the prefilter stops queuing it. Known cases on 2026-11-16: aiid
  1556, 1668, 1800, 1797, 1646, 1604 (`OPEN.md` item 63).
- **A record needs instances.** Run `python 0.2/pipeline/run.py instances-due`, then
  `/classify-incidents`, which runs call 2 on the list. Copy the instances that pass into the
  dossier's `instances` by hand. A quoted I28 or I29 replaces a presumed pair.
- **`check` fails.** Each `FAIL` line names the file and the rule. The commonest: a dossier
  with `multi_agent: true` and a label source other than `ours`.

## Where things are

All paths under `0.2/` unless shown.

| path | what | who writes it | edit by hand? |
|---|---|---|---|
| `registry/sources.csv` | the source registry | person | yes |
| `registry/labels/` | hand-copied outside labels (the Navigator list) | person | yes |
| `taxonomy/` | risks (FM1-3, RF1-7), 36 instances, FM-RF associations, evidence types | person | yes, with care |
| `raw/<source>/` | verbatim fetch output | `fetch`, `update --manual` | **never** |
| `records/<source>.jsonl` | normalised records, append-only | `normalise`, `update --manual` | **never** |
| `context/<source>.jsonl` | readings of the sources | the skill; `update --manual` | no |
| `proposals/` | model output, never authoritative | the skill | no |
| `state/` | queue, readiness, verdicts, instances due, run logs | `run.py` | no |
| `incidents/<ID>.md` | the dossiers: the curated record | person | **yes**: this is your work |
| `out/` | the index and the pages | `index`, `viz` | **never** |
| `prompts/` | the versioned prompts | person | only as a new version |
| `pipeline/derive.py` | the labelling rules | person | only with a rules-version bump and a gold re-score |
| `gold/` | the gold set and scoring | person | through `gold/build_review.py` |
| `testenv/` | test-run fixtures, all made up | person | never put real incidents here |
| `docs/` | these documents | person | yes |
| `OPEN.md` (repo root) | open questions and decisions | person | yes |

## Known limits

- **Almost everything goes to review.** 102 of 103 verdicts on 2026-11-16, and 49 of 55 gold
  rows. The pipeline saves reading, not judging (`OPEN.md` items 59, 63).
- **The presumption counts all agents, not the attacking side.** `n_ai_agents` is asked for
  the whole record; a prompt v4 with an attacking-side field is proposed (item 59).
- **The accuracy figures assume good readings.** Gold readings were written during review;
  fresh enrichment readings will be weaker (item 59).
- **694 queued records have never been read** on 2026-11-16, most of them newly caught by
  the `recent` basis (item 60).
- **Pre-2024 incidents outside the frozen list are not queued**, and the keyword
  flag's recall is unmeasured (items 45, 60).
- **Source-pass quotes came through a summarising fetcher** and must be checked against the
  page before they enter a dossier (item 63).
- **Dossiers are not yet linked to their AIID records** (items 25, 63).
- **Discovery of non-AIID sources is not built**; the forum adapter is the main gap
  (item 24).
- **The map's node counts mix populations** (item 58).
- **The record pass has not been measured on the gold set** before a full run
  ([context_layer.md](context_layer.md) § Limits).
