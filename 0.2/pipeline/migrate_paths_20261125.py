#!/usr/bin/env python3
"""Make 0.2/'s data name 0.2/, not mvp/. One-off, kept for provenance.

0.2/ began on 2026-11-25 as a copy of mvp/ (0.2/docs/plan.md, P1). The machine-written
files it carried over still named their paths under mvp/. This rewrites them, so 0.2/
depends on nothing in the frozen tree:

- records/*.jsonl: each row's raw_ref.path. raw_ref is not part of the content hash
  (run.make_record), so no hash changes and no row is added or removed;
- the fetch note, the calibration outputs and the local run logs: their path text.

Nothing else in a row changes. Run once, from the repository root:

    python 0.2/pipeline/migrate_paths_20261125.py
"""
from __future__ import annotations

import re
from pathlib import Path

TREE = Path(__file__).resolve().parents[1]
OLD_REF = '"path": "mvp/'
NEW_REF = '"path": "0.2/'
PATH_TEXT = re.compile(r"(?<![\w./-])mvp/")


def rewrite(path: Path, fn) -> int:
    text = path.read_text(encoding="utf-8")
    new, n = fn(text)
    if n:
        path.write_text(new, encoding="utf-8")
    return n


def main():
    total = 0
    for p in sorted((TREE / "records").glob("*.jsonl")):
        n = rewrite(p, lambda t: (t.replace(OLD_REF, NEW_REF), t.count(OLD_REF)))
        print(f"{n:5d}  raw_ref paths  {p.relative_to(TREE.parent)}")
        total += n
    texts = ([TREE / "raw" / "aiid" / "FETCHED.md", TREE / "out" / "gate1_accuracy.json",
              TREE / "state" / "work_orders.md"]
             + sorted((TREE / "out" / "calibration").glob("*"))
             + sorted((TREE / "state" / "runs").glob("*.json")))
    for p in texts:
        if p.is_file():
            n = rewrite(p, lambda t: PATH_TEXT.subn("0.2/", t))
            if n:
                print(f"{n:5d}  path text      {p.relative_to(TREE.parent)}")
                total += n
    print(f"{total} paths rewritten")


if __name__ == "__main__":
    main()
