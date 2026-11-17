# labels

External labels that were made by hand and so cannot live in `mvp/raw/`, which holds only
verbatim fetch output.

## navigator_multiagent.tsv

The MIT AI Risk Navigator's behaviour facet, `behaviour = Multi-agent`. It lists 28 AIID
incidents, one row each, keyed by `aiid_incident_id`.

- Copied by hand from the Navigator's rendered web page on 2026-11-09. No script in this
  project can fetch it again. To refresh it, copy the page again by hand and replace the
  file.
- Read by `mvp/pipeline/run.py` at `normalise` (`read_navigator`). Each listed incident
  gets one external label on its AIID record: source `mit_navigator`, field `behaviour`,
  value `Multi-agent`. The prefilter's `label` arm counts it.
- A label marks a candidate. It never puts an incident in scope by itself.
