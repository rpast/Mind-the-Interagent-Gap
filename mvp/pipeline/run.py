#!/usr/bin/env python3
"""The input-layer update routine.

Stages, in the order they run:

    fetch      pull a source into mvp/raw/<source>/, verbatim
    normalise  raw -> mvp/records/<source>.jsonl, append-only, content-hashed
    discover   search non-AIID sources for incidents AIID does not have
    prefilter  screen records into a candidate queue, recall first
    classify   (claude code skill; see mvp/docs/classifiers.md)
    promote    scaffold a dossier from a record
    index      regenerate mvp/out/incident_index.csv and mvp/state/pipeline.json
    viz        render mvp/out/input_workflow.html
    check      validate the layer; exits non-zero on any problem

`update` runs the ones a mode calls for. Each stage is also runnable alone.

AIID is the baseline source: it is fetched in every mode. Everything else is a
discovery source, searched for what AIID does not carry.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("this pipeline needs PyYAML: pip install -r requirements.txt")

MVP = Path(__file__).resolve().parents[1]
ROOT = MVP.parent

REGISTRY = MVP / "registry" / "sources.csv"
TAXONOMY = MVP / "taxonomy"
RAW = MVP / "raw"
RECORDS = MVP / "records"
INCIDENTS = MVP / "incidents"
PROPOSALS = MVP / "proposals"
STATE = MVP / "state"
OUT = MVP / "out"

TODAY = date.today().isoformat()

MODES = {
    # mode -> which stages run
    "labelled-only": ["fetch", "normalise", "prefilter", "index", "viz"],
    "aiid-full": ["fetch", "normalise", "prefilter", "queue", "index", "viz"],
    "all-sources": ["fetch", "normalise", "discover", "prefilter", "queue",
                    "index", "viz"],
}

EVIDENCE_TYPES = ["real_world", "synthetic", "lab", "theoretical"]
INTERACTION_KINDS = ["communication", "one-acting-on-another",
                     "shared-environment", "none", "unclear"]
VERIFICATION = ["verified", "partially_verified", "unverified"]
DATE_PRECISION = ["day", "month", "year"]

SECTIONS = ["Context", "What happened", "Mechanism", "Agents and interaction",
            "Response", "Verification notes", "Sources"]

REQUIRED_KEYS = [
    "id", "title", "canonical_source", "sources", "occurrence_date",
    "occurrence_date_precision", "first_seen", "last_verified", "systems",
    "actor_count", "interaction_kind", "evidence_type", "multi_agent",
    "multi_agent_basis", "multi_agent_label_source", "external_labels",
    "failure_mode", "failure_mode_source", "instances", "verification",
]

# The keyword net, lifted verbatim from notebooks/explore_aiid.ipynb section 8
# so the regex has exactly one home. Recall first: this is a net, not a
# classifier, and every hit still needs verifying against the primary source.
KEYWORD_TERMS = [
    r"multi-?agent",
    r"agent[- ]to[- ]agent",
    r"\bagents\b",
    r"collusion|collude|colluding",
    r"coordinat(?:e|ion|ing)",
    r"negotiat(?:e|ion|ing)",
    r"bot[- ]to[- ]bot",
    r"swarm",
    r"prompt injection",
    r"trading algorithm|algorithmic trading|flash crash",
    r"price[- ]fixing|pricing algorithm",
]
KEYWORD_RE = [(t, re.compile(t, re.I)) for t in KEYWORD_TERMS]

# A record with no external classification at all is unscreened, not negative.
# Recent records are the ones that lack classifications, so they go to the queue.
UNCLASSIFIED_CUTOFF = "2024-01-01"

MA_FIELD = "Multiple AI Interaction"
MA_POSITIVE = {"yes", "maybe"}


# --------------------------------------------------------------------- utils

def die(msg):
    sys.exit(f"error: {msg}")


def info(msg):
    print(msg, file=sys.stderr)


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def registry():
    if not REGISTRY.exists():
        die(f"no source registry at {REGISTRY}")
    return {r["source_id"]: r for r in read_csv(REGISTRY)}


def content_hash(obj):
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()[:32]


def read_jsonl(path):
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                die(f"{path}:{n}: {e}")
    return rows


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def latest_records(source_id=None):
    """Newest version of every record, keyed (source_id, source_record_id)."""
    out = {}
    paths = sorted(RECORDS.glob("*.jsonl")) if source_id is None \
        else [RECORDS / f"{source_id}.jsonl"]
    for path in paths:
        for row in read_jsonl(path):
            out[(row["source_id"], row["source_record_id"])] = row
    return out


def parse_iso(value):
    """Accept YYYY, YYYY-MM or YYYY-MM-DD. Return (ok, precision)."""
    text = str(value)
    for fmt, precision in (("%Y-%m-%d", "day"), ("%Y-%m", "month"), ("%Y", "year")):
        try:
            datetime.strptime(text, fmt)
            return True, precision
        except ValueError:
            continue
    return False, None


# ----------------------------------------------------------------- dossiers

def dossier_path(doc_id):
    return INCIDENTS / f"{doc_id}.md"


def read_dossier(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        die(f"{path}: no YAML frontmatter")
    _, fm, body = text.split("---\n", 2)
    try:
        meta = yaml.safe_load(fm) or {}
    except yaml.YAMLError as e:
        die(f"{path}: frontmatter is not valid YAML: {e}")
    return meta, body


def write_dossier(path, meta, sections):
    ordered = {k: meta[k] for k in REQUIRED_KEYS if k in meta}
    ordered.update({k: v for k, v in meta.items() if k not in ordered})
    fm = yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True,
                        default_flow_style=False, width=88)
    parts = [f"---\n{fm}---\n"]
    for name in SECTIONS:
        parts.append(f"\n## {name}\n\n{sections.get(name, '').rstrip()}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(parts), encoding="utf-8")


def all_dossiers():
    return sorted(INCIDENTS.glob("*.md")) if INCIDENTS.exists() else []


# -------------------------------------------------------------------- fetch

def stage_fetch(source_ids, force=False, token_file=None):
    reg = registry()
    done, skipped, orders = [], [], []
    for sid in source_ids:
        row = reg.get(sid)
        if row is None:
            die(f"unknown source_id {sid!r}; it must be a row in {REGISTRY}")
        method, adapter = row["access_method"], row["adapter"]
        target = RAW / sid
        if method == "read_only":
            skipped.append(f"{sid}: reference source, nothing to fetch")
            continue
        if adapter == "work_order":
            orders.append(work_order(row))
            continue
        if method == "graphql" and adapter == "aiid":
            if target.exists() and not force:
                n = len(read_jsonl(target / "incidents.jsonl"))
                skipped.append(f"{sid}: snapshot present ({n} records); --force to refetch")
                continue
            fetch_aiid(target, token_file)
            done.append(sid)
        else:
            orders.append(work_order(row))
    for line in skipped:
        info(f"  skip  {line}")
    for line in done:
        info(f"  ok    {line}: fetched")
    if orders:
        STATE.mkdir(parents=True, exist_ok=True)
        path = STATE / "work_orders.md"
        path.write_text("\n".join(orders), encoding="utf-8")
        info(f"  note  {len(orders)} source(s) need a human: {path}")
    return done


def work_order(row):
    """A source a script cannot reach is a stage, not a gap: say what to do."""
    return (
        f"## {row['name']} (`{row['source_id']}`)\n\n"
        f"- URL: {row['url']}\n"
        f"- Access: {row['access_method']} — a script cannot reach this.\n"
        f"- Last fetched: {row['last_fetched'] or 'never'}\n"
        f"- Reuse: {row['reuse_status']}\n"
        f"- Multi-agent label: {row['external_ma_label']}"
        f"{' at ' + row['external_ma_field'] if row['external_ma_field'] else ''}\n"
        f"- Caveat: {row['caveat']}\n\n"
        f"**To do:** open the URL, find incidents involving two or more AI agents that are "
        f"not already in `mvp/records/`, and save what you find to "
        f"`mvp/raw/{row['source_id']}/` as JSON lines with at least "
        f"`source_record_id`, `title`, `text`, `date` and `url`. Then run "
        f"`python mvp/pipeline/run.py normalise {row['source_id']}`.\n"
    )


def fetch_aiid(target, token_file):
    """Delegate to fetch_aiid.py, imported as a library and never modified."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import fetch_aiid as fa
    except ImportError as e:
        die(f"cannot import fetch_aiid.py: {e}")
    target.mkdir(parents=True, exist_ok=True)
    token = fa.resolve_token(token_file)
    client = fa.Client(token)
    schema = fa.Schema(client)
    for collection, depth, exclude, sort in (
            ("incidents", 0, [], "incident_id"),
            ("classifications", 1, ["reports"], "_id")):
        builder = fa.SelectionBuilder(schema, depth=depth, exclude=exclude)
        selection = builder.build(schema.root_type(collection))
        rows = fa.fetch_all(client, collection, selection, 100, sort)
        fa.write_outputs(rows, str(target), collection)
        info(f"  ok    aiid/{collection}: {len(rows)} records")
    (target / "FETCHED.md").write_text(
        f"# AIID snapshot\n\nFetched {TODAY} by `mvp/pipeline/run.py fetch aiid`.\n",
        encoding="utf-8")


# ---------------------------------------------------------------- normalise

def stage_normalise(source_ids):
    total = 0
    for sid in source_ids:
        if sid == "aiid":
            new = normalise_aiid()
        else:
            new = normalise_generic(sid)
        if new is not None:
            total += new
    return total


def append_records(source_id, incoming):
    """Append only what changed. Returns how many versions were written."""
    path = RECORDS / f"{source_id}.jsonl"
    existing = read_jsonl(path)
    newest = {}
    for row in existing:
        newest[row["source_record_id"]] = row
    out = list(existing)
    added = 0
    for row in incoming:
        prev = newest.get(row["source_record_id"])
        if prev is not None and prev["content_hash"] == row["content_hash"]:
            continue
        out.append(row)
        added += 1
    if added:
        write_jsonl(path, out)
    info(f"  ok    {source_id}: {len(incoming)} records, {added} new or changed")
    return added


def normalise_aiid():
    src = RAW / "aiid"
    incidents = read_jsonl(src / "incidents.jsonl")
    if not incidents:
        info("  skip  aiid: no raw snapshot; run fetch first")
        return None
    classifications = read_jsonl(src / "classifications.jsonl")
    fetched_at = aiid_fetched_at(src)

    # classifications.jsonl carries no incident_id; its only path back is the
    # expanded `incidents` list, so join on the mongo _id.
    by_mongo = {}
    for c in classifications:
        for inc in c.get("incidents") or []:
            by_mongo.setdefault(inc.get("_id"), []).append(c)

    navigator = read_navigator(src)

    out = []
    for inc in incidents:
        iid = str(inc.get("incident_id"))
        joined = by_mongo.get(inc.get("_id"), [])
        labels = []
        # A record nobody has classified is unscreened, not negative. That is a
        # different thing from a record CSETv1 classified as 'no', so the two
        # must be distinguishable downstream.
        meta = {"has_classification": bool(joined),
                "namespaces": sorted({c.get("namespace") or "" for c in joined})}
        for c in joined:
            ns = c.get("namespace") or ""
            for attr in c.get("attributes") or []:
                name = attr.get("short_name")
                value = decode_value(attr.get("value_json"))
                if name == MA_FIELD and value not in (None, ""):
                    # every namespace separately, so a split between the
                    # consensus and an individual annotator stays visible
                    labels.append({"source": "aiid", "namespace": ns,
                                   "field": MA_FIELD, "value": value,
                                   "fetched_at": fetched_at})
                elif name == "Risk Subdomain" and ns == "MIT" and value:
                    meta["mit_subdomain"] = value
        if iid in navigator:
            labels.append(navigator[iid])
        body = {
            "title": inc.get("title") or "",
            "text": inc.get("description") or "",
            "date": inc.get("date") or "",
            "url": f"https://incidentdatabase.ai/cite/{iid}",
            "external_labels": labels,
            "meta": meta,
        }
        out.append({"source_id": "aiid", "source_record_id": iid,
                    "fetched_at": fetched_at,
                    "content_hash": content_hash(body), **body})
    return append_records("aiid", out)


def aiid_fetched_at(src):
    manifest = src / "FETCHED.md"
    if manifest.exists():
        m = re.search(r"(\d{4}-\d{2}-\d{2})", manifest.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return TODAY


def decode_value(value_json):
    if value_json in (None, ""):
        return None
    try:
        decoded = json.loads(value_json)
    except (json.JSONDecodeError, TypeError):
        return str(value_json)
    return decoded if isinstance(decoded, str) else decoded


def read_navigator(src):
    """The Navigator's behaviour facet, read off the rendered page by hand."""
    path = src / "navigator_multiagent.tsv"
    if not path.exists():
        return {}
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            iid = row.get("aiid_incident_id")
            if iid:
                out[str(iid)] = {"source": "mit_navigator", "namespace": "navigator",
                                 "field": "behaviour", "value": "Multi-agent",
                                 "fetched_at": "2026-11-09"}
    return out


def normalise_generic(source_id):
    """Any source whose raw drop is already JSON lines of the right shape."""
    src = RAW / source_id
    files = sorted(src.glob("*.jsonl")) if src.exists() else []
    if not files:
        info(f"  skip  {source_id}: nothing in {src}")
        return None
    out = []
    for path in files:
        for row in read_jsonl(path):
            rid = str(row.get("source_record_id") or row.get("id") or "")
            if not rid:
                die(f"{path}: a record has no source_record_id")
            body = {
                "title": row.get("title") or "",
                "text": row.get("text") or row.get("description") or "",
                "date": row.get("date") or "",
                "url": row.get("url") or "",
                "external_labels": row.get("external_labels") or [],
                "meta": row.get("meta") or {},
            }
            out.append({"source_id": source_id, "source_record_id": rid,
                        "fetched_at": row.get("fetched_at") or TODAY,
                        "content_hash": content_hash(body), **body})
    return append_records(source_id, out)


# ----------------------------------------------------------------- discover

def stage_discover(source_ids):
    """Search the discovery sources for what AIID does not carry.

    18 of the project's 27 incidents are absent from AIID entirely, so this is
    not a nicety. Sources a script can reach are queried; the rest produce a
    work order rather than failing silently.
    """
    reg = registry()
    reachable, manual = [], []
    for sid in source_ids:
        row = reg.get(sid)
        if row is None or row["role"] != "discovery":
            continue
        (reachable if row["adapter"] == "forummagnum" else manual).append(row)
    for row in reachable:
        info(f"  todo  {row['source_id']}: ForumMagnum adapter not implemented yet; "
             f"query {row['url']} by tag and search term")
    if manual:
        STATE.mkdir(parents=True, exist_ok=True)
        path = STATE / "work_orders.md"
        path.write_text("\n".join(work_order(r) for r in manual), encoding="utf-8")
        info(f"  note  {len(manual)} discovery source(s) need a human: {path}")
    return 0


# ---------------------------------------------------------------- prefilter

def stage_prefilter():
    """Three arms, union. No single net has acceptable recall.

    Measured: the keyword net matched 3 of 200 sampled AIID incidents; the
    Navigator's rater missed 3 of the 9 of our incidents that are in AIID; and
    305 of 1,803 AIID incidents carry no classification at all, skewed recent.
    """
    records = latest_records()
    if not records:
        info("  skip  prefilter: no records; run normalise first")
        return []
    known = dossier_source_refs()
    rows = []
    for (sid, rid), rec in sorted(records.items()):
        if (sid, rid) in known:
            continue
        arms = []
        label_hits = [l for l in rec.get("external_labels", [])
                      if str(l.get("value", "")).lower() in MA_POSITIVE
                      or l.get("field") == "behaviour"]
        if label_hits:
            arms.append("label")
        haystack = f"{rec.get('title', '')} {rec.get('text', '')}"
        terms = [t for t, rx in KEYWORD_RE if rx.search(haystack)]
        if terms:
            arms.append("keyword")
        classified = rec.get("meta", {}).get("has_classification")
        if classified is False and rec.get("date", "") >= UNCLASSIFIED_CUTOFF:
            arms.append("unclassified")
        if not arms:
            continue
        rows.append({
            "source_id": sid,
            "source_record_id": rid,
            "date": rec.get("date", ""),
            "title": rec.get("title", ""),
            "arms": ";".join(arms),
            "label_values": ";".join(
                f"{l.get('namespace') or l.get('source')}={l.get('value')}"
                for l in label_hits),
            "keyword_terms": ";".join(terms),
            "url": rec.get("url", ""),
        })
    STATE.mkdir(parents=True, exist_ok=True)
    write_jsonl(STATE / "queue.jsonl", rows)
    by_arm = {}
    for row in rows:
        for arm in row["arms"].split(";"):
            by_arm[arm] = by_arm.get(arm, 0) + 1
    info(f"  ok    prefilter: {len(rows)} candidates of {len(records)} records")
    for arm, n in sorted(by_arm.items()):
        info(f"          {arm}: {n}")
    return rows


def dossier_source_refs():
    """(source_id, source_record_id) pairs already attested by a dossier."""
    out = set()
    for path in all_dossiers():
        meta, _ = read_dossier(path)
        for s in meta.get("sources") or []:
            out.add((s.get("source_id"), str(s.get("record_id"))))
    return out


# ------------------------------------------------------------------ promote

def stage_promote(refs):
    records = latest_records()
    made = []
    for ref in refs:
        if ":" not in ref:
            die(f"promote takes <source_id>:<record_id>, got {ref!r}")
        sid, rid = ref.split(":", 1)
        rec = records.get((sid, rid))
        if rec is None:
            die(f"no record {ref}; run normalise first")
        doc_id = f"AIID-{int(rid):04d}" if sid == "aiid" else next_mig_id(made)
        path = dossier_path(doc_id)
        if path.exists():
            info(f"  skip  {doc_id}: already exists")
            continue
        ok, precision = parse_iso(rec.get("date") or "")
        meta = {
            "id": doc_id,
            "title": rec.get("title") or "",
            "canonical_source": sid,
            "sources": [{"source_id": sid, "record_id": rid,
                         "url": rec.get("url", ""), "first_seen": TODAY}],
            "occurrence_date": rec.get("date") or "",
            "occurrence_date_precision": precision or "year",
            "first_seen": TODAY,
            "last_verified": "",
            "systems": [],
            "actor_count": "unclear",
            "interaction_kind": "unclear",
            "evidence_type": "",
            "multi_agent": False,
            "multi_agent_basis": "",
            "multi_agent_label_source": "",
            "external_labels": rec.get("external_labels") or [],
            "failure_mode": None,
            "failure_mode_source": "",
            "instances": [],
            "verification": "unverified",
        }
        pending = "_pending_"
        sections = {name: pending for name in SECTIONS}
        sections["What happened"] = rec.get("text") or pending
        sections["Sources"] = f"- {sid}: {rec.get('url', '')}"
        write_dossier(path, meta, sections)
        made.append(doc_id)
        info(f"  ok    {doc_id}: scaffolded from {ref}")
    if made:
        info("  note  a scaffold is not a record: fill every _pending_ section, verify "
             "against the primary source, and set multi_agent yourself.")
    return made


def next_mig_id(pending):
    used = {p.stem for p in all_dossiers()} | set(pending)
    n = 1
    while f"MIG-{n:04d}" in used:
        n += 1
    return f"MIG-{n:04d}"


# -------------------------------------------------------------------- index

def stage_index():
    rows = []
    for path in all_dossiers():
        meta, _ = read_dossier(path)
        sources = meta.get("sources") or []
        rows.append({
            "id": meta.get("id", ""),
            "title": meta.get("title", ""),
            "occurrence_date": meta.get("occurrence_date", ""),
            "date_precision": meta.get("occurrence_date_precision", ""),
            "canonical_source": meta.get("canonical_source", ""),
            "sources": ";".join(str(s.get("source_id")) for s in sources),
            "source_count": str(len(sources)),
            "evidence_type": meta.get("evidence_type", ""),
            "multi_agent": str(meta.get("multi_agent", "")),
            "multi_agent_label_source": meta.get("multi_agent_label_source", ""),
            "external_label_count": str(len(meta.get("external_labels") or [])),
            "failure_mode": meta.get("failure_mode") or "",
            "instances": ";".join(meta.get("instances") or []),
            "verification": meta.get("verification", ""),
            "first_seen": meta.get("first_seen", ""),
            "last_verified": meta.get("last_verified") or "",
            "path": str(path.relative_to(ROOT)),
        })
    rows.sort(key=lambda r: (r["occurrence_date"], r["id"]))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "incident_index.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["id"])
        w.writeheader()
        w.writerows(rows)
    state = pipeline_state(rows)
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "pipeline.json").write_text(
        json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    info(f"  ok    index: {len(rows)} dossiers -> {path.relative_to(ROOT)}")
    return state


def pipeline_state(index_rows):
    reg = registry()
    records = latest_records()
    queue = read_jsonl(STATE / "queue.jsonl")
    proposals = sum(len(read_jsonl(p)) for p in sorted(PROPOSALS.glob("*.jsonl"))) \
        if PROPOSALS.exists() else 0

    per_source = {}
    for (sid, _), _rec in records.items():
        per_source[sid] = per_source.get(sid, 0) + 1

    provenance = {"ours": 0, "external": 0, "machine": 0, "unlabelled": 0}
    for row in index_rows:
        src = row["multi_agent_label_source"]
        if not src:
            provenance["unlabelled"] += 1
        elif src == "ours":
            provenance["ours"] += 1
        elif src.startswith("classifier:"):
            provenance["machine"] += 1
        else:
            provenance["external"] += 1

    queue_arms = {}
    for row in queue:
        for arm in str(row.get("arms", "")).split(";"):
            if arm:
                queue_arms[arm] = queue_arms.get(arm, 0) + 1

    return {
        "generated": TODAY,
        "modes": MODES,
        "stages": [
            {"id": "sources", "label": "Sources", "count": len(reg),
             "detail": {r["role"]: sum(1 for x in reg.values()
                                       if x["role"] == r["role"]) for r in reg.values()}},
            {"id": "records", "label": "Records", "count": len(records),
             "detail": per_source},
            {"id": "discover", "label": "Discover", "count": sum(
                1 for r in reg.values() if r["role"] == "discovery"),
             "detail": {"implemented": sum(1 for r in reg.values()
                                           if r["role"] == "discovery"
                                           and r["adapter"] != "work_order"),
                        "work_order": sum(1 for r in reg.values()
                                          if r["role"] == "discovery"
                                          and r["adapter"] == "work_order")}},
            {"id": "prefilter", "label": "Prefilter", "count": len(queue),
             "detail": queue_arms},
            {"id": "classify", "label": "Classify", "count": proposals,
             "detail": {"proposals": proposals}},
            {"id": "review", "label": "Review", "count": max(len(queue) - proposals, 0),
             "detail": {"awaiting": max(len(queue) - proposals, 0)}},
            {"id": "dossiers", "label": "Dossiers", "count": len(index_rows),
             "detail": {k: v for k, v in provenance.items() if v}},
            {"id": "index", "label": "Index", "count": len(index_rows),
             "detail": {}},
        ],
        "provenance": provenance,
        "sources": sorted(per_source),
        "incidents": index_rows,
        "queue": [{k: row.get(k, "") for k in
                   ("source_id", "source_record_id", "date", "title", "arms",
                    "label_values", "keyword_terms", "url")} for row in queue],
        "registry": [{"source_id": r["source_id"], "name": r["name"],
                      "role": r["role"], "access_method": r["access_method"],
                      "adapter": r["adapter"], "status": r["status"],
                      "external_ma_label": r["external_ma_label"],
                      "reuse_status": r["reuse_status"]}
                     for r in sorted(reg.values(), key=lambda x: (x["role"], x["source_id"]))],
    }


# -------------------------------------------------------------------- check

def stage_check():
    problems = []
    taxonomy_instances = {r["instance_id"] for r in read_csv(TAXONOMY / "instances.csv")}
    risks = {r["risk_id"] for r in read_csv(TAXONOMY / "risks.csv")}
    reg = registry()
    records = latest_records()
    seen_ids = set()

    for path in all_dossiers():
        rel = path.relative_to(ROOT)
        meta, body = read_dossier(path)

        for key in REQUIRED_KEYS:
            if key not in meta:
                problems.append(f"{rel}: missing frontmatter key {key!r}")

        doc_id = meta.get("id", "")
        if doc_id != path.stem:
            problems.append(f"{rel}: id {doc_id!r} does not match the filename")
        if doc_id in seen_ids:
            problems.append(f"{rel}: duplicate id {doc_id!r}")
        seen_ids.add(doc_id)
        if not re.fullmatch(r"(AIID-\d{4}|MIG-\d{4})", doc_id or ""):
            problems.append(f"{rel}: id {doc_id!r} matches no canonical-source pattern")

        ok, precision = parse_iso(meta.get("occurrence_date") or "")
        if not ok:
            problems.append(f"{rel}: occurrence_date {meta.get('occurrence_date')!r} "
                            f"is not ISO or partial-ISO")
        elif meta.get("occurrence_date_precision") != precision:
            problems.append(f"{rel}: occurrence_date_precision says "
                            f"{meta.get('occurrence_date_precision')!r} but the date is "
                            f"{precision!r}")
        for key in ("first_seen", "last_verified"):
            if meta.get(key) and not parse_iso(meta[key])[0]:
                problems.append(f"{rel}: {key} {meta[key]!r} is not a date")

        for s in meta.get("sources") or []:
            sid, rid = s.get("source_id"), str(s.get("record_id", ""))
            if sid not in reg:
                problems.append(f"{rel}: source_id {sid!r} is not in the registry")
            elif (sid, rid) not in records:
                problems.append(f"{rel}: sources entry {sid}:{rid} resolves to no record")
        if not meta.get("sources"):
            problems.append(f"{rel}: sources is empty")
        canonical = meta.get("canonical_source")
        source_ids = [s.get("source_id") for s in meta.get("sources") or []]
        if canonical not in source_ids:
            problems.append(f"{rel}: canonical_source {canonical!r} is not among sources")
        if "aiid" in source_ids and canonical != "aiid":
            problems.append(f"{rel}: AIID attests this incident, so it is the canonical "
                            f"source, but canonical_source is {canonical!r}")

        et = meta.get("evidence_type")
        if et not in EVIDENCE_TYPES:
            problems.append(f"{rel}: evidence_type {et!r} not in {EVIDENCE_TYPES}")
        if meta.get("interaction_kind") not in INTERACTION_KINDS:
            problems.append(f"{rel}: interaction_kind "
                            f"{meta.get('interaction_kind')!r} not in {INTERACTION_KINDS}")
        if meta.get("verification") not in VERIFICATION:
            problems.append(f"{rel}: verification {meta.get('verification')!r} "
                            f"not in {VERIFICATION}")

        label_source = meta.get("multi_agent_label_source") or ""
        if meta.get("multi_agent") is True and label_source != "ours":
            problems.append(f"{rel}: multi_agent is true but multi_agent_label_source is "
                            f"{label_source!r}. An external or machine label may mark a "
                            f"candidate; only a human verdict puts an incident in scope.")
        if label_source and not (label_source == "ours"
                                 or label_source.startswith(("external:", "classifier:"))):
            problems.append(f"{rel}: multi_agent_label_source {label_source!r} is not "
                            f"'ours', 'external:<source_id>' or 'classifier:<prompt>@<ver>'")
        if meta.get("multi_agent") is True and not (meta.get("multi_agent_basis") or "").strip():
            problems.append(f"{rel}: multi_agent is true with no multi_agent_basis")

        fm = meta.get("failure_mode")
        if fm and fm not in risks:
            problems.append(f"{rel}: failure_mode {fm!r} is not a risk id")
        for iid in meta.get("instances") or []:
            if iid not in taxonomy_instances:
                problems.append(f"{rel}: instance {iid!r} is not in taxonomy/instances.csv")

        for key in meta:
            if re.fullmatch(r"e[1-5](_.*)?", str(key)):
                problems.append(f"{rel}: {key!r} is an evidence score; "
                                f"scoring is parked and no score belongs in a dossier")

        for name in SECTIONS:
            if not re.search(rf"^## {re.escape(name)}\s*$", body, re.M):
                problems.append(f"{rel}: missing section '## {name}'")

    if problems:
        for p in problems:
            print(f"  FAIL  {p}", file=sys.stderr)
        print(f"\ncheck failed: {len(problems)} problem(s) over "
              f"{len(all_dossiers())} dossier(s)", file=sys.stderr)
        return 1
    info(f"  ok    check: {len(all_dossiers())} dossiers, no problems")
    return 0


# ---------------------------------------------------------------------- viz

def stage_viz():
    template = Path(__file__).resolve().parent / "input_workflow.html"
    if not template.exists():
        info(f"  skip  viz: no template at {template.relative_to(ROOT)}")
        return
    state_path = STATE / "pipeline.json"
    if not state_path.exists():
        info("  skip  viz: no pipeline state; run index first")
        return
    payload = state_path.read_text(encoding="utf-8")
    html = template.read_text(encoding="utf-8")
    if "__DATA__" not in html:
        die(f"{template}: the __DATA__ placeholder is gone")
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "input_workflow.html"
    target.write_text(html.replace("__DATA__", payload), encoding="utf-8")
    info(f"  ok    viz: {target.relative_to(ROOT)}")


# ------------------------------------------------------------------- update

def stage_queue():
    queue = read_jsonl(STATE / "queue.jsonl")
    info(f"  note  {len(queue)} candidate(s) queued for the multi-agent classifier.")
    info( "        Run it with the claude code skill:  /classify-incidents")
    info( "        It is not an API job; see mvp/docs/classifiers.md.")


def stage_update(mode, token_file=None, force=False):
    if mode not in MODES:
        die(f"unknown mode {mode!r}; one of {', '.join(MODES)}")
    reg = registry()
    stages = MODES[mode]
    info(f"update --mode {mode}: {' -> '.join(stages)}")

    baseline = [s for s, r in reg.items() if r["role"] == "baseline"]
    discovery = [s for s, r in reg.items() if r["role"] == "discovery"]
    fetch_set = baseline if mode != "all-sources" else baseline + discovery

    for stage in stages:
        info(f"[{stage}]")
        if stage == "fetch":
            stage_fetch(fetch_set, force=force, token_file=token_file)
        elif stage == "normalise":
            stage_normalise(sorted({s for s in fetch_set
                                    if (RAW / s).exists()}))
        elif stage == "discover":
            stage_discover(discovery)
        elif stage == "prefilter":
            rows = stage_prefilter()
            if mode == "labelled-only":
                kept = [r for r in rows if "label" in r["arms"]]
                write_jsonl(STATE / "queue.jsonl", kept)
                info(f"  ok    labelled-only: kept {len(kept)} of {len(rows)} "
                     f"(label arm only, no classifier)")
        elif stage == "queue":
            stage_queue()
        elif stage == "index":
            stage_index()
        elif stage == "viz":
            stage_viz()
    info("done.")


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("update", help="run a whole mode")
    up.add_argument("--mode", default="aiid-full", choices=sorted(MODES))
    up.add_argument("--token-file")
    up.add_argument("--force", action="store_true", help="refetch even if raw exists")

    f = sub.add_parser("fetch")
    f.add_argument("source_id", nargs="+")
    f.add_argument("--token-file")
    f.add_argument("--force", action="store_true")

    n = sub.add_parser("normalise")
    n.add_argument("source_id", nargs="+")

    d = sub.add_parser("discover")
    d.add_argument("source_id", nargs="*")

    sub.add_parser("prefilter")

    p = sub.add_parser("promote")
    p.add_argument("ref", nargs="+", help="<source_id>:<record_id>")

    sub.add_parser("index")
    sub.add_parser("viz")
    sub.add_parser("check")

    args = ap.parse_args()

    if args.cmd == "update":
        stage_update(args.mode, args.token_file, args.force)
    elif args.cmd == "fetch":
        stage_fetch(args.source_id, args.force, args.token_file)
    elif args.cmd == "normalise":
        stage_normalise(args.source_id)
    elif args.cmd == "discover":
        ids = args.source_id or [s for s, r in registry().items()
                                 if r["role"] == "discovery"]
        stage_discover(ids)
    elif args.cmd == "prefilter":
        stage_prefilter()
    elif args.cmd == "promote":
        stage_promote(args.ref)
    elif args.cmd == "index":
        stage_index()
    elif args.cmd == "viz":
        stage_viz()
    elif args.cmd == "check":
        sys.exit(stage_check())


if __name__ == "__main__":
    main()
