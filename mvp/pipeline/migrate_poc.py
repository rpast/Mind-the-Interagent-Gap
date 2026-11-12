#!/usr/bin/env python3
"""One-off: carry the PoC's 27 verified incidents into the mvp store.

Their narratives and verification verdicts are real research effort, so they
are migrated rather than rebuilt. Two things are written:

  mvp/records/<source>.jsonl   the PoC row as a source record, so every dossier
                               has a provenance chain the pipeline can check
  mvp/incidents/MIG-nnnn.md    the curated dossier

Nothing is invented. Fields the PoC never captured - the mechanism, the
response, how many agents, what kind of interaction - are written as pending or
'unclear', so the gaps stay visible instead of being filled with guesses.

Run once, from the repository root. It refuses to overwrite existing dossiers.
"""
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as pipeline  # noqa: E402  the pipeline owns the dossier format

ROOT = Path(__file__).resolve().parents[2]
POC = ROOT / "poc" / "data"

# event_id prefix -> the registry source that attests it
PREFIX_SOURCE = {"AIR": "air_enkrypt", "LW": "lesswrong", "AIV": "aivillage"}

TYPE_MAP = {
    "Observed in real world": "real_world",
    "Synthetic evidence": "synthetic",
    "Observed in lab": "lab",
    "Theoretical": "theoretical",
}

PENDING = "_pending — not captured in the PoC row_"


def short_title(text):
    """A name, not a sentence. Returns (title, was_truncated)."""
    text = re.sub(r"\s+", " ", text).strip()
    head = text.split(":", 1)[0].strip()
    if 10 <= len(head) <= 90 and head != text:
        return head, False
    if len(text) <= 80:
        return text, False
    cut = text[:80].rsplit(" ", 1)[0].rstrip(",;.")
    return cut, True


def verification_of(notes):
    low = notes.lower()
    if low.startswith("partially verified"):
        return "partially_verified"
    if low.startswith("verified"):
        return "verified"
    return "unverified"


def main():
    incidents = list(csv.DictReader(open(POC / "incidents.csv", encoding="utf-8")))
    extra_sources = {}
    for row in csv.DictReader(open(POC / "sources.csv", encoding="utf-8")):
        extra_sources.setdefault(row["event_id"], []).append(row)

    aiid_titles = {}
    for rec in pipeline.read_jsonl(pipeline.RECORDS / "aiid.jsonl"):
        aiid_titles.setdefault(rec["source_record_id"], rec.get("title", ""))

    incidents.sort(key=lambda r: (r["date"], r["event_id"]))

    records = {}
    truncated, made, near = [], [], []

    for n, row in enumerate(incidents, 1):
        event_id = row["event_id"]
        prefix = event_id.split("-")[0]
        source_id = PREFIX_SOURCE.get(prefix)
        if source_id is None:
            sys.exit(f"no registry source for the {prefix}- prefix ({event_id})")

        ok, precision = pipeline.parse_iso(row["date"])
        if not ok:
            sys.exit(f"{event_id}: date {row['date']!r} is not ISO")

        title, was_cut = short_title(row["incident"])
        if was_cut:
            truncated.append(event_id)

        # the PoC row, recorded as what it is: a source record captured on
        # retrieved_on, which is where its fetch date honestly comes from
        body = {
            "title": title,
            "text": row["incident"],
            "date": row["date"],
            "url": row["source_url"],
            "external_labels": [],
            "meta": {"poc_event_id": event_id,
                     "poc_source_class": row["source_class"],
                     "poc_system": row["system"]},
        }
        records.setdefault(source_id, []).append({
            "source_id": source_id,
            "source_record_id": event_id,
            "fetched_at": row["retrieved_on"],
            "content_hash": pipeline.content_hash(body),
            **body,
        })

        fms = [x for x in row["failure_modes"].split(";") if x]
        if len(fms) > 1:
            sys.exit(f"{event_id}: more than one failure mode {fms}; the dossier holds one")

        doc_id = f"MIG-{n:04d}"
        path = pipeline.dossier_path(doc_id)
        if path.exists():
            sys.exit(f"{path} exists; delete mvp/incidents/ if you mean to re-migrate")

        sources = [{"source_id": source_id, "record_id": event_id,
                    "url": row["source_url"], "first_seen": row["retrieved_on"]}]

        meta = {
            "id": doc_id,
            "title": title,
            "canonical_source": source_id,
            "sources": sources,
            "occurrence_date": row["date"],
            "occurrence_date_precision": precision,
            "first_seen": row["retrieved_on"],
            "last_verified": row["retrieved_on"],
            "systems": [row["system"]] if row["system"] else [],
            "actor_count": "unclear",
            "interaction_kind": "unclear",
            "evidence_type": TYPE_MAP[row["type"]],
            "multi_agent": True,
            "multi_agent_basis": (
                "Inherited from the PoC inventory, which applied the same inclusion test: "
                "the behaviour arises from interaction between two or more AI agents."),
            "multi_agent_label_source": "ours",
            "external_labels": [],
            "failure_mode": fms[0] if fms else None,
            "failure_mode_source": "ours" if fms else "",
            "instances": [x for x in row["instances"].split(";") if x],
            "verification": verification_of(row["notes"]),
            "legacy_id": event_id,
        }

        source_lines = [f"- Primary: [{row['source']}]({row['source_url']}) "
                        f"— {row['source_class']}, retrieved {row['retrieved_on']}"]
        for s in extra_sources.get(event_id, []):
            source_lines.append(f"- [{s['title']}]({s['url']}) — {s['source_type']}")

        agents = row["system"] or PENDING
        if row.get("system_basis"):
            agents += f"\n\nSystem basis: {row['system_basis']}."
        agents += ("\n\nHow many agents there were, and what kind of interaction took "
                   "place, are not recorded in the PoC row. `actor_count` and "
                   "`interaction_kind` are `unclear` until someone reads the primary "
                   "source.")

        sections = {
            "Context": PENDING,
            "What happened": row["incident"],
            "Mechanism": PENDING,
            "Agents and interaction": agents,
            "Response": PENDING,
            "Verification notes": row["notes"] or PENDING,
            "Sources": "\n".join(source_lines),
        }
        pipeline.write_dossier(path, meta, sections)
        made.append(doc_id)

        # AIID attestation is not auto-linked: a wrong merge is worse than a
        # missing one. Report close title matches for a human to confirm.
        for aiid_id, aiid_title in aiid_titles.items():
            if title_overlap(title, aiid_title) >= 0.6:
                near.append(f"{doc_id} ({event_id}) ~ AIID {aiid_id}: {aiid_title}")

    for source_id, rows in records.items():
        pipeline.append_records(source_id, rows)

    print(f"migrated {len(made)} dossiers: {made[0]}..{made[-1]}")
    if truncated:
        print(f"{len(truncated)} title(s) truncated from a long summary sentence and "
              f"should be renamed by hand: {', '.join(truncated)}")
    if near:
        print(f"\n{len(near)} possible AIID attestation(s) to confirm by hand "
              f"(not linked automatically):")
        for line in near:
            print("  " + line)
    else:
        print("no close AIID title matches; none of the 27 is linked to an AIID record yet")


def title_overlap(a, b):
    """Jaccard over lowercased word sets, ignoring very common words."""
    stop = {"the", "a", "an", "of", "to", "and", "in", "on", "for", "with", "by",
            "ai", "agents", "agent"}
    wa = {w for w in re.findall(r"[a-z0-9]+", a.lower()) if w not in stop}
    wb = {w for w in re.findall(r"[a-z0-9]+", b.lower()) if w not in stop}
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


if __name__ == "__main__":
    main()
