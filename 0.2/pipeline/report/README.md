# The report

The published report: one page for readers, the successor to the PoC's
`poc/build/dashboard_template.html`. Built by its own step, from what the last `index`
wrote:

    python 0.2/pipeline/run.py index     # if the dossiers changed
    python 0.2/pipeline/run.py report    # -> 0.2/out/index_report.html

`report` is deliberately not part of `update`, `viz` or `serve`. The index is rebuilt on
every run; a report is built when someone decides the index is worth reporting.

| file | what |
|---|---|
| `head.html` | title, fonts and all CSS |
| `body.html` | the sections; the §5 flowchart SVG is pasted in from `flow.py` |
| `app.js` | renders every figure and the table from the inlined data; the shared click filter and side panel |
| `VERSION` | the report's version, shown in the top bar and above the title |
| `flow.py` | writes the §5 method flowchart as SVG (`flow.svg`), to paste into `body.html` by hand |

`stage_report` in `run.py` gathers the data (`report_data`) and joins the three parts into
one file with the data inlined; it opens on file://. The data is
`0.2/out/incident_index.csv`, each dossier's canonical link, `0.2/taxonomy/risks.csv` and
`instances.csv`, and `0.2/registry/sources.csv`.

The report shows only the incidents a person put in scope (`multi_agent: True` in the
index). Those decided out of scope or unclear are left out of it entirely; they stay in
`0.2/out/incident_index.csv` with that flag, and in their dossiers.

## Version and dates

- **Version** comes from `VERSION`. Change it by hand when a release's scope changes:
  0.1 mapped failure modes only, built from `mvp/`; 0.2 is built from `0.2/`, whose
  folder name follows this version.
- **Sources last refreshed** is the AIID fetch date in `0.2/raw/aiid/FETCHED.md`. Sources
  added by hand have no fetch date, so the page shows none for them.
- **Index as of** is `generated_at` in `0.2/state/pipeline.json`, written by `index`.

## Publishing

The claude.ai page is a separate copy. It changes only when
`0.2/out/index_report.html` is published to it, which is always a deliberate step,
never automatic.

## Design decisions

- Counts only. No score or grounding, since scoring is parked.
- Failure modes come only from the dossier's `failure_mode`. Risk factors are not classified,
  and no incident is given one through its instances.
- The instance × failure-mode matrix lists instances flat, in id order, so no block of
  risk-factor instances crosses the failure-mode columns.
