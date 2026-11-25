"""Duplicate proposals: is a record an incident the index already holds? Rules only.

0.2/docs/plan.md, 3.8. For a record, `propose` names the existing incident it most likely
reports, or `new`, with the evidence. It never decides: a person confirms `duplicate_of`
on the records sheet.

The evidence, strongest first:

  url      the record's url is the url of a record the incident already has
  text     the record's title and text are close to the incident's (TF-IDF cosine over
           every loaded record, so rare names - RubyGems, Vanderbilt - weigh most)
  date     the event dates are close; it only strengthens a text match, never makes one

Thresholds are set on the incidents the curator merged by hand (`measure`).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date

TEXT_CHARS = 2000         # how much of a record's text is compared
STRONG = 0.30             # cosine that names a duplicate on its own
WITH_DATE = 0.15          # cosine that names one when the dates are close
NEAR_DAYS = 14            # how close "close" is
# Measured 2026-11-25 on the curator's merges (5 incidents, 12 records): every record
# found at these settings; a 7-day window loses two. Of 64 records that are not merged,
# 10 were proposed as duplicates: one a true duplicate never merged (aiid:1556 of
# MIG-0015), two the Moltbook pair MIG-0012 / MIG-0013, seven different incidents that
# share names. A person confirms every proposal, so a false alarm costs a look; a miss
# costs a second dossier for one incident. Recall is chosen over precision.
STOP = set("""a an and are as at be been but by for from has have he her his in into is
it its of on or our over she that the their them they this to was were which while who
will with without after before about also than then there these those not no can could
would should may might reportedly allegedly reported according said says""".split())


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9\-]+", text.lower())
            if t not in STOP and len(t) > 2 and not t.isdigit()]


def doc_text(rec: dict) -> str:
    return f"{rec.get('title', '')} {rec.get('title', '')} {(rec.get('text') or '')[:TEXT_CHARS]}"


class Index:
    """TF-IDF vectors of every loaded record (the idf comes from all of them)."""

    def __init__(self, records: dict):
        self.tf = {k: Counter(tokens(doc_text(r))) for k, r in records.items()}
        df = Counter()
        for c in self.tf.values():
            df.update(c.keys())
        n = max(len(self.tf), 1)
        self.idf = {t: math.log(n / (1 + d)) + 1 for t, d in df.items()}
        self.vec = {k: self._vector(c) for k, c in self.tf.items()}

    def _vector(self, counts: Counter) -> dict:
        v = {t: (1 + math.log(c)) * self.idf.get(t, 1.0) for t, c in counts.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def cosine(self, a, b) -> float:
        va, vb = self.vec.get(a, {}), self.vec.get(b, {})
        if len(va) > len(vb):
            va, vb = vb, va
        return sum(x * vb.get(t, 0.0) for t, x in va.items())


def days_apart(a: str, b: str):
    def parse(s):
        s = str(s or "")
        parts = s.split("-")
        try:
            return date(int(parts[0]), int(parts[1]) if len(parts) > 1 else 7,
                        int(parts[2]) if len(parts) > 2 else 1)
        except (ValueError, IndexError):
            return None
    x, y = parse(a), parse(b)
    return abs((x - y).days) if x and y else None


def norm_url(u: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", str(u or "")).rstrip("/").lower()


def propose(key: str, rec: dict, incidents: dict, records: dict, index: Index):
    """(duplicate_of, why, score) for one record. `incidents` is
    {incident_key: [record_key, ...]}, the records each incident already has; the
    record itself is left out of every incident."""
    url = norm_url(rec.get("url"))
    best = ("new", "no existing incident is close", 0.0)
    for inc, members in incidents.items():
        members = [m for m in members if m != key]
        if not members:
            continue
        if url and any(norm_url(records[m].get("url")) == url for m in members):
            return inc, f"same url as {inc}", 1.0
        score, near, via = 0.0, None, None
        for m in members:
            s = index.cosine(key, m)
            if s > score:
                score, via = s, m
                near = days_apart(rec.get("date"), records[m].get("date"))
        close = near is not None and near <= NEAR_DAYS
        if score >= STRONG or (score >= WITH_DATE and close):
            if score > best[2]:
                when = f", dates {near} days apart" if near is not None else ""
                best = (inc, f"text close to {inc} (cosine {score:.2f} with {via}{when})",
                        score)
    return best


def measure(records: dict, incidents: dict, index: Index, others: list):
    """Leave-one-out on the curator's merges: every record of a multi-record incident,
    taken out, should be proposed as that incident. `others`: records that are not
    duplicates (each single-record incident's own record, and records proposed in that
    have no incident); each should come out `new`, or it is a false alarm.
    Returns (hits, misses, false_alarms), each a list of (key, proposal, why)."""
    hits, misses, alarms = [], [], []
    for inc, members in incidents.items():
        if len(members) < 2:
            continue
        for m in members:
            got, why, _ = propose(m, records[m], incidents, records, index)
            (hits if got == inc else misses).append((m, inc, got, why))
    for k in others:
        got, why, _ = propose(k, records[k], incidents, records, index)
        if got != "new":
            alarms.append((k, got, why))
    return hits, misses, alarms
