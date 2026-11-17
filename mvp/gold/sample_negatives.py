#!/usr/bin/env python3
"""Draw the negative-candidate sample for the gold set, from the prefilter queue.

Pool: queued candidates dated 2025-2026 that AIID does **not** mark as
multi-agent, i.e. everything the prefilter surfaced on the keyword or
unclassified arm rather than on an external label.

These are *unscreened*, not labelled negative. In that window AIID applies no
multi-agent label at all - CSETv1 stops in 2024 - so the absence of one carries
no information. Every row is drawn as `to_judge` and becomes a negative only
when a human applies the two gates.

**The draw is deliberately hard, not representative.** Only ~12% of the pool
trips the keyword arm, so a proportional sample would be almost all
unclassified records with no multi-agent signal at all - easy negatives that
flatter precision. This oversamples the keyword arm instead, so the sample sits
on the decision boundary. The consequence is the opposite bias: precision
measured against it is *pessimistic*, and it describes the boundary rather than
the population. For a base-rate figure, draw with --hard 0.

    python mvp/gold/sample_negatives.py [--n 27] [--hard 18] [--seed 20261113]
"""
import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

MVP = Path(__file__).resolve().parents[1]
QUEUE = MVP / "state" / "queue.jsonl"
RECORDS = MVP / "records" / "aiid.jsonl"
OUT = MVP / "gold" / "negative_sample.csv"

YEARS = ("2025", "2026")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=27)
    ap.add_argument("--hard", type=int, default=18,
                    help="how many to draw from the keyword arm (default 18)")
    ap.add_argument("--seed", type=int, default=20261113)
    args = ap.parse_args()

    if not QUEUE.exists():
        sys.exit(f"no queue at {QUEUE}; run `run.py prefilter` first")
    queue = [json.loads(line) for line in QUEUE.open(encoding="utf-8") if line.strip()]
    records = {}
    if RECORDS.exists():
        for line in RECORDS.open(encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                records[r["source_record_id"]] = r

    pool = [r for r in queue
            if "label" not in r["flags"] and r["date"][:4] in YEARS]
    hard = [r for r in pool if "keyword" in r["flags"]]
    soft = [r for r in pool if "keyword" not in r["flags"]]
    if len(pool) < args.n:
        sys.exit(f"pool has only {len(pool)} candidates")
    n_hard = min(args.hard, len(hard))
    n_soft = args.n - n_hard
    if n_soft > len(soft):
        sys.exit(f"only {len(soft)} non-keyword candidates available")

    rng = random.Random(args.seed)
    hard.sort(key=lambda r: int(r["source_record_id"]))
    soft.sort(key=lambda r: int(r["source_record_id"]))
    picked = rng.sample(hard, n_hard) + rng.sample(soft, n_soft)
    picked.sort(key=lambda r: (r["date"], int(r["source_record_id"])))

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source_id", "source_record_id", "date", "title",
                    "mit_subdomain", "arms", "keyword_terms", "url", "stratum"])
        for r in picked:
            rec = records.get(r["source_record_id"], {})
            w.writerow([r["source_id"], r["source_record_id"], r["date"], r["title"],
                        rec.get("meta", {}).get("mit_subdomain", ""),
                        ";".join([r["basis"]] + [f for f in r["flags"].split(";") if f]),
                        r["keyword_terms"], r["url"],
                        "boundary" if "keyword" in r["flags"] else "base_rate"])

    print(f"pool: {len(pool)} queued candidates dated 2025-2026 that AIID does not "
          f"mark multi-agent")
    print(f"      {len(hard)} carry the keyword flag, {len(soft)} are queued without a flag")
    print(f"drew {len(picked)} with seed {args.seed} -> {OUT.relative_to(MVP.parent)}")
    print(f"  {n_hard:3d}  boundary   (keyword flag: something looked multi-agent)")
    print(f"  {n_soft:3d}  base_rate  (no signal at all; a control)")
    print(f"\nby year: {dict(sorted(Counter(r['date'][:4] for r in picked).items()))}")
    terms = Counter()
    for r in picked:
        for t in (r["keyword_terms"] or "").split(";"):
            if t:
                terms[t] += 1
    if terms:
        print("what tripped the keyword arm:")
        for t, c in terms.most_common():
            print(f"  {c:3d}  {t}")
    print("\nAll drawn rows are `to_judge`. None is evidence of a negative until judged.")
    print("The draw is deliberately hard, so precision measured against it is")
    print("pessimistic and describes the decision boundary, not the population.")


if __name__ == "__main__":
    main()
