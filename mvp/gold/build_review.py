#!/usr/bin/env python3
"""Assemble the gold set and render the review worksheet.

Writes:
  mvp/gold/multiagent_gold.csv   the label file: three strata, verdicts blank
  mvp/out/gold_review.html       a self-contained worksheet, opens from disk

Three strata:
  poc_positive      the 27 migrated incidents. Labelled multi_agent by the PoC,
                    which was AI-assisted throughout and never independently
                    reviewed. Being re-verified from the primary sources.
  aiid_csetv1       AIID's 5 `yes` and 1 `maybe` on the CSETv1 attribute
                    `Multiple AI Interaction`. Independent human annotators,
                    but a different concept from our Gate 1.
  aiid_unlabelled   27 drawn from AIID 2025-2026 records that AIID does not
                    mark multi-agent. Unscreened, not negative: AIID applies no
                    multi-agent label in that window.

Every row is to_judge. The worksheet hides the prior label behind a toggle so a
verdict is formed before the earlier pass is seen.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import run as pipeline  # noqa: E402

MVP = Path(__file__).resolve().parents[1]
ROOT = MVP.parent
GOLD = MVP / "gold" / "multiagent_gold.csv"
TEMPLATE = MVP / "gold" / "gold_review_template.html"
OUT = MVP / "out" / "gold_review.html"

FIELDS = ["gold_id", "stratum", "source_id", "source_record_id", "dossier",
          "date", "title", "prior_multi_agent", "prior_failure_mode",
          "prior_instances", "prior_basis", "prior_verification",
          "review_verdict", "review_gate1", "review_gate2_cooperation",
          "review_gate2_objectives", "review_failure_mode", "review_note",
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


REVIEW_COLS = ["review_verdict", "review_gate1", "review_gate2_cooperation",
               "review_gate2_objectives", "review_failure_mode", "review_note",
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

    # --- stratum 1: the 27 migrated positives -----------------------------
    for path in pipeline.all_dossiers():
        meta, body = pipeline.read_dossier(path)
        src = meta["sources"][0]
        key = (src["source_id"], str(src["record_id"]))
        rec = records.get(key, {})
        rows.append({
            "gold_id": f"G-{len(rows) + 1:03d}",
            "stratum": "poc_positive",
            "source_id": src["source_id"],
            "source_record_id": src["record_id"],
            "dossier": meta["id"],
            "date": meta["occurrence_date"],
            "title": meta["title"],
            "prior_multi_agent": "true",
            "prior_failure_mode": meta.get("failure_mode") or "",
            "prior_instances": ";".join(meta.get("instances") or []),
            "prior_basis": meta.get("multi_agent_basis", ""),
            "prior_verification": meta.get("verification", ""),
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
            "gold_id": f"G-{len(rows) + 1:03d}",
            "stratum": "aiid_csetv1",
            "source_id": sid, "source_record_id": rid, "dossier": "",
            "date": rec["date"], "title": rec["title"],
            "prior_multi_agent": f'csetv1={str(cse[0]["value"]).lower()}',
            "prior_failure_mode": "", "prior_instances": "",
            "prior_basis": "AIID CSETv1 annotators; a different concept from Gate 1",
            "prior_verification": "",
            "_narrative": {"What happened": rec.get("text", "")},
            "_sources": [{"source_id": sid, "record_id": rid, "url": rec.get("url", "")}],
            "_external": rec["external_labels"],
            "_url": rec.get("url", ""),
            "_mit": rec["meta"].get("mit_subdomain", ""),
        })

    # --- stratum 3: the drawn negative candidates -------------------------
    sample = MVP / "gold" / "negative_sample.csv"
    if not sample.exists():
        sys.exit(f"no {sample.relative_to(ROOT)}; run sample_negatives.py first")
    for s in csv.DictReader(sample.open(encoding="utf-8")):
        rec = records.get((s["source_id"], s["source_record_id"]), {})
        why = s.get("keyword_terms") or ""
        rows.append({
            "gold_id": f"G-{len(rows) + 1:03d}",
            "stratum": f'queue_{s.get("stratum", "base_rate")}',
            "source_id": s["source_id"],
            "source_record_id": s["source_record_id"],
            "dossier": "", "date": s["date"], "title": s["title"],
            "prior_multi_agent": "",
            "prior_failure_mode": "", "prior_instances": "",
            "prior_basis": (
                "AIID applies no multi-agent label in 2025-2026, so this is unscreened, "
                "not negative. Surfaced by the prefilter on: " + (s.get("arms") or "")
                + (f" ({why})" if why else "")),
            "prior_verification": "",
            "_narrative": {"What happened": rec.get("text", "")},
            "_sources": [{"source_id": s["source_id"],
                          "record_id": s["source_record_id"], "url": s["url"]}],
            "_external": rec.get("external_labels", []),
            "_url": s["url"],
            "_mit": s.get("mit_subdomain", ""),
        })

    # --- the label file, verdicts blank -----------------------------------
    existing = {}
    if GOLD.exists():
        for old in csv.DictReader(GOLD.open(encoding="utf-8")):
            if old.get("review_verdict"):
                existing[(old.get("source_id"), old.get("source_record_id"))] = old
    incoming = merged_verdicts(args.merge) if args.merge else {}
    existing.update(incoming)

    with GOLD.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            keep = existing.get((r["source_id"], r["source_record_id"]), {})
            for col in FIELDS:
                r.setdefault(col, "")
                if col.startswith("review") or col == "reviewed_by" or col == "reviewed_on":
                    r[col] = keep.get(col, "")
            w.writerow(r)

    # --- the worksheet ----------------------------------------------------
    payload = {
        "generated": pipeline.TODAY,
        "instances": [
            {"instance_id": i["instance_id"], "instance": i["instance"],
             "risk_id": i["risk_id"], "definition": i["definition"]}
            for i in pipeline.read_csv(MVP / "taxonomy" / "instances.csv")],
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
