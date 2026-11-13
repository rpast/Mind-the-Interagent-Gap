#!/usr/bin/env python3
"""Score Gate 1 against the reviewed gold set.

Truth is the human review verdict in mvp/gold/multiagent_gold.csv. Rows judged
`unclear` are excluded: with no ground truth there is nothing to score against.

The accuracy ceiling is the precision of the index's own earlier hand-curation,
measured against that review. Those earlier assertions are not held in the live
gold set - they sit in mvp/gold/archive/, so they cannot be seen by a later
reviewer and contaminate the verdicts - so this script reads them from there.

Methodology, and how to read the numbers: mvp/docs/gold_set.md
Latest figures:                          mvp/docs/gate1_accuracy.md

Usage:  python mvp/gold/score_gate1.py [--json PATH]
"""
import argparse
import collections
import csv
import json
from pathlib import Path

MVP = Path(__file__).resolve().parents[1]
GOLD = MVP / "gold" / "multiagent_gold.csv"
ARCHIVE = MVP / "gold" / "archive" / "ceiling_input_multiagent_gold_20261113.csv"
QUEUE = MVP / "state" / "queue.jsonl"


def score(pairs, name, note="", only_precision=False):
    """pairs: (predicted_in_scope, truly_in_scope)."""
    tp = sum(1 for p, t in pairs if p and t)
    fp = sum(1 for p, t in pairs if p and not t)
    fn = sum(1 for p, t in pairs if not p and t)
    tn = sum(1 for p, t in pairs if not p and not t)
    n = len(pairs)
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    acc = (tp + tn) / n if n else None
    f1 = (2 * prec * rec / (prec + rec)) if prec and rec else None

    def pct(x):
        return "   n/a" if x is None else f"{x:6.1%}"

    print(f"\n{name}")
    if note:
        print(f"  {note}")
    print(f"  n={n:3}   TP={tp:3} FP={fp:3} FN={fn:3} TN={tn:3}")
    if only_precision:
        print(f"  precision {pct(prec)}")
        print("  recall, accuracy and F1 are omitted: this stratum holds only asserted")
        print("  positives, so there is nothing to have missed and nothing to reject.")
    else:
        print(f"  precision {pct(prec)}   recall {pct(rec)}   "
              f"accuracy {pct(acc)}   F1 {pct(f1)}")
    return dict(n=n, tp=tp, fp=fp, fn=fn, tn=tn,
                precision=prec, recall=rec, accuracy=acc, f1=f1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(MVP / "out" / "gate1_accuracy.json"))
    args = ap.parse_args()

    gold = list(csv.DictReader(GOLD.open(encoding="utf-8")))
    scorable = [r for r in gold if r["review_verdict"] in ("in", "out")]
    unclear = [r for r in gold if r["review_verdict"] == "unclear"]
    truth = {r["gold_id"]: r["review_verdict"] == "in" for r in scorable}

    print("=" * 72)
    print("GATE 1 ACCURACY")
    print("=" * 72)
    print(f"\nGold rows: {len(gold)}   scorable: {len(scorable)}   "
          f"excluded as unclear: {len(unclear)} "
          f"({', '.join(r['gold_id'] for r in unclear)})")
    print("Truth:", dict(collections.Counter(r["review_verdict"] for r in gold)))

    proposals = MVP / "proposals"
    if not proposals.exists():
        print("\nNOTE: mvp/proposals/ does not exist. The classifier has not been run,")
        print("so its accuracy cannot be computed. What follows scores the predictors")
        print("that do exist, which are what the classifier has to beat.")

    out = {}

    # --- the ceiling: the index's own earlier hand-curation -----------------
    if ARCHIVE.exists():
        prior = {r["gold_id"]: r for r in csv.DictReader(ARCHIVE.open(encoding="utf-8"))}
        pairs = [(True, truth[g]) for g, r in prior.items()
                 if g in truth and r["prior_multi_agent"] == "true"]
        out["ceiling_hand_curation"] = score(
            pairs, "1. CEILING - the index's own earlier hand-curation",
            "Every row was added to the index as a multi-agent incident, then re-decided "
            "from the primary sources.", only_precision=True)
    else:
        print(f"\n1. CEILING - skipped, no {ARCHIVE.name}")

    # --- an outside human rater --------------------------------------------
    sub = [r for r in scorable if r["stratum"] == "aiid_csetv1"]
    out["aiid_csetv1"] = score(
        [(True, truth[r["gold_id"]]) for r in sub],
        "2. AIID CSETv1 'Multiple AI Interaction' - independent human annotators",
        "All were yes/maybe, so again a precision-only test on their positives.",
        only_precision=True)

    # --- the keyword prefilter arm -----------------------------------------
    queue = {(r["source_id"], str(r["source_record_id"])): r
             for r in (json.loads(l) for l in QUEUE.open(encoding="utf-8"))}
    pairs, missing = [], []
    for r in scorable:
        q = queue.get((r["source_id"], str(r["source_record_id"])))
        if q is None:
            missing.append(r["gold_id"])
            continue
        arms = [a for a in (q.get("arms") or "").split(";") if a]
        pairs.append(("keyword" in arms, truth[r["gold_id"]]))
    out["keyword_arm"] = score(
        pairs, "3. Keyword prefilter arm",
        "DO NOT QUOTE THESE. Every queue_boundary row tripped this arm by definition, "
        "so the predictor is the sampling frame and its precision here is just that "
        f"stratum's base rate. {len(missing)} scorable rows have no queue row at all.")

    print("\n" + "=" * 72)
    print("Read mvp/docs/gold_set.md before quoting any of these.")
    Path(args.json).write_text(json.dumps(
        {"gold_rows": len(gold), "scorable": len(scorable),
         "excluded_unclear": [r["gold_id"] for r in unclear],
         "classifier_run": proposals.exists(), "predictors": out}, indent=2))
    print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
