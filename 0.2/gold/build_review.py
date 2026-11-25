#!/usr/bin/env python3
"""Assemble the gold set and render the review worksheet.

Writes:
  0.2/gold/multiagent_gold.csv   the label file: four strata, with the verdicts
  0.2/out/gold_review.html       a self-contained worksheet, opens from disk

Four strata:
  carried_over      every incident the index already held, taken whole rather
                    than sampled, and judged from the primary sources.
  aiid_csetv1       AIID's 5 `yes` and 1 `maybe` on the CSETv1 attribute
                    `Multiple AI Interaction`. Independent human annotators,
                    but a different concept from our Gate 1.
  queue_boundary    candidates that tripped the prefilter's keyword arm.
  queue_base_rate   candidates with no signal at all, as a control.

The boundary and base-rate rows were drawn as unscreened, not as negatives:
AIID applies no multi-agent label in the 2025-2026 window, so its silence
carries no information and each row needed a human verdict.

See 0.2/docs/gold_set.md for the sampling design, the review protocol and the
accuracy ceiling computed from this set.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import run as pipeline  # noqa: E402

TREE = Path(__file__).resolve().parents[1]
ROOT = TREE.parent
GOLD = TREE / "gold" / "multiagent_gold.csv"
# The id registry: every gold id ever issued, including rows since dropped, so a
# row restored or a dossier merged never changes anyone's id.
GOLD_IDS = TREE / "gold" / "gold_ids.csv"
TEMPLATE = TREE / "gold" / "gold_review_template.html"
OUT = TREE / "out" / "gold_review.html"

FIELDS = ["gold_id", "stratum", "source_id", "source_record_id", "dossier",
          "date", "title", "draw_note",
          "review_verdict", "review_gate1", "review_gate2_cooperated",
               "review_gate2_cooperation",
          "review_gate2_objectives", "review_failure_mode", "review_note",
          "multiplicity_role", "duplicate_of", "review_round",
          "reviewed_by", "reviewed_on"]


def narrative(dossier_meta, body, record):
    """What the reviewer reads. Prefer the dossier's prose, fall back to the record."""
    if body:
        out = {}
        for name in pipeline.SECTIONS:
            chunk = body.split(f"## {name}", 1)
            if len(chunk) < 2:
                continue
            text = chunk[1]
            for other in pipeline.SECTIONS:
                text = text.split(f"## {other}", 1)[0]
            text = text.strip()
            if text and not text.startswith("_pending"):
                out[name] = text
        if out:
            return out
    return {"What happened": record.get("text", "")}


REVIEW_COLS = ["review_verdict", "review_gate1", "review_gate2_cooperated",
               "review_gate2_cooperation",
               "review_gate2_objectives", "review_failure_mode", "review_note",
               "multiplicity_role", "duplicate_of", "review_round",
               "reviewed_by", "reviewed_on"]


def merged_verdicts(paths):
    """Verdicts from the worksheet's exported CSV, keyed by source record."""
    out = {}
    for path in paths:
        p = Path(path).expanduser()
        if not p.exists():
            sys.exit(f"no such file: {p}")
        for row in csv.DictReader(p.open(encoding="utf-8")):
            if not (row.get("review_verdict") or "").strip():
                continue
            key = (row.get("source_id"), row.get("source_record_id"))
            out[key] = {c: (row.get(c) or "") for c in REVIEW_COLS}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--merge", nargs="+", metavar="CSV",
                    help="exported gold_reviewed.csv to fold back in before rebuilding")
    args = ap.parse_args()

    records = pipeline.latest_records()
    rows = []

    # --- stratum 1: everything the index already held ---------------------
    for path in pipeline.all_dossiers():
        meta, body = pipeline.read_dossier(path)
        src = meta["sources"][0]
        key = (src["source_id"], str(src["record_id"]))
        rec = records.get(key, {})
        rows.append({
            "gold_id": "",
            "stratum": "carried_over",
            "source_id": src["source_id"],
            "source_record_id": src["record_id"],
            "dossier": meta["id"],
            "date": meta["occurrence_date"],
            "title": meta["title"],
            "_narrative": narrative(meta, body, rec),
            "_sources": meta.get("sources") or [],
            "_external": meta.get("external_labels") or [],
            "_url": src.get("url", ""),
            "_mit": "",
        })

    # --- stratum 2: AIID CSETv1 verdicts ----------------------------------
    for (sid, rid), rec in sorted(records.items(),
                                  key=lambda kv: (kv[0][0], kv[0][1])):
        if sid != "aiid":
            continue
        cse = [l for l in rec["external_labels"]
               if l.get("namespace") == "CSETv1"
               and str(l["value"]).lower() in ("yes", "maybe")]
        if not cse:
            continue
        rows.append({
            "gold_id": "",
            "stratum": "aiid_csetv1",
            "source_id": sid, "source_record_id": rid, "dossier": "",
            "date": rec["date"], "title": rec["title"],
            "_narrative": {"What happened": rec.get("text", "")},
            "_sources": [{"source_id": sid, "record_id": rid, "url": rec.get("url", "")}],
            "_external": rec["external_labels"],
            "_url": rec.get("url", ""),
            "_mit": rec["meta"].get("mit_subdomain", ""),
        })

    # --- strata 3 and 4: the drawn, unscreened candidates -----------------
    sample = TREE / "gold" / "negative_sample.csv"
    if not sample.exists():
        sys.exit(f"no {sample.relative_to(ROOT)}; run sample_negatives.py first")
    for s in csv.DictReader(sample.open(encoding="utf-8")):
        rec = records.get((s["source_id"], s["source_record_id"]), {})
        why = s.get("keyword_terms") or ""
        rows.append({
            "gold_id": "",
            "stratum": f'queue_{s.get("stratum", "base_rate")}',
            "source_id": s["source_id"],
            "source_record_id": s["source_record_id"],
            "dossier": "", "date": s["date"], "title": s["title"],
            "draw_note": (
                "AIID applies no multi-agent label in 2025-2026, so this is unscreened, "
                "not negative. Surfaced by the prefilter on: " + (s.get("arms") or s.get("flags") or "")
                + (f" ({why})" if why else "")),
            "_narrative": {"What happened": rec.get("text", "")},
            "_sources": [{"source_id": s["source_id"],
                          "record_id": s["source_record_id"], "url": s["url"]}],
            "_external": rec.get("external_labels", []),
            "_url": s["url"],
            "_mit": s.get("mit_subdomain", ""),
        })

    # --- rows retired from the set ----------------------------------------
    # 0.2/gold/dropped.csv records rows removed with a reason (duplicates, and
    # rows whose only source cannot be read). They are regenerated from the
    # dossiers on every run, so they have to be filtered out again here or they
    # would silently return to the set.
    dropped_path = TREE / "gold" / "dropped.csv"
    if dropped_path.exists():
        retired = {(r["source_id"], r["source_record_id"])
                   for r in csv.DictReader(dropped_path.open(encoding="utf-8"))}
        before = len(rows)
        rows = [r for r in rows
                if (r["source_id"], str(r["source_record_id"])) not in retired]
        if before != len(rows):
            print(f"  retired {before - len(rows)} row(s) per {dropped_path.name}")

    # --- the label file, verdicts blank -----------------------------------
    existing = {}
    ids = {}   # (source_id, source_record_id) -> gold_id, so an id never moves
    if GOLD_IDS.exists():
        for old in csv.DictReader(GOLD_IDS.open(encoding="utf-8")):
            ids[(old["source_id"], old["source_record_id"])] = old["gold_id"]
    if dropped_path.exists():
        for old in csv.DictReader(dropped_path.open(encoding="utf-8")):
            ids[(old["source_id"], old["source_record_id"])] = old["gold_id"]
    if GOLD.exists():
        for old in csv.DictReader(GOLD.open(encoding="utf-8")):
            ids[(old.get("source_id"), old.get("source_record_id"))] = old["gold_id"]
            if old.get("review_verdict"):
                existing[(old.get("source_id"), old.get("source_record_id"))] = old
    # A gold id is permanent. Ids used to be dealt out by position, so removing or
    # merging one dossier renumbered every row after it and silently broke every
    # reference to a gold id elsewhere. Known rows keep their id; new rows take the
    # next unused number.
    used = {int(g[2:]) for g in ids.values() if g}
    for r in rows:
        key = (r["source_id"], str(r["source_record_id"]))
        if key not in ids:
            n = max(used, default=0) + 1
            used.add(n)
            ids[key] = f"G-{n:03d}"
        r["gold_id"] = ids[key]
    rows.sort(key=lambda r: r["gold_id"])
    with GOLD_IDS.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["gold_id", "source_id", "source_record_id"])
        for (sid, rid), gid in sorted(ids.items(), key=lambda kv: kv[1]):
            w.writerow([gid, sid, rid])
    incoming = merged_verdicts(args.merge) if args.merge else {}
    existing.update(incoming)

    with GOLD.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            keep = existing.get((r["source_id"], r["source_record_id"]), {})
            for col in FIELDS:
                r.setdefault(col, "")
                if col in REVIEW_COLS:
                    r[col] = keep.get(col, "")
            w.writerow(r)

    # --- the worksheet ----------------------------------------------------
    payload = {
        "generated": pipeline.TODAY,
        "instances": [
            {"instance_id": i["instance_id"], "instance": i["instance"],
             "risk_id": i["risk_id"], "definition": i["definition"]}
            for i in pipeline.read_csv(TREE / "taxonomy" / "instances.csv")],
        "rows": [{k: v for k, v in r.items()
                  if not k.startswith("_") or k in
                  ("_narrative", "_sources", "_external", "_url", "_mit")}
                 for r in rows],
    }
    if not TEMPLATE.exists():
        sys.exit(f"no template at {TEMPLATE.relative_to(ROOT)}")
    html = TEMPLATE.read_text(encoding="utf-8")
    if "__DATA__" not in html:
        sys.exit("the __DATA__ placeholder is gone from the template")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html.replace("__DATA__", json.dumps(payload, ensure_ascii=False)),
                   encoding="utf-8")

    counts = {}
    for r in rows:
        counts[r["stratum"]] = counts.get(r["stratum"], 0) + 1
    print(f"{len(rows)} gold rows -> {GOLD.relative_to(ROOT)}")
    for k, v in sorted(counts.items()):
        print(f"  {v:3d}  {k}")
    if incoming:
        print(f"  merged {len(incoming)} verdict(s) from {', '.join(args.merge)}")
    if existing:
        done = {}
        for v in existing.values():
            done[v.get("review_verdict", "")] = done.get(v.get("review_verdict", ""), 0) + 1
        print(f"  {len(existing)} of {len(rows)} reviewed: "
              + ", ".join(f"{k or '(blank)'} {n}" for k, n in sorted(done.items())))
    print(f"worksheet -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
