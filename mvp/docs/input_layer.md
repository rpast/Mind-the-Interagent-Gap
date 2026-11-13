# Input layer

How incidents get in: the sources, the record store, the dossiers, and the one command that
runs it.

## The shape

Two levels, because one incident appears in several sources and a single-level store
duplicates it the first time a second adapter runs.

```
mvp/raw/<source>/          verbatim fetch output. Never hand-edited.
mvp/records/<source>.jsonl normalised, append-only, content-hashed. Machine-written.
mvp/incidents/<ID>.md      the curated record. Hand-edited. One dossier per incident.
mvp/out/incident_index.csv a flat index generated from the dossiers.
```

A record is what one source said, when we fetched it. A dossier is what we believe happened,
citing the records that attest it.

## The update routine

```
python mvp/pipeline/run.py update --mode labelled-only   # AIID, external labels only
python mvp/pipeline/run.py update --mode aiid-full       # AIID, prefilter, queue for the classifier
python mvp/pipeline/run.py update --mode all-sources     # the above plus the discovery sources
```

| mode | fetches | screens by | classifier |
|---|---|---|---|
| `labelled-only` | AIID | external multi-agent labels only | no |
| `aiid-full` | AIID | all three prefilter arms | yes |
| `all-sources` | AIID + discovery sources | all three arms | yes |

AIID is the **baseline** source and is fetched in every mode. Everything else is a
**discovery** source, searched for incidents AIID does not carry — which matters, because
18 of the project's 27 incidents are absent from AIID entirely, including all 7 AI Village
rows.

Each stage is also runnable alone: `fetch`, `normalise`, `discover`, `prefilter`, `promote`,
`index`, `viz`, `check`.

## Stages

**fetch** dispatches on the registry's `adapter` column. AIID imports
`mvp/pipeline/fetch_aiid.py` as a library and never modifies it. A source a script cannot
reach does not fail silently: it writes a **work order** to `mvp/state/work_orders.md`
saying what to search, where, and what to paste back. A human-in-the-loop source is a stage,
not a gap.

**normalise** writes one record per source record. AIID needs a join: `incidents.jsonl` at
depth 0 carries no classifications, and `classifications.jsonl` has no `incident_id` — its
only path back is the expanded `incidents` list, so the join is on `incidents[]._id`. It
harvests the `Multiple AI Interaction` attribute from the consensus `CSETv1` namespace *and*
all three `CSETv1_Annotator-*` namespaces, so rater disagreement stays visible.

**prefilter** is a union of three arms, because no single net has acceptable recall:

| arm | rule | current |
|---|---|---|
| `label` | any external label says `yes` or `maybe`, including one dissenting annotator | 39 |
| `keyword` | the recall-first regex net, lifted from the exploratory notebook | 62 |
| `unclassified` | no classification at all, and dated on or after 2024-01-01 | 286 |

The third arm exists because 305 of AIID's 1,803 incidents carry no classification, and they
are the recent ones. An unclassified record is unscreened, not negative — which is a
different thing from a record CSETv1 looked at and called `no`.

Measured, which is why there are three arms and not one: the keyword arm alone gets **78%
recall** (21 of 27) against our own known positives, and the MIT Navigator's rater has a
**33% false-negative rate** on the 9 of our incidents that are in AIID.

**classify** is not part of `run.py`. It is a Claude Code skill, `/classify-incidents`,
because a Pro subscription covers Claude Code and not the Messages API. See
`mvp/docs/classifiers.md`.

**promote** scaffolds a dossier from a record, with every narrative section marked pending.
A scaffold is not a record: the gaps are filled by hand against the primary source.

**check** validates and exits non-zero. It enforces the id pattern, every required
frontmatter key, ISO or partial-ISO dates with matching precision, that every `sources[]`
entry resolves to a record that exists, that every instance id is in the taxonomy, every
controlled vocabulary, all seven narrative sections, that AIID is the canonical source
wherever it attests an incident, and that no `e1..e5` key has crept in.

## Idempotency

Records are keyed on `(source_id, source_record_id)` and carry a `content_hash` over the
fields that matter. A re-fetch appends a new version **only when the hash changed**, so an
upstream edit is detected rather than silently overwriting, and re-running `update` on
unchanged upstream data produces no diff.

## Dossier format

YAML frontmatter plus seven fixed sections, so dossiers diff cleanly and `rg` finds them by
narrative content.

Id comes from the canonical source: `AIID-0007.md` where AIID attests the incident,
`MIG-nnnn.md` where no indexed database does. When AIID is among the sources it is the
canonical one, and `check` enforces that.

Required frontmatter: `id`, `title`, `canonical_source`, `sources`, `occurrence_date`,
`occurrence_date_precision`, `first_seen`, `last_verified`, `systems`, `actor_count`,
`interaction_kind`, `evidence_type`, `multi_agent`, `multi_agent_basis`,
`multi_agent_label_source`, `external_labels`, `failure_mode`, `failure_mode_source`,
`instances`, `verification`.

Sections, in this order: `## Context`, `## What happened`, `## Mechanism`,
`## Agents and interaction`, `## Response`, `## Verification notes`, `## Sources`.

**No evidence scores.** The evidence-scoring rubric is parked, so a dossier carries no
score fields.

## Vocabularies

- `evidence_type`: `real_world` · `synthetic` · `lab` · `theoretical`
- `interaction_kind`: `communication` · `one-acting-on-another` · `shared-environment` ·
  `none` · `unclear`
- `verification`: `verified` · `partially_verified` · `unverified`
- `multi_agent_label_source`: `ours` · `external:<source_id>` · `classifier:<prompt>@<ver>`
- `occurrence_date_precision`: `day` · `month` · `year`

## The registry

`mvp/registry/sources.csv` is the machine-readable spine the pipeline reads: one row per
source, with its role, access method, adapter, reuse status and where its multi-agent label
lives, if it has one. Three files describe sources and each has one job:

| file | job |
|---|---|
| `mvp/registry/sources.csv` | what the pipeline reads: role, adapter, access, reuse, label field |
| `RESOURCES.md` | the human lead list: what is worth reading, what blocks reading it |
| `docs/sources.txt` | the audit trail: which source backs which row, what was screened and rejected |

A source may appear in all three. Each note belongs to exactly one.

## Known gaps

- The ForumMagnum adapter (LessWrong, Alignment Forum, EA Forum) is specified but not
  implemented; those sources currently emit work orders.
- None of the 27 migrated incidents is linked to an AIID record. The migration looked for
  close title matches and found none above threshold; linking is deliberately not automatic,
  because a wrong merge is worse than a missing one.
- Four migrated titles were truncated from a long summary sentence and want renaming by
  hand: the dossiers for AIR-2026-0101, AIR-2026-0219, AIR-2026-0194 and AIR-2026-0183.
- `actor_count` and `interaction_kind` are `unclear` on every carried-over dossier, because
  the inventory they came from did not record either. Both have to be filled from the
  primary sources; `interaction_kind` feeds the failure-mode assignment.
