# AIID fetch manifest

Raw pulls from the [AI Incident Database](https://incidentdatabase.ai) GraphQL API,
plus the derived candidate lists. Content is CC-BY-SA 4.0; attribute it if a row
reaches `data/incidents.csv` and record the source in `data/sources.csv`.

`fetch_aiid.py` overwrites its outputs on every run, so this file is the record of
which snapshot the claims in `OPEN.md` item 23 rest on.

## Snapshot 2026-11-09

Endpoint `https://incidentdatabase.ai/api/graphql`.

| File | Rows | Command |
|---|---|---|
| `incidents.jsonl` | 1,803 | `python3 build/fetch_aiid.py --depth 0 --sort-field incident_id` |
| `classifications.jsonl` | 2,623 | `python3 build/fetch_aiid.py --collection classifications --depth 1 --exclude reports --sort-field _id` |

Incidents span 1983-09-26 to 2026-11-05, ids 1–1814.
Classification namespaces: MIT 1,498 · GMF 326 · CSETv1 214 · CSETv1_Annotator-1 298 ·
CSETv1_Annotator-2 106 · CSETv1_Annotator-3 81 · CSETv0 100.

Three things about the fetch flags, each established the hard way:

- From `classifications`, `--depth 1` is what reaches `attributes { short_name value_json }`.
  Depth 0 omits them; depth 2 adds nothing needed.
- `--exclude reports` is mandatory. Without it each row drags full report bodies and the
  run grinds against the server's 6 MB response cap.
- `--sort-field _id` is required. `incident_id` is not a `Classification` scalar, so the
  default silently disables sorting and paging by `skip` becomes unstable. Note also that
  sorting ascending by `_id` orders by creation time, so any `--max-records` smoke test on
  this collection returns only the oldest namespace (CSETv0) and nothing about MIT.

Each run also writes a flattened `.csv` beside each `.jsonl`. Those are gitignored:
the JSONL is the archive, the CSV is a convenience view the same call regenerates.

## Derived files

| File | Contents |
|---|---|
| `navigator_multiagent.tsv` | The 28 incidents under `behaviour=Multi-agent` in the [MIT AI Risk Navigator](https://airisk.mit.edu/navigator), read from the rendered page on 2026-11-09 and matched to AIID ids. Columns: aiid_incident_id, date, nav_risk_subdomain, nav_extra_subdomains, entity, intent, timing, title. |
| `candidates_multiagent.tsv` | Keyword prefilter over all 1,803 incidents: 11 strong-signal and 214 weak-signal candidates, with their MIT subdomain and entity where one exists. Columns: incident_id, date, tier, mit_subdomain, mit_entity, title, description. |

Navigator labels are a research prototype, described on the site as "preliminary and not
yet validated"; the site asks that its visualizations not be redistributed. Treat both the
MIT labels and the Navigator behaviour facet as a machine rater's candidate signal, never
as evidence for a score.
