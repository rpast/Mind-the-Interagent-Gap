# Gold-set source context

Enriched facts for the gold rows, read from the primary and registry sources on 2026-11-13.

## Why this exists

Every gold row carried only its one-line inventory text: 70–261 characters for the
carried-over rows, 335–500 for the AIID ones. That is a headline, not a record. It is not
enough for a human to apply the two gates, and not enough for a classifier either — several
of the facts the gates need (how many agents, whether they interacted, who controlled the
environment, whether multiplicity mattered) were simply absent from the text being judged.

These files hold what the sources actually say, field by field, in the shape the gates ask
for.

## What is in a row

One JSON object per gold row, keyed by `gold_id`, with the source record it came from and
these fields where the source supports them: `agents`, `operators`, `mechanism`,
`interaction`, `multiplicity`, `setting`, `coop`, `obj`, `quote`, `primary`, `caveat`.
`multiplicity` is the fact behind `multiplicity_role`, written out: what the source says the
number or variety of agents contributed, or that it says nothing. "not stated" means the
source is silent, and that is a finding, not a gap in the fetch.

`caveat` is this project's own reading, not the source's. It flags provenance problems,
duplicates and verdicts worth revisiting. It is commentary and carries no authority.

## Coverage

41 of 60 rows. The 19 left out are all reviewed `out` and all describe one AI system —
deepfakes, voice-cloning scams, a single coding agent, a robotaxi fire. Their AIID
description is already the full record and nothing in them turns on a fact a fetch would
settle. They are listed in `OPEN.md`.

## Provenance and limits

- Fetched 2026-11-13 over HTTP. **Nothing here is verbatim fetch output** — each row is a
  reading of the source, so this directory is not `mvp/raw/`.
- `air_enkrypt.jsonl` paraphrases the Agent Incident Registry, which asks to be contacted
  before dataset reuse. One short quote per row, no bulk text. That registry is a secondary
  source; `primary` names what it cites, and those should be read before a dossier rests on
  it.
- AIID rows: the incident description and editor notes were read in full. Linked reports were
  read only from the teasers on the incident page, not from the external articles.
- `lesswrong:LW-01` is a PDF that text extraction cannot read; it was read as page images.
- `lesswrong:LW-04` could not be read at all. Reuters refuses automated fetches.
