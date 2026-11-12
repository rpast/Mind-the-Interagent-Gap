# PoC — frozen

This tree is the proof of concept that established the ontology: the Hammond et al. (2025)
failure modes and risk factors, 36 instances as the link layer, 13 case studies and 27
incidents scored E1–E5, a grounding score per risk, and a self-contained dashboard.

It is **reference only**. It is not extended, and it receives no new data. New work happens
in `mvp/`, which is built from zero and carries forward the lessons rather than the
structure. The two trees do not share files.

## Still runnable

```
pip install -r ../requirements.txt
python poc/build/build_xlsx.py        # run from the repository root
```

It validates `poc/data/*.csv` and rewrites `poc/out/`. Nothing in it changed during the
move: `build_xlsx.py` resolves its paths from its own location, so relocating `build/`,
`data/` and `out/` together needed no code edit.

`poc/out/multi_agent_risk_taxonomy.xlsx` is not byte-reproducible across rebuilds — it is a
zip archive and embeds timestamps. The five other outputs are.

## What carries forward into `mvp/`

- **Evidence reaches a risk only through an instance.** Two tags on one row are a
  conjunction, never a connection. This is why the mvp has its own instance repository and
  why its failure-mode classifier assigns instance ids rather than failure modes.
- **Grounding is a maximum, never a sum.** Corroboration is already scored inside E4.
- **Associations come only from the authors.** They are never inferred from our own tags
  co-occurring.
- **One fact per field**, and multi-value fields hold `;`-separated ids.

## What is deliberately left behind

- Scoring. E1–E5 live here and are parked; no E-score appears anywhere in `mvp/`.
- The flat-CSV incident row. It cannot hold the mechanism or the response, which is the
  reason the mvp stores one dossier per incident.
- Hand-only ingestion. The mvp has a runnable update routine instead.

## Contents

| path | what |
|---|---|
| `build/build_xlsx.py` | validates the data and writes `out/` |
| `build/dashboard_template.html` | the dashboard, with a `__DATA__` placeholder |
| `data/*.csv` | the PoC's source of truth |
| `out/*` | build artifacts, committed alongside the data |
| `docs/methodology.md` | definitions, the evidence rubric and the scoring rules |
| `docs/mapping_2026-10-26.md` | the hand mapping of the 27 incidents to risks and scores |
| `docs/validation_2026-10-26.md` | the external validation pass over the inventory |
