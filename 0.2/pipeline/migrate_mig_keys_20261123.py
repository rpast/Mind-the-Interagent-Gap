#!/usr/bin/env python3
"""One-off, 2026-11-23: two key fields, and our key on every record that reaches review.

Until today a dossier's id was AIID-nnnn when AIID attested the incident and MIG-nnnn
otherwise, and the review sheets and logs named records by record_key ("aiid:794"),
which mixes the source with its key. From now on:

  - `mig_key`, MIG-nnnn, is our key. Every record that reaches the decide-scope sheet
    gets one, once, and its dossier keeps it. The registry is
    0.2/registry/mig_keys.csv: one row per key, the record it was given to.
  - `source_key` is the key the source itself uses (AIID's 794), blank when the source
    has none (a hand-added record).

What this script does, once:

  1. Gives every dossier a MIG key. MIG-nnnn dossiers keep theirs. The five dossiers
     renamed from MIG to AIID earlier today get their MIG key back (RESTORE). The other
     26 AIID-nnnn dossiers get MIG-0028 onward, in order of their AIID number.
  2. Rewrites each dossier: `id` becomes `mig_key`, `source_key` is added, the file is
     renamed to <mig_key>.md, and a renamed dossier gets a dated line in its
     ## Verification notes saying so. Nothing else in it changes.
  3. Writes the registry: the dossiers' keys first, then a new key for every other
     record that has a derived verdict (it has been on the decide-scope sheet), or is
     named in a decision log, or was added by hand, in record order.
  4. Rewrites the two decision logs, scope_decisions.csv and promote_decisions.csv,
     with `mig_key, source_id, source_key` in place of `record_key`. Every row is kept,
     in order, with its decision, text and dates unchanged.
  5. Rewrites the gold set's `dossier` column with the new keys.

Idempotent: once no dossier has `id`, it says so and writes nothing. Then run
`run.py check`, `index`, `viz` and `index_report.py`.

    python 0.2/pipeline/migrate_mig_keys_20261123.py
"""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as pipeline  # noqa: E402  the pipeline owns the formats

RESTORE = {"AIID-1054": "MIG-0003", "AIID-1668": "MIG-0016", "AIID-1797": "MIG-0017",
           "AIID-1646": "MIG-0019", "AIID-1604": "MIG-0020"}
TODAY = pipeline.TODAY
OLD_LOG_COLS = {"scope": ["record_key", "decision", "reason", "decided_on",
                          "sheet_generated_on"],
                "promote": ["record_key", "decision", "note", "decided_on",
                            "sheet_generated_on"]}


def main():
    dossiers = []
    for path in pipeline.all_dossiers():
        meta, body = pipeline.read_dossier(path)
        dossiers.append((path, meta, body))
    if not any("id" in meta for _, meta, _ in dossiers):
        print("  ok    nothing to do: no dossier has `id` any more")
        return 0
    if pipeline.MIG_KEYS.exists():
        sys.exit(f"error: {pipeline.MIG_KEYS} exists already; this script writes it")

    # 1. a key per dossier
    new_of = {}
    for _, meta, _ in dossiers:
        old = meta["id"]
        if re.fullmatch(pipeline.MIG_PATTERN, old):
            new_of[old] = old
        elif old in RESTORE:
            new_of[old] = RESTORE[old]
    taken = set(new_of.values())
    n = max(int(k[4:]) for k in taken) + 1
    for old in sorted((m["id"] for _, m, _ in dossiers if m["id"] not in new_of),
                      key=lambda i: int(i.split("-")[1])):
        while f"MIG-{n:04d}" in taken:
            n += 1
        new_of[old] = f"MIG-{n:04d}"
        taken.add(new_of[old])
    assert len(set(new_of.values())) == len(new_of) == len(dossiers)

    # 2. the dossiers
    reg_rows, attested = [], set()
    for path, meta, body in dossiers:
        old, key = meta["id"], new_of[meta["id"]]
        pair = pipeline.canonical_pair(meta)
        new = {"mig_key": key, "source_key": pipeline.source_key(*pair)}
        new.update({k: v for k, v in meta.items() if k != "id"})
        if key != old:
            line = (f"{TODAY}: renamed from {old} to {key}. Every incident is now keyed by "
                    f"its MIG key; the source's own key, {pair[0]} "
                    f"{pipeline.source_key(*pair)}, is in source_key.")
            if old in RESTORE:
                line = (f"{TODAY}: renamed from {old} back to {key}, the key it had before "
                        f"AIID was linked. Every incident is now keyed by its MIG key; "
                        f"AIID's own key, {pipeline.source_key(*pair)}, is in source_key.")
            body = pipeline.add_to_section(body, "Verification notes", line)
        dest = pipeline.dossier_path(key)
        if dest != path and dest.exists():
            sys.exit(f"error: {dest} exists already")
        pipeline.write_dossier_body(dest, new, body)
        if dest != path:
            path.unlink()
        reg_rows.append({"mig_key": key, "source_id": pair[0], "source_record_id": pair[1],
                         "assigned_on": meta.get("first_seen") or TODAY,
                         "basis": "dossier"})
        for s in meta.get("sources") or []:
            attested.add((s.get("source_id"), str(s.get("record_id"))))
        print(f"  ok    {old:10s} -> {key}  source_key {pipeline.source_key(*pair)!r}")

    # 3. the registry
    logs = {}
    for kind in ("scope", "promote"):
        path = pipeline.REVIEW / pipeline.SHEETS[kind]["log"]
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != OLD_LOG_COLS[kind]:
                sys.exit(f"error: {path} has header {reader.fieldnames}, expected "
                         f"{OLD_LOG_COLS[kind]}")
            logs[kind] = list(reader)
    records = pipeline.latest_records()
    pairs = set(pipeline.read_verdicts())
    pairs |= {p for p in records if p[0] == pipeline.MANUAL}
    pairs |= {pipeline.split_key(r["record_key"]) for rows in logs.values() for r in rows}
    reg_rows.sort(key=lambda r: r["mig_key"])
    n = max(int(r["mig_key"][4:]) for r in reg_rows) + 1
    for pair in sorted(pairs - attested, key=lambda p: pipeline.natural(
            pipeline.record_key(*p))):
        reg_rows.append({"mig_key": f"MIG-{n:04d}", "source_id": pair[0],
                         "source_record_id": pair[1], "assigned_on": TODAY,
                         "basis": "decide scope"})
        n += 1
    pipeline.MIG_KEYS.parent.mkdir(parents=True, exist_ok=True)
    with open(pipeline.MIG_KEYS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=pipeline.MIG_COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(reg_rows)
    print(f"  ok    {pipeline.MIG_KEYS.relative_to(pipeline.ROOT)}: {len(reg_rows)} keys "
          f"({len(dossiers)} dossiers, {len(reg_rows) - len(dossiers)} other records)")

    # 4. the decision logs
    index = pipeline.mig_index()
    for kind, rows in logs.items():
        cfg = pipeline.SHEETS[kind]
        path = pipeline.REVIEW / cfg["log"]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cfg["cols"], lineterminator="\n")
            w.writeheader()
            for r in rows:
                fields = pipeline.key_fields(pipeline.split_key(r["record_key"]), index)
                assert fields["mig_key"], r["record_key"]
                w.writerow({**{c: r.get(c, "") for c in cfg["cols"]}, **fields})
        print(f"  ok    {path.relative_to(pipeline.ROOT)}: {len(rows)} rows rekeyed")

    # 5. the gold set
    gold = pipeline.TREE / "gold" / "multiagent_gold.csv"
    eol = "\r\n" if b"\r\n" in gold.read_bytes() else "\n"   # keep the file's own
    with open(gold, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        head, rows = reader.fieldnames, list(reader)
    changed = 0
    for r in rows:
        if r.get("dossier") in new_of and new_of[r["dossier"]] != r["dossier"]:
            r["dossier"] = new_of[r["dossier"]]
            changed += 1
    with open(gold, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=head, lineterminator=eol)
        w.writeheader()
        w.writerows(rows)
    print(f"  ok    {gold.relative_to(pipeline.ROOT)}: {changed} dossier keys rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main())
