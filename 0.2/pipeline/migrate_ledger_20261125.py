#!/usr/bin/env python3
"""Build the ledger from the files it replaces. One-off, kept for provenance.

0.2/docs/plan.md, P2. Until now the prefilter wrote state/queue.jsonl and derive wrote
state/verdicts.jsonl. Both become columns of ledger/ledger.csv. This script:

1. writes the load columns for every record; `loaded_on`, which did not exist, is set
   from each record's fetch date (the closest date on file; documented as backfilled);
2. writes the prefilter columns from state/queue.jsonl as it stands, and the derive
   columns from state/verdicts.jsonl as it stands - carried over, not recomputed;
3. writes the reading columns from context/;
4. checks that the queue and the verdicts rebuilt from the ledger equal the two files,
   row for row and field for field;
5. only then deletes the two files.

Nothing is decided here: every value is one the pipeline had already written.

    python 0.2/pipeline/migrate_ledger_20261125.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run  # noqa: E402
import ledger  # noqa: E402


def main():
    queue_file = run.STATE / "queue.jsonl"
    verdicts_file = run.STATE / "verdicts.jsonl"
    if run.LEDGER.exists():
        sys.exit(f"{run.LEDGER.relative_to(run.ROOT)} exists; this migration runs once")
    if not queue_file.exists() or not verdicts_file.exists():
        sys.exit("state/queue.jsonl or state/verdicts.jsonl is missing; nothing to migrate")
    old_queue = run.read_jsonl(queue_file)
    old_verdicts = {run.row_pair(v): v for v in run.read_jsonl(verdicts_file)}

    run.ledger_load(backfill=True)
    ledger.write(run.LEDGER, "prefilter",
                 {q["record_key"]: run.prefilter_columns(q) for q in old_queue})
    gates = run.proposal_rows("extract_gate")
    refs = run.proposal_files("extract_gate")
    ledger.write(run.LEDGER, "derive",
                 {run.record_key(*pair): run.derive_columns(gates.get(pair, {}), v,
                                                            refs.get(pair, ""))
                  for pair, v in old_verdicts.items()})
    n_read = run.write_reading_columns()

    problems = []
    new_queue = run.read_queue()
    if len(new_queue) != len(old_queue):
        problems.append(f"queue: {len(old_queue)} rows before, {len(new_queue)} after")
    for a, b in zip(sorted(old_queue, key=lambda q: (q["source_id"], q["source_record_id"])),
                    new_queue):
        if a != b:
            problems.append(f"queue row differs: {a.get('record_key')}: "
                            f"{ {k: (a.get(k), b.get(k)) for k in a if a.get(k) != b.get(k)} }")
            break
    new_verdicts = run.read_verdicts()
    if set(new_verdicts) != set(old_verdicts):
        problems.append(f"verdicts: {len(old_verdicts)} before, {len(new_verdicts)} after")
    for pair, a in old_verdicts.items():
        b = new_verdicts.get(pair)
        if a != b:
            problems.append(f"verdict differs: {run.record_key(*pair)}: "
                            f"{ {k: (a.get(k), (b or {}).get(k)) for k in set(a) | set(b or {}) if a.get(k) != (b or {}).get(k)} }")
            break
    if problems:
        for p in problems:
            print(f"  FAIL  {p}")
        sys.exit("the ledger does not reproduce the files; they are kept")

    queue_file.unlink()
    verdicts_file.unlink()
    rows = ledger.read(run.LEDGER)
    print(f"  ok    ledger: {len(rows)} records, {len(new_queue)} queued, "
          f"{len(new_verdicts)} verdicts, {n_read} readings; queue and verdicts "
          f"reproduced exactly; state/queue.jsonl and state/verdicts.jsonl removed")


if __name__ == "__main__":
    main()
