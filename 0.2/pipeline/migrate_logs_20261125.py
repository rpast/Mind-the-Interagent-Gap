#!/usr/bin/env python3
"""Carry the three review logs of 0.1 into the two of 0.2. One-off, kept for provenance.

0.2/docs/plan.md, P5. Until now: scope_decisions_log.csv (sheet 1), promote_decisions_log.csv
(sheet 2) and dossier_edits_log.csv (sheet 3). From now: record_decisions_log.csv and
incident_decisions_log.csv, one row per label decision (decide.LOG_COLS). Each old row
becomes one new row, with its dates:

  scope    -> record log, label scope; decision and final the value decided
  promote  yes -> record log, label duplicate_of, final `new` (the record got a dossier
           of its own); no -> label dossier, final `no` (a person said: no dossier).
           Kept as the person wrote it, not read as a change of scope.
  edits    -> incident log, the field as the label (multi_agent as incident_scope)

`proposed` is blank: 0.1 did not log what the rules proposed. Only after every old row is
written are the old logs removed. Run once, from the repository root:

    python 0.2/pipeline/migrate_logs_20261125.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run  # noqa: E402
import decide  # noqa: E402

OLD = {"scope": "scope_decisions_log.csv", "promote": "promote_decisions_log.csv",
       "edits": "dossier_edits_log.csv"}
FIELD_LABEL = {"multi_agent": "incident_scope", "title": "incident_title"}


def main():
    paths = {k: run.REVIEW / v for k, v in OLD.items()}
    if any(decide.log_path(run.THIS, k).exists() for k in decide.LOGS):
        sys.exit("the 0.2 logs exist already; this migration runs once")
    record, incident = [], []
    for r in run.read_csv(paths["scope"]) if paths["scope"].exists() else []:
        record.append({"mig_key": r["mig_key"], "label": "scope", "proposed": "",
                       "decision": r["decision"], "final": r["decision"],
                       "reason": r["reason"], "decided_on": r["decided_on"],
                       "sheet_generated_on": r["sheet_generated_on"]})
    for r in run.read_csv(paths["promote"]) if paths["promote"].exists() else []:
        label, final = ("duplicate_of", "new") if r["decision"] == "yes" else ("dossier", "no")
        record.append({"mig_key": r["mig_key"], "label": label, "proposed": "",
                       "decision": final, "final": final, "reason": r["note"],
                       "decided_on": r["decided_on"],
                       "sheet_generated_on": r["sheet_generated_on"]})
    for r in run.read_csv(paths["edits"]) if paths["edits"].exists() else []:
        incident.append({"mig_key": r["mig_key"],
                         "label": FIELD_LABEL.get(r["field"], r["field"]),
                         "proposed": r["old_value"], "decision": r["new_value"],
                         "final": r["new_value"], "reason": "",
                         "decided_on": r["decided_on"],
                         "sheet_generated_on": r["sheet_generated_on"]})
    decide.ensure_logs(run.THIS)
    decide.append_log(run.THIS, "record", record)
    decide.append_log(run.THIS, "incident", incident)
    if len(decide.read_log(run.THIS, "record")) != len(record) or \
            len(decide.read_log(run.THIS, "incident")) != len(incident):
        sys.exit("the new logs do not hold every old row; the old logs are kept")
    for p in paths.values():
        if p.exists():
            p.unlink()
    decide.write_decision_columns(run.THIS)
    print(f"  ok    {len(record)} record decision(s), {len(incident)} incident decision(s) "
          f"carried over; the three 0.1 logs removed")


if __name__ == "__main__":
    main()
