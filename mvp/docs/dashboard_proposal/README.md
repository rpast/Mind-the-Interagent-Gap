# Dashboard proposal

A design proposal for the mvp dashboard, the successor to the PoC's
`poc/build/dashboard_template.html`. Work in progress; not yet a pipeline step.

| file | what |
|---|---|
| `interagent_gap_index.html` | the assembled page, data inlined, opens on file:// |
| `head.html` | title, fonts and all CSS |
| `body.html` | the sections; the §5 flowchart SVG is pasted in from `flow.py` |
| `app.js` | renders every figure and the table from the inlined data; the shared click filter and side panel |
| `mk.py` | exports `mvp/out/incident_index.csv`, the dossiers' source links, `mvp/taxonomy/` and `mvp/registry/sources.csv` as JSON |
| `flow.py` | writes the §5 method flowchart as SVG (`flow.svg`) |
| `build.sh` | rebuilds the page: `sh mvp/docs/dashboard_proposal/build.sh` from the repository root |

Decisions taken while designing it:

- Counts only. No score or grounding, since scoring is parked.
- Failure modes come only from the dossier's `failure_mode`. Risk factors are not classified,
  and no incident is given one through its instances.
- The instance × failure-mode matrix lists instances flat, in id order, so no block of
  risk-factor instances crosses the failure-mode columns.

Intended home once accepted: a `run.py dashboard` step writing to `mvp/out/`.
