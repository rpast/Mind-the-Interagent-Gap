#!/usr/bin/env python3
"""Seed mvp/context/ from the gold-set source context. One-off, kept for provenance.

mvp/gold/context/ holds what the gold reviewer judged from: 41 rows of source
facts written on 2026-11-13. It stays frozen as that audit record. This script
copies those rows into the live context layer, mvp/context/<source_id>.jsonl, in
the schema `run.py readiness` reads, so the layer does not start empty.

Three things are set here by hand rather than derived, and are listed below so
they can be checked: how many AI agents each source describes, how deeply each
source was read, and whether the record describes an attack.

See mvp/docs/context_layer.md.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as pipeline  # noqa: E402

MVP = Path(__file__).resolve().parents[1]
SRC = MVP / "gold" / "context"

# gold field -> context fact
FACT_KEYS = {"agents": "agents", "interaction": "interaction",
             "multiplicity": "multiplicity", "setting": "setting",
             "coop": "cooperation", "obj": "objectives", "mechanism": "mechanism"}

SILENT = re.compile(
    r"^\W*(not stated|none stated|not mentioned|not addressed|not established|"
    r"not counted|unreported|unknown|no evidence)", re.I)
NOT_APPLICABLE = re.compile(r"^\W*not applicable", re.I)

# How many AI agents the source describes. Read off each row's `agents` text.
AGENT_COUNT = {
    "none": {"G-013"},
    "one": {"G-029", "G-032", "G-048"},
    "unknown": {"G-002", "G-005", "G-022", "G-028", "G-060"},
}

# How deeply the source was read. The default per source is below; these rows
# differ, each for the reason given.
DEPTH_OVERRIDE = {
    "G-022": ("unreadable", "2026-11-13"),       # Reuters refuses automated fetches
    "G-020": ("primary_full", "2026-11-14"),     # OpenAI report, all 38 pages
    "G-018": ("primary_partial", "2026-11-14"),  # researcher's page, first 85 per cent
    "G-049": ("primary_partial", "2026-11-14"),  # same page, via the AIID record
    "G-016": ("primary_full", "2026-11-14"),     # collusion.wiki read in full
    "G-024": ("primary_full", "2026-11-14"),     # OpenAI report, all 38 pages; Nextgov
}
DEPTH_DEFAULT = {
    "aivillage": "primary_full",   # the operator's own write-ups
    "lesswrong": "primary_full",   # the linked primary document
    "air_enkrypt": "secondary",    # the registry entry, not what it cites
    "aiid": "secondary",           # the incident page and report teasers only
}


def fact(text):
    if text is None:
        return {"status": "unread", "text": "", "quote": ""}
    if NOT_APPLICABLE.match(text):
        return {"status": "not_applicable", "text": text, "quote": ""}
    if SILENT.match(text):
        return {"status": "not_stated", "text": text, "quote": ""}
    return {"status": "stated", "text": text, "quote": ""}


def main():
    out = {}
    for path in sorted(SRC.glob("*.jsonl")):
        for row in pipeline.read_jsonl(path):
            sid, rid = row["rec"].split(":", 1)
            gid = row["gold_id"]
            facts = {new: fact(row.get(old)) for old, new in FACT_KEYS.items()}
            count = next((k for k, ids in AGENT_COUNT.items() if gid in ids), "several")
            if count in ("none", "one"):
                facts["agents"]["status"] = "stated"
            depth, read_on = DEPTH_OVERRIDE.get(gid, (DEPTH_DEFAULT[sid], "2026-11-13"))
            mult = facts["multiplicity"]["status"]
            out.setdefault(sid, []).append({
                "source_id": sid,
                "source_record_id": rid,
                "agent_count": count,
                "attack": mult in ("stated", "not_stated"),
                "read": [{"url": row.get("url") or row.get("primary") or "",
                          "depth": depth, "read_on": read_on}],
                "facts": facts,
                "quote": row.get("quote", ""),
                "provenance": {"method": "seeded:gold/context", "model": "",
                               "run_date": "2026-11-13", "gold_id": gid},
            })
    for sid, rows in out.items():
        rows.sort(key=lambda r: r["source_record_id"])
        pipeline.write_jsonl(pipeline.CONTEXT / f"{sid}.jsonl", rows)
        print(f"  {sid}: {len(rows)} context rows")


if __name__ == "__main__":
    main()
