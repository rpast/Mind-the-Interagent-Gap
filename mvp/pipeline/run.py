#!/usr/bin/env python3
"""The input-layer update routine.

Stages, in the order an update runs them:

    sources    load the source registry
    discover   search non-AIID sources for incidents AIID does not have
               (placeholder: not built yet; `discover` alone writes the work orders)
    fetch      pull the baseline source into mvp/raw/<source>/, verbatim
    manual     copy hand-written incident write-ups into mvp/raw/manual/
    normalise  raw -> mvp/records/<source>.jsonl, append-only, content-hashed
    prefilter  screen records into a candidate queue, recall first
    read       (claude code skill /classify-incidents, step 0: the readings)
    readiness  say, per record, whether enough has been read to classify it
    judge      (claude code skill /classify-incidents; see mvp/docs/classifiers.md)
    derive     the labels, by rule (derive.py), from the newest extract_gate proposal
               of each record -> mvp/state/verdicts.jsonl
    review     a person promotes proposals to dossiers (`promote`);
               `instances-due` lists the records in scope with no instance proposal
    check      validate the layer; exits non-zero on any problem
    index      regenerate mvp/out/incident_index.csv and mvp/state/pipeline.json
    viz        render the pages in mvp/out/

    update [--discover] [--manual DIR] [--refetch] [--token-file F]
    serve  [--port 8765]     the front end on http://127.0.0.1:<port>/
    testrun [--refetch] [--manual] [--discover] [--skip STEP ...]
                             the same steps on made-up incidents in a scratch folder
                             (see mvp/testenv/README.md); never touches the real tree
    runs [RUN]               the retained logs of real runs, newest first; with RUN, its trace:
                             how the map's numbers changed, step by step

`update` runs them all, step by step. A step that needs a person (a skill run, a
review) is reported with what is needed, and the run goes on; `serve` runs the same
steps and waits for the person instead. Each stage is also runnable alone.

AIID is the baseline source: the snapshot in mvp/raw/aiid/ is reused unless
--refetch. Everything else is a discovery source, searched for what AIID does not
carry, or a write-up the curator adds by hand with --manual.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import itertools
import json
import os
import re
import shutil
import sys
import threading
import traceback
from datetime import date, datetime
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("this pipeline needs PyYAML: pip install -r requirements.txt")

# The labelling rules live in one file beside this one, derive.py, and nowhere else.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import derive as rules  # noqa: E402

# Every path the stages read or write. They live in module globals, set in one place.
# The test run (testenv.py) loads a second instance of this module and points that
# one at a scratch workspace; this instance is set once, here, and never re-pointed.
PATH_NAMES = ("MVP", "ROOT", "REGISTRY", "TAXONOMY", "RAW", "RECORDS", "INCIDENTS",
              "PROPOSALS", "CONTEXT", "STATE", "OUT", "RUN_FILE", "RUNS")


def set_paths(mvp_dir):
    global MVP, ROOT, REGISTRY, TAXONOMY, RAW, RECORDS, INCIDENTS, PROPOSALS, \
        CONTEXT, STATE, OUT, RUN_FILE, RUNS
    MVP = Path(mvp_dir).resolve()
    ROOT = MVP.parent
    REGISTRY = MVP / "registry" / "sources.csv"
    TAXONOMY = MVP / "taxonomy"
    RAW = MVP / "raw"
    RECORDS = MVP / "records"
    INCIDENTS = MVP / "incidents"
    PROPOSALS = MVP / "proposals"
    CONTEXT = MVP / "context"
    STATE = MVP / "state"
    OUT = MVP / "out"
    RUN_FILE = STATE / "run.json"
    RUNS = STATE / "runs"           # one retained log per run: <run id>.json


set_paths(Path(__file__).resolve().parents[1])

TODAY = date.today().isoformat()

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
    "failure_mode", "failure_mode_source", "instances", "instances_presumed",
    "verification",
]

# The multi-agent-attack presumption carries to the instance layer: an attack whose
# source does not say what multiplicity contributed is presumed to show both of
# these until the source settles it. See mvp/docs/definitions.md.
PRESUMABLE_INSTANCES = {"I28", "I29"}

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

# A record nobody asked the multi-agent question of is unscreened, not negative.
# The `unasked` arm queues every such record dated on or after this cutoff.
UNCLASSIFIED_CUTOFF = "2024-01-01"

MA_FIELD = "Multiple AI Interaction"
MA_POSITIVE = {"yes", "maybe"}
# The source whose taxonomies can carry MA_FIELD. Only its records can be "asked".
MA_SOURCE = "aiid"

# The third prefilter arm was `unclassified` until 2026-11-16. Queue rows written
# before then still carry the old name; they are read as `unasked`.
ARM_ALIASES = {"unclassified": "unasked"}


# The context layer: what a source says, read for the facts the gates need.
# See mvp/docs/context_layer.md. A fact is `stated`, `not_stated` (the source was
# read and is silent - a finding), `not_applicable`, or `unread` (nobody looked).
CONTEXT_FACTS = ["agents", "interaction", "multiplicity", "setting",
                 "cooperation", "objectives", "mechanism"]
FACT_STATUS = ["stated", "not_stated", "not_applicable", "unread"]
AGENT_COUNTS = ["none", "one", "several", "unknown"]
# Worst to best. `record` is the source record's own text; `secondary` is an
# aggregator's page read in full with the source it cites unread; `curator` is a
# write-up the curator added by hand and vouches for (manual records only).
READ_DEPTH = ["unreadable", "record", "secondary", "curator", "primary_partial",
              "primary_full"]
DECISIONS = ["scope", "evidence_type", "failure_mode", "instances"]
READY_LEVELS = ["ready", "provisional", "not_ready", "not_needed"]

# Prefilter arms that flag a record as a likely multi-agent case. A flagged record
# may not be dismissed as single-agent on its record text alone.
FLAG_ARMS = {"label", "keyword"}

# Hand-written incident write-ups (update --manual DIR).
MANUAL = "manual"
MANUAL_SUFFIXES = {".txt", ".md"}

# --------------------------------------------------------------------- utils

def die(msg):
    sys.exit(f"error: {msg}")


# A step of an update run collects what its stages say. The sink is per thread, so
# the server's request threads never write into a run's log.
_LOCAL = threading.local()


def info(msg):
    sink = getattr(_LOCAL, "sink", None)
    if sink is not None:
        for line in str(msg).splitlines() or [""]:
            sink.append(line)
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


# A record's identity is the pair (source_id, source_record_id). Every file row carries
# it twice: as the two fields, and as one string, `record_key`, "<source_id>:<record_id>"
# (e.g. "aiid:1604"). It is the same string `promote` takes. Inside run.py dicts are
# keyed on the pair; every row written to a file carries the string.

def record_key(source_id, source_record_id):
    return f"{source_id}:{source_record_id}"


def split_key(key):
    """'aiid:1604' -> ('aiid', '1604'). The record id may itself hold a colon."""
    if ":" not in str(key):
        die(f"a record key is <source_id>:<record_id>, got {key!r}")
    sid, rid = str(key).split(":", 1)
    return sid, rid


def row_pair(row):
    """(source_id, source_record_id) of a file row: from `record_key` when the row has
    one, else from the two fields (rows written before the key existed, or by a skill
    that does not write it)."""
    if row.get("record_key"):
        return split_key(row["record_key"])
    return row["source_id"], str(row["source_record_id"])


# The fields a record's content_hash covers: its substance, nothing about when or how it
# was fetched. A label's `fetched_at` is stored but never hashed, so a re-fetch on a new
# date with nothing changed appends nothing.
HASHED_FIELDS = {"title": "", "text": "", "date": "", "url": "",
                 "external_labels": [], "meta": {}}


def record_hash(row):
    body = {k: row.get(k, default) for k, default in HASHED_FIELDS.items()}
    body["external_labels"] = [{k: v for k, v in label.items() if k != "fetched_at"}
                               for label in body["external_labels"] or []]
    return content_hash(body)


def make_record(source_id, source_record_id, fetched_at, body, raw_ref):
    """One record row. `raw_ref` says where in raw/ it came from; it is not hashed.

    raw_ref = {"path": the raw file, repo-relative; "id_field": the source's own id
               field in that file; "id": its value; "fetched_at": the fetch date}
    """
    rid = str(source_record_id)
    return {"source_id": source_id, "source_record_id": rid,
            "record_key": record_key(source_id, rid),
            "fetched_at": fetched_at, "raw_ref": raw_ref,
            "content_hash": record_hash(body), **body}


def repo_path(path):
    """A path as the repository names it: relative to the repo root when inside it."""
    p = Path(path).resolve()
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


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
            out[row_pair(row)] = row
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
    """Fetch what a script can fetch. Sources a person must visit are discover's
    business: `run.py discover` writes their work orders, fetch does not."""
    reg = registry()
    done, skipped = [], []
    for sid in source_ids:
        row = reg.get(sid)
        if row is None:
            die(f"unknown source_id {sid!r}; it must be a row in {REGISTRY}")
        method, adapter = row["access_method"], row["adapter"]
        target = RAW / sid
        if method == "read_only":
            skipped.append(f"{sid}: reference source, nothing to fetch")
            continue
        if adapter == MANUAL:
            skipped.append(f"{sid}: added by hand with `update --manual DIR`")
            continue
        if method == "graphql" and adapter == "aiid":
            if target.exists() and not force:
                n = len(read_jsonl(target / "incidents.jsonl"))
                skipped.append(f"{sid}: snapshot present ({n} records); "
                               f"--refetch to fetch again")
                continue
            fetch_aiid(target, token_file)
            done.append(sid)
        else:
            skipped.append(f"{sid}: no fetcher; `run.py discover` writes its work order")
    for line in skipped:
        info(f"  skip  {line}")
    for line in done:
        info(f"  ok    {line}: fetched")
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
    token, _where = fa.resolve_token(token_file)
    client = fa.Client(token)
    schema = fa.Schema(client.query(fa.INTROSPECT))
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
        elif sid == MANUAL:
            new = normalise_manual()
        else:
            new = normalise_generic(sid)
        if new is not None:
            total += new
    return total


def append_records(source_id, incoming):
    """Append only what changed: a record whose content_hash (its substance; see
    record_hash) equals its newest version's is not written again. Returns how many
    versions were written."""
    path = RECORDS / f"{source_id}.jsonl"
    existing = read_jsonl(path)
    newest = {}
    for row in existing:
        newest[row_pair(row)] = row
    out = list(existing)
    added = 0
    for row in incoming:
        prev = newest.get(row_pair(row))
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

    navigator = read_navigator()
    raw_path = repo_path(src / "incidents.jsonl")

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
        out.append(make_record("aiid", iid, fetched_at, body,
                               {"path": raw_path, "id_field": "_id",
                                "id": inc.get("_id"), "fetched_at": fetched_at}))
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


def navigator_path():
    """Hand-made, so it lives in the registry, not in raw/ (verbatim fetch output)."""
    return MVP / "registry" / "labels" / "navigator_multiagent.tsv"


def read_navigator():
    """The Navigator's behaviour facet, copied off the rendered page by hand on
    2026-11-09. See mvp/registry/labels/README.md."""
    path = navigator_path()
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
            id_field = "source_record_id" if row.get("source_record_id") else "id"
            rid = str(row.get(id_field) or "")
            if not rid:
                die(f"{path}: a record has no source_record_id")
            fetched_at = row.get("fetched_at") or TODAY
            body = {
                "title": row.get("title") or "",
                "text": row.get("text") or row.get("description") or "",
                "date": row.get("date") or "",
                "url": row.get("url") or "",
                "external_labels": row.get("external_labels") or [],
                "meta": row.get("meta") or {},
            }
            out.append(make_record(source_id, rid, fetched_at, body,
                                   {"path": repo_path(path), "id_field": id_field,
                                    "id": row.get(id_field), "fetched_at": fetched_at}))
    return append_records(source_id, out)


# ------------------------------------------------------------------- manual
#
# The curator's own write-ups. One file is one incident, unless it holds two or more
# headings at its top level (`# `, else `## `), in which case each heading starts one.
# The files are copied verbatim to mvp/raw/manual/; ORIGINS.json beside them records
# where each came from. Records, queue rows and context rows follow from the copies.

MANUAL_ORIGINS = "ORIGINS.json"
ISO_DATE_RE = re.compile(
    r"(?<![\d-])((?:19|20)\d{2})(?:-(0[1-9]|1[0-2])(?:-(0[1-9]|[12]\d|3[01]))?)?(?![\d-])")
URL_RE = re.compile(r"https?://[^\s<>()\[\]\"']+")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "untitled"


def manual_files(directory):
    return sorted(p for p in Path(directory).iterdir()
                  if p.is_file() and p.suffix.lower() in MANUAL_SUFFIXES
                  and not p.name.startswith("."))


def ingest_manual(directory):
    """Copy a directory of write-ups into mvp/raw/manual/, verbatim.

    Returns (files, incidents) found. A copy is only rewritten if its bytes differ,
    so running twice on the same directory changes nothing.
    """
    src = Path(directory).expanduser().resolve()
    if not src.is_dir():
        die(f"--manual {directory!r} is not a directory")
    files = manual_files(src)
    target = RAW / MANUAL
    origins_path = target / MANUAL_ORIGINS
    origins = json.loads(origins_path.read_text(encoding="utf-8")) \
        if origins_path.exists() else {}
    copied = 0
    for path in files:
        data = path.read_bytes()
        dest = target / path.name
        if not dest.exists() or dest.read_bytes() != data:
            target.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            copied += 1
        origins[path.name] = str(path)
    if files:
        blob = json.dumps(origins, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if not origins_path.exists() or origins_path.read_text(encoding="utf-8") != blob:
            origins_path.write_text(blob, encoding="utf-8")
    incidents = sum(len(split_manual(p.read_text(encoding="utf-8"))) for p in files)
    info(f"  ok    manual: {len(files)} file(s), {incidents} incident(s) in {src}; "
         f"{copied} copied to {target.relative_to(ROOT)}/")
    if not files:
        info(f"  note  no .txt or .md files in {src}")
    return len(files), incidents


def split_manual(text):
    """[(title, body)] for one write-up. Headings inside code fences do not count."""
    lines = text.splitlines()
    fenced, heads = False, {1: [], 2: []}
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        m = re.match(r"(#{1,2}) +\S", line)
        if m and not fenced:
            heads[len(m.group(1))].append(i)
    top = 1 if heads[1] else 2
    starts = heads[top]
    if len(starts) < 2:
        for i, line in enumerate(lines):
            if line.strip():
                title = re.sub(r"^#+\s*", "", line.strip())
                return [(title, "\n".join(lines[i + 1:]).strip("\n"))]
        return []
    out = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        title = re.sub(r"^#+\s*", "", lines[start].strip())
        out.append((title, "\n".join(lines[start + 1:end]).strip("\n")))
    return out


def first_iso_date(text):
    m = ISO_DATE_RE.search(URL_RE.sub(" ", text))
    return m.group(0) if m and parse_iso(m.group(0))[0] else ""


def first_url(text):
    m = URL_RE.search(text)
    return m.group(0).rstrip(".,;:!?") if m else ""


def normalise_manual():
    src = RAW / MANUAL
    files = manual_files(src) if src.exists() else []
    if not files:
        info(f"  skip  {MANUAL}: nothing in {src.relative_to(ROOT)}")
        return None
    origins_path = src / MANUAL_ORIGINS
    origins = json.loads(origins_path.read_text(encoding="utf-8")) \
        if origins_path.exists() else {}
    stems = {}
    for path in files:
        stems.setdefault(slug(path.stem), []).append(path)
    out = []
    for path in files:
        base = slug(path.stem)
        if len(stems[base]) > 1:      # a.txt and a.md: keep their ids apart
            base = slug(path.name)
        parts = split_manual(path.read_text(encoding="utf-8"))
        for n, (title, text) in enumerate(parts, 1):
            rid = base if len(parts) == 1 else f"{base}-{n}"
            whole = f"{title}\n{text}"
            body = {
                "title": title,
                "text": text,
                "date": first_iso_date(whole),
                "url": first_url(whole),
                "external_labels": [],
                "meta": {"manual": True, "origin_path": origins.get(path.name, ""),
                         "raw_file": path.name},
            }
            # a write-up has no id of its own: the record id is made from its file name
            out.append(make_record(MANUAL, rid, TODAY, body,
                                   {"path": repo_path(path), "id_field": "source_record_id",
                                    "id": rid, "fetched_at": TODAY}))
    # content_hash covers the body only, so an unchanged write-up is not re-appended
    added = append_records(MANUAL, out)
    ensure_manual_context()
    return added


def ensure_manual_context():
    """Every manual record gets one context row, written once: the curator's flag.

    It settles one fact, that several agents are involved, on the curator's word.
    Every other fact stays unread. See mvp/docs/context_layer.md.
    """
    path = CONTEXT / f"{MANUAL}.jsonl"
    have = {row_pair(r)[1] for r in read_jsonl(path) if r.get("manual")}
    new = []
    for (sid, rid), rec in sorted(latest_records(MANUAL).items()):
        if rid in have:
            continue
        facts = {name: {"status": "unread", "text": "", "quote": ""}
                 for name in CONTEXT_FACTS}
        facts["agents"] = {"status": "stated", "quote": "",
                           "text": "several agents, on the curator's word"}
        new.append({"source_id": MANUAL, "source_record_id": rid,
                    "record_key": record_key(MANUAL, rid), "manual": True,
                    "agent_count": "several", "attack": None,
                    "read": [{"url": rec.get("url", ""), "depth": "curator",
                              "read_on": TODAY}],
                    "facts": facts, "quote": "",
                    "provenance": {"method": "manual"}})
    if new:
        write_jsonl(path, read_jsonl(path) + new)
        info(f"  ok    {MANUAL}: {len(new)} context row(s) -> "
             f"{path.relative_to(ROOT)}")
    return len(new)


# ----------------------------------------------------------------- discover

def stage_discover(source_ids):
    """Search the discovery sources for what AIID does not carry.

    18 of the project's 27 incidents are absent from AIID entirely, so this is
    not a nicety. NOT BUILT YET: no adapter queries anything. What exists is its
    sub-step, the work orders: a to-do note for every source a person must visit.
    An update run does not depend on it.
    """
    reg = registry()
    reachable, manual = [], []
    for sid in source_ids:
        row = reg.get(sid)
        if row is None or row["role"] != "discovery" or row["adapter"] == MANUAL:
            continue
        (manual if row["adapter"] == "work_order" else reachable).append(row)
    for row in reachable:
        info(f"  todo  {row['source_id']}: the {row['adapter']} reader is not written yet; "
             f"a script could reach {row['url']}")
    if manual:
        STATE.mkdir(parents=True, exist_ok=True)
        path = STATE / "work_orders.md"
        path.write_text("\n".join(work_order(r) for r in manual), encoding="utf-8")
        info(f"  note  {len(manual)} discovery source(s) need a human: "
             f"{path.relative_to(ROOT)}")
    return len(manual)


# ---------------------------------------------------------------- prefilter

def row_arms(row):
    """The arms of a queue row, as a list, old names read as the new ones."""
    return [ARM_ALIASES.get(a, a) for a in str(row.get("arms") or "").split(";") if a]


def arm_counts(queue):
    """Queue rows per arm. A row caught by two arms counts under both."""
    out = {}
    for row in queue:
        for arm in row_arms(row):
            out[arm] = out.get(arm, 0) + 1
    return out


def ma_asked(rec):
    """Did any AIID taxonomy ask this record the multi-agent question? True when it
    carries an external label for MA_FIELD from the AIID namespaces, whatever the
    answer was."""
    return any(l.get("source") == MA_SOURCE and l.get("field") == MA_FIELD
               for l in rec.get("external_labels") or [])


def stage_prefilter():
    """Three arms, union. No single net has acceptable recall.

      label    an external label says yes or maybe (MA_POSITIVE), or the Navigator's
               multi-agent facet lists it
      keyword  the recall-first regex net, KEYWORD_TERMS
      unasked  an AIID record dated on or after UNCLASSIFIED_CUTOFF that no AIID
               taxonomy asked the multi-agent question (no MA_FIELD label at all)

    Only `label` and `keyword` flag a record (FLAG_ARMS); `unasked` does not.

    Measured: the keyword net matched 3 of 200 sampled AIID incidents; the
    Navigator's rater missed 3 of the 9 of our incidents that are in AIID; and
    305 of 1,803 AIID incidents carry no classification at all, skewed recent.

    Until 2026-11-16 the third arm was `unclassified`: no classification of any kind.
    Measured that day: 772 AIID incidents dated 2024-01-01 or later were classified
    by MIT or GMF only, so that arm skipped them, yet neither taxonomy asks the
    multi-agent question. A random sample of 100 of them, read from record text, gave
    22 that need a source read (18 `unknown`, 4 `several`). So the arm now asks
    whether anybody asked, not whether anybody classified: 361 + 772 = 1,133 queued.
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
        if sid == MANUAL or (rec.get("meta") or {}).get("manual"):
            # the curator put it here; no net needs to catch it
            rows.append({"source_id": sid, "source_record_id": rid,
                         "record_key": record_key(sid, rid),
                         "date": rec.get("date", ""), "title": rec.get("title", ""),
                         "arms": MANUAL, "label_values": "", "keyword_terms": "",
                         "url": rec.get("url", "")})
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
        if sid == MA_SOURCE and not ma_asked(rec) \
                and rec.get("date", "") >= UNCLASSIFIED_CUTOFF:
            arms.append("unasked")
        if not arms:
            continue
        rows.append({
            "source_id": sid,
            "source_record_id": rid,
            "record_key": record_key(sid, rid),
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
    by_arm = arm_counts(rows)
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


# ---------------------------------------------------------------- readiness

def load_context():
    """Newest context row per record, keyed (source_id, source_record_id)."""
    out = {}
    for path in sorted(CONTEXT.glob("*.jsonl")) if CONTEXT.exists() else []:
        for row in read_jsonl(path):
            out[row_pair(row)] = row
    return out


def is_flagged(arms):
    """A record the label or keyword arm put in the queue is flagged."""
    return bool(FLAG_ARMS & set(str(arms or "").split(";")))


def queue_flags(queue=None):
    """(source_id, source_record_id) -> flagged, for every queued record."""
    queue = read_jsonl(STATE / "queue.jsonl") if queue is None else queue
    return {row_pair(r): is_flagged(r.get("arms")) for r in queue}


def best_depth(ctx):
    return max((r.get("depth") for r in (ctx or {}).get("read") or []
                if r.get("depth") in READ_DEPTH),
               key=READ_DEPTH.index, default="unreadable")


def single_agent_said(ctx):
    """The reading says one agent only, or none."""
    return bool(ctx) and ctx.get("agent_count") in ("none", "one") \
        and ((ctx.get("facts") or {}).get("agents") or {}).get("status") == "stated"


def readiness(ctx, flagged=False):
    """Is there enough information to make each decision? One verdict per decision.

    The rule is about what has been READ, not about what was found. A source read
    in full that says nothing about a fact has answered the question: the answer
    is `unclear`, and the record is ready. A fact nobody looked for has not been
    answered, and no label may be derived from it.

      ready        the primary source was read in full and the facts are resolved
      provisional  the facts are resolved, but from a partial or secondary reading
      not_ready    a needed fact is unread, or nothing usable has been read
      not_needed   the decision does not arise (the record is out of scope)

    `flagged`: the label or keyword arm queued the record (a dossier's sources count
    as flagged). Its record text alone may not dismiss it as single-agent.
    """
    if ctx is None:
        why = "no context row: the source has not been read for the gate facts"
        return {d: {"level": "not_ready", "why": why} for d in DECISIONS}

    if ctx.get("manual") is True:
        out = {"scope": {"level": "ready",
                         "why": "added by hand: in scope on the curator's word"}}
        for d in DECISIONS[1:]:
            out[d] = {"level": "provisional",
                      "why": "to be judged from the curator's write-up"}
        return out

    depth = best_depth(ctx)
    facts = ctx.get("facts") or {}

    def status(name):
        return (facts.get(name) or {}).get("status", "unread")

    def judge(needed):
        unread = [n for n in needed if status(n) == "unread"]
        if depth == "unreadable":
            return {"level": "not_ready", "why": "the source could not be read"}
        if unread:
            return {"level": "not_ready", "why": "unread: " + ", ".join(unread)}
        if depth == "record":
            return {"level": "not_ready",
                    "why": "only the record text was read; it cannot settle this"}
        if depth == "primary_full":
            return {"level": "ready", "why": "primary source read in full"}
        return {"level": "provisional", "why": f"facts resolved from a {depth} reading"}

    out = {}
    # A source that describes one agent only, or none, is out of scope on that fact
    # alone. For an unflagged record the record text is enough. A flagged record
    # needs a reading of depth `secondary` or better to confirm it.
    if single_agent_said(ctx):
        if not flagged or READ_DEPTH.index(depth) > READ_DEPTH.index("record"):
            what = "no agent" if ctx["agent_count"] == "none" else "one agent only"
            out["scope"] = {"level": "ready", "why": f"{what} described; out of scope"}
            for d in DECISIONS[1:]:
                out[d] = {"level": "not_needed", "why": "out of scope"}
            return out
        why = (f"the record text says {ctx['agent_count']}, but a label or keyword "
               f"flagged it; read the source to confirm")
        return {d: {"level": "not_ready", "why": why} for d in DECISIONS}

    scope_needs = ["agents", "interaction"] + (["multiplicity"] if ctx.get("attack") else [])
    out["scope"] = judge(scope_needs)
    out["evidence_type"] = judge(["setting"])
    out["failure_mode"] = judge(["interaction", "cooperation", "objectives"])
    out["instances"] = judge(["mechanism"])
    return out


def out_of_scope(verdict):
    """The single-agent shortcut held: scope settled, nothing else arises."""
    return verdict["scope"]["level"] == "ready" \
        and verdict["evidence_type"]["level"] == "not_needed"


def stage_readiness():
    """Report, for every record awaiting a decision, whether it can be classified."""
    records = latest_records()
    context = load_context()
    queue = read_jsonl(STATE / "queue.jsonl")
    flags = queue_flags(queue)
    pools = {"queue": [row_pair(r) for r in queue],
             "dossiers": sorted(dossier_source_refs())}
    rows, summary = [], {}
    for pool, keys in pools.items():
        for key in keys:
            verdict = readiness(context.get(key), flagged=flags.get(key, True))
            rec = records.get(key, {})
            rows.append({"pool": pool, "source_id": key[0], "source_record_id": key[1],
                         "record_key": record_key(*key),
                         "title": rec.get("title", ""),
                         "text_chars": len(rec.get("text", "")),
                         **{d: verdict[d]["level"] for d in DECISIONS},
                         "why": verdict["scope"]["why"]})
            for d in DECISIONS:
                bucket = summary.setdefault(pool, {}).setdefault(d, {})
                bucket[verdict[d]["level"]] = bucket.get(verdict[d]["level"], 0) + 1
    STATE.mkdir(parents=True, exist_ok=True)
    write_jsonl(STATE / "readiness.jsonl", rows)
    for pool, keys in pools.items():
        info(f"  {pool}: {len(keys)} records")
        for d in DECISIONS:
            counts = summary.get(pool, {}).get(d, {})
            info(f"    {d:14s} " + "  ".join(
                f"{lvl} {counts[lvl]}" for lvl in READY_LEVELS if lvl in counts))
    info(f"  ok    readiness -> {(STATE / 'readiness.jsonl').relative_to(ROOT)}")
    return summary


# ------------------------------------------------------------------- derive
#
# Proposals hold model output only. The labels are derived from them by rule
# (derive.py), every time, into state/verdicts.jsonl: generated state, never edited
# and never written back into a proposal.

VERDICTS = "verdicts.jsonl"
INSTANCES_DUE = "instances_due.jsonl"


def proposal_rows(prompt_id):
    """Newest proposal row per record for one prompt (extract_gate, assign_instances),
    keyed (source_id, source_record_id). Files are read in name order, which is run
    date order, so a later row wins."""
    out = {}
    for path in sorted(PROPOSALS.glob(f"{prompt_id}.*.jsonl")) if PROPOSALS.exists() else []:
        for row in read_jsonl(path):
            if row.get("record_key") or row.get("source_id") is not None:
                out[row_pair(row)] = row
    return out


def stage_derive():
    """Apply the rules to the newest extract_gate proposal of every record."""
    gates = proposal_rows("extract_gate")
    rows, split = [], {s: 0 for s in rules.STATUSES}
    for (sid, rid), gate in sorted(gates.items()):
        v = rules.derive(gate, manual=(sid == MANUAL))
        split[v["status"]] += 1
        rows.append({"record_key": record_key(sid, rid), "source_id": sid,
                     "source_record_id": rid,
                     "prompt": f"{gate.get('prompt_id', '')}@{gate.get('prompt_version', '')}",
                     "run_date": gate.get("run_date", ""), **v})
    STATE.mkdir(parents=True, exist_ok=True)
    write_jsonl(STATE / VERDICTS, rows)
    presumed = sum(1 for r in rows if r["by_presumption"])
    info(f"  ok    derive: {len(rows)} verdict(s), rules {rules.RULES_VERSION} -> "
         f"{(STATE / VERDICTS).relative_to(ROOT)}")
    info(f"          in scope {split['in_scope']}  out of scope {split['out_of_scope']}  "
         f"review {split['review']}  (of the review items, {presumed} would be in scope "
         f"only by the attack presumption if a person confirms them)")
    return split


def read_verdicts():
    """state/verdicts.jsonl, keyed (source_id, source_record_id)."""
    return {row_pair(r): r for r in read_jsonl(STATE / VERDICTS)}


def instances_due():
    """Records a person, or the rules, have put in scope that have no instance
    proposal. One row per record:

      dossier  a dossier with multi_agent true and label source `ours`, an empty
               `instances` list, and no assign_instances proposal for any of its
               sources. The record named is its canonical source's.
      verdict  a record derive settled in_scope, with no assign_instances proposal,
               and no dossier that already lists instances.
    """
    have = set(proposal_rows("assign_instances"))
    out, seen, listed = [], set(), set()
    for path in all_dossiers():
        meta, _ = read_dossier(path)
        refs = [(s.get("source_id"), str(s.get("record_id")))
                for s in meta.get("sources") or []]
        if meta.get("instances"):
            listed.update(refs)
        if meta.get("multi_agent") is not True \
                or meta.get("multi_agent_label_source") != "ours" \
                or meta.get("instances") or not refs or any(r in have for r in refs):
            continue
        key = next((r for r in refs if r[0] == meta.get("canonical_source")), refs[0])
        seen.update(refs)
        out.append({"record_key": record_key(*key), "source_id": key[0],
                    "source_record_id": key[1], "why": "dossier",
                    "dossier": meta.get("id", path.stem)})
    for key, v in sorted(read_verdicts().items()):
        if v.get("status") != "in_scope" or key in have or key in seen or key in listed:
            continue
        out.append({"record_key": record_key(*key), "source_id": key[0],
                    "source_record_id": key[1], "why": "verdict", "dossier": ""})
    return out


def stage_instances_due():
    rows = instances_due()
    STATE.mkdir(parents=True, exist_ok=True)
    write_jsonl(STATE / INSTANCES_DUE, rows)
    info(f"  ok    instances-due: {len(rows)} record(s) in scope with no instance "
         f"proposal -> {(STATE / INSTANCES_DUE).relative_to(ROOT)}")
    for r in rows:
        why = f"dossier {r['dossier']}" if r["why"] == "dossier" else "derived in scope"
        info(f"          {r['record_key']:28s} {why}")
    return rows


# ------------------------------------------------------------------ promote

def stage_promote(refs, force=False):
    records = latest_records()
    context = load_context()
    made = []
    for ref in refs:
        if ":" not in ref:
            die(f"promote takes a record_key, <source_id>:<record_id>, got {ref!r}")
        sid, rid = split_key(ref)
        rec = records.get((sid, rid))
        if rec is None:
            die(f"no record {ref}; run normalise first")
        flagged = queue_flags().get((sid, rid), True)
        scope = readiness(context.get((sid, rid)), flagged=flagged)["scope"]
        if scope["level"] == "not_ready" and not force:
            die(f"{ref} is not ready to classify ({scope['why']}). Enrich it first - "
                f"see mvp/docs/context_layer.md - or pass --force to scaffold anyway.")
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
            "instances_presumed": [],
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
    rows = index_rows()
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


def index_rows():
    """One row per dossier, as the index table prints it."""
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
            "instances_presumed": ";".join(meta.get("instances_presumed") or []),
            "verification": meta.get("verification", ""),
            "first_seen": meta.get("first_seen", ""),
            "last_verified": meta.get("last_verified") or "",
            "path": str(path.relative_to(ROOT)),
        })
    rows.sort(key=lambda r: (r["occurrence_date"], r["id"]))
    return rows


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

    queue_arms = arm_counts(queue)

    return {
        "generated": TODAY,
        "map": pipeline_map(reg, records, queue, proposals, index_rows),
        # The old workflow page draws `modes` as stage lists; the modes are gone, and
        # what an update visits depends only on --discover.
        "modes": {
            "update": ["sources", "records", "prefilter", "classify", "review",
                       "dossiers", "index"],
            "update --discover": ["sources", "records", "discover", "prefilter",
                                  "classify", "review", "dossiers", "index"],
        },
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
                                           and r["adapter"] not in ("work_order", MANUAL)),
                        "manual": sum(1 for r in reg.values() if r["adapter"] == MANUAL),
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
                   ("source_id", "source_record_id", "record_key", "date", "title", "arms",
                    "label_values", "keyword_terms", "url")} for row in queue],
        "registry": [{"source_id": r["source_id"], "name": r["name"],
                      "role": r["role"], "access_method": r["access_method"],
                      "adapter": r["adapter"], "status": r["status"],
                      "external_ma_label": r["external_ma_label"],
                      "reuse_status": r["reuse_status"]}
                     for r in sorted(reg.values(), key=lambda x: (x["role"], x["source_id"]))],
    }


# Where each step of the dataflow map keeps what it makes. Paths are relative to mvp/.
# The map links to them, and marks any that do not exist yet.
MAP_ARTIFACTS = {
    "sources": [("The list of sources", "registry/sources.csv")],
    "discover": [("Where its finds would be saved", "raw/")],
    "fetch": [("Exact copies, as downloaded", "raw/aiid/")],
    "orders": [("The to-do notes", "state/work_orders.md")],
    "manual": [("Your write-ups, copied as given", "raw/manual/"),
               ("Their records", "records/manual.jsonl"),
               ("The curator's flag on each", "context/manual.jsonl")],
    "normalise": [("Records, one file per source", "records/")],
    "prefilter": [("The queue of candidates", "state/queue.jsonl")],
    "notqueued": [("The records, one file per source", "records/"),
                  ("The queue they are not in", "state/queue.jsonl")],
    "outscope": [("The readings that settled it", "context/"),
                 ("The readiness report", "state/readiness.jsonl")],
    "readrec": [("Readings, one file per source", "context/"),
                ("The instructions the model follows", "prompts/enrich_context.v2.md")],
    "readsrc": [("Readings, one file per source", "context/"),
                ("The instructions the model follows", "prompts/enrich_context.v2.md")],
    "ready": [("The readiness report", "state/readiness.jsonl"),
              ("How the rule works", "docs/context_layer.md")],
    "taxonomy": [("The definitions", "docs/definitions.md"),
                 ("Risks, patterns and their links", "taxonomy/")],
    "extract": [("The instructions the model follows", "prompts/extract_gate.v3.md"),
                ("Where its output will be saved", "proposals/")],
    "gate1": [("The written rule", "docs/definitions.md"),
              ("The rule in code", "pipeline/derive.py"),
              ("Where its answers are saved", "state/verdicts.jsonl")],
    "gate2": [("The written rule", "docs/definitions.md"),
              ("The rule in code", "pipeline/derive.py"),
              ("Where its answers are saved", "state/verdicts.jsonl")],
    "evtype": [("The four evidence types", "taxonomy/evidence_types.csv"),
               ("The rule in code", "pipeline/derive.py"),
               ("Where its answers are saved", "state/verdicts.jsonl")],
    "instances": [("The named patterns", "taxonomy/instances.csv"),
                  ("The instructions the model follows", "prompts/assign_instances.v2.md"),
                  ("Where its output will be saved", "proposals/"),
                  ("Records in scope still without one", "state/instances_due.jsonl")],
    "proposals": [("The suggestions", "proposals/")],
    "review": [("The incident files a person writes", "incidents/")],
    "dossiers": [("The incident files", "incidents/")],
    "check": [("The program that runs the check", "pipeline/run.py")],
    "index": [("The finished table", "out/incident_index.csv")],
    "gold": [("The answer key", "gold/multiagent_gold.csv"),
             ("The worksheet used to judge it", "out/gold_review.html")],
    "score": [("The latest scores", "out/gate1_accuracy.json"),
              ("How to read them", "docs/gate1_accuracy.md")],
}


def queue_stage(row, ctx):
    """Where one queued record stands on the map's path, by the readiness rule.

      bypass        added by hand and ready on the curator's word: skips the reads
      unread        no reading at all: waits at "Read the record"
      oos_record    out of scope on its record text (unflagged, one agent or none)
      oos_source    out of scope on a reading deeper than the record
      wait_source   read at record depth only (or unreadable), not settled: waits
                    at "Read the source"
      unresolved    read deeper than the record, but a needed fact is still unread
      ready         scope ready or provisional: ready to judge
    """
    verdict = readiness(ctx, flagged=is_flagged(row.get("arms")))
    level = verdict["scope"]["level"]
    if MANUAL in row_arms(row) and level in ("ready", "provisional") \
            and not out_of_scope(verdict):
        return "bypass", verdict
    if ctx is None:
        return "unread", verdict
    deeper = READ_DEPTH.index(best_depth(ctx)) > READ_DEPTH.index("record")
    if out_of_scope(verdict):
        return ("oos_source" if deeper else "oos_record"), verdict
    if not deeper:
        return "wait_source", verdict
    if level in ("ready", "provisional"):
        return "ready", verdict
    return "unresolved", verdict


def map_flow(reg, records, queue, context, index_rows):
    """The record flow the map draws: one population, records, over all sources.

    Returns (nodes, checks, counts). Each node: `n` (its headline count), `in`, `out`
    (edges {to, n, label, branch}), `stop` (what ends here, finished), `held` (what
    waits here), `by_source` (the node's records per source), `groups` (breakdowns),
    `files` and `rule` (where the number comes from). A branch edge sends the same
    records on a second, descriptive path: it is not part of its source's split.
    `checks` lists every conservation equation with both sides."""
    def by_source(keys):
        out = {}
        for sid, _ in keys:
            out[sid] = out.get(sid, 0) + 1
        return dict(sorted(out.items()))

    def rows(*pairs):
        return [{"label": p[0], "n": p[1], "tech": p[2] if len(p) > 2 else ""}
                for p in pairs]

    allkeys = set(records)
    manual_keys = {k for k in allkeys if k[0] == MANUAL
                   or ((records[k].get("meta") or {}).get("manual"))}
    fetched = allkeys - manual_keys
    attested = dossier_source_refs() & allkeys
    qrows = {row_pair(r): r for r in queue if row_pair(r) in allkeys}
    queued = set(qrows)
    to_dossier = attested - queued
    not_queued = allkeys - queued - to_dossier

    stage, verdicts_r = {}, {}
    for key, row in qrows.items():
        stage[key], verdicts_r[key] = queue_stage(row, context.get(key))
    at = lambda *names: {k for k, s in stage.items() if s in names}
    bypass = at("bypass")
    to_readrec = queued - bypass
    unread = at("unread")
    oos_record, oos_source = at("oos_record"), at("oos_source")
    wait_source, unresolved = at("wait_source"), at("unresolved")
    read_any = to_readrec - unread
    to_readsrc = read_any - oos_record
    src_ready = at("ready")
    read_deeper = to_readsrc - wait_source
    ready = src_ready | bypass

    gates = proposal_rows("extract_gate")
    extracted = {k for k in ready if k in gates}
    verdicts = read_verdicts()
    derived = {k for k in extracted if (verdicts.get(k) or {}).get("status") in rules.STATUSES}
    status_of = {k: verdicts[k]["status"] for k in derived}
    promoted = derived & attested
    waiting_person = derived - promoted
    early = (queued & attested) - promoted     # promoted before reaching review

    # dossier facts, per record
    dossier_of, dmeta = {}, {}
    for path in all_dossiers():
        meta, _ = read_dossier(path)
        dmeta[meta.get("id", path.stem)] = meta
        for s in meta.get("sources") or []:
            dossier_of[(s.get("source_id"), str(s.get("record_id")))] = meta.get("id", path.stem)
    in_dossiers = to_dossier | promoted
    scope_word = {True: "in", False: "out"}
    d_scope = {"in": 0, "out": 0, "unclear": 0}
    d_ver = {}
    for k in in_dossiers:
        meta = dmeta.get(dossier_of.get(k), {})
        d_scope[scope_word.get(meta.get("multi_agent"), "unclear")] += 1
        v = meta.get("verification") or "not set"
        d_ver[v] = d_ver.get(v, 0) + 1

    # instances: a branch, fed by records in scope, by the rules or by a person
    inst = proposal_rows("assign_instances")
    by_rule = {k for k, s in status_of.items() if s == "in_scope"} - attested
    by_person = {k for k in in_dossiers
                 if dmeta.get(dossier_of.get(k), {}).get("multi_agent") is True
                 and dmeta.get(dossier_of.get(k), {}).get("multi_agent_label_source") == "ours"}
    in_scope = by_rule | by_person
    has_inst = {k for k in in_scope if k in inst}
    listed = {k for k in in_scope - has_inst
              if dmeta.get(dossier_of.get(k), {}).get("instances")}
    due = in_scope - has_inst - listed
    due_rows = len(instances_due())

    def agent_count(k):
        return (context.get(k) or {}).get("agent_count") or "not said"

    depth_rows = {}
    for k in read_deeper:
        d = best_depth(context.get(k))
        depth_rows[d] = depth_rows.get(d, 0) + 1
    DEPTH_WORDS = {"secondary": "an aggregator's page, read in full",
                   "curator": "the curator's own write-up",
                   "primary_partial": "the original source, read in part",
                   "primary_full": "the original source, read in full"}
    conf = {}
    for k in extracted:
        c = gates[k].get("confidence") or "not given"
        conf[c] = conf.get(c, 0) + 1
    arms = {}
    for k in queued:
        for a in row_arms(qrows[k]):
            arms[a] = arms.get(a, 0) + 1
    flagged = sum(1 for k in queued if is_flagged(qrows[k].get("arms")))
    levels = {}
    for k in src_ready:
        lv = verdicts_r[k]["scope"]["level"]
        levels[lv] = levels.get(lv, 0) + 1
    STATUS_WORDS = {"in_scope": "settled in scope by the rules",
                    "out_of_scope": "settled out of scope by the rules",
                    "review": "needs a person"}
    split = {s: sum(1 for k in derived if status_of[k] == s) for s in rules.STATUSES}
    presumed = sum(1 for k in derived if verdicts[k].get("by_presumption"))

    E = lambda to, keys, label, branch=False: {"to": to, "n": len(keys), "label": label,
                                               "branch": branch}
    nodes = [
        {"id": "fetch", "n": len(fetched), "origin": True, "in": len(fetched),
         "out": [E("normalise", fetched, "records collected")], "stop": [], "held": 0,
         "pop": fetched,
         "groups": [{"title": "Records per source", "rows": rows(
             *[(f"{sid}", n, f"records/{sid}.jsonl") for sid, n in by_source(fetched).items()])}],
         "files": ["raw/aiid/", "records/<source>.jsonl"],
         "rule": "records of every source but manual: latest_records()"},
        {"id": "manual", "n": len(manual_keys), "origin": True, "in": len(manual_keys),
         "out": [E("normalise", manual_keys, "added by hand")], "stop": [], "held": 0,
         "pop": manual_keys, "groups": [],
         "files": ["raw/manual/", "records/manual.jsonl"],
         "rule": "records with source_id manual or meta.manual"},
        {"id": "normalise", "n": len(allkeys), "in": len(allkeys),
         "out": [E("prefilter", allkeys, "records")], "stop": [], "held": 0,
         "pop": allkeys, "groups": [],
         "files": ["records/<source>.jsonl"],
         "rule": "newest version of every (source_id, source_record_id): latest_records()"},
        {"id": "prefilter", "n": len(queued), "in": len(allkeys),
         "out": [E("dossiers", to_dossier, "already in a dossier"),
                 E("readrec", to_readrec, "candidates"),
                 E("ready", bypass, "added by hand: on the curator's word"),
                 E("notqueued", not_queued, "not queued")],
         "stop": [], "held": 0, "pop": allkeys,
         "groups": [
             {"title": "Candidates per source", "rows": rows(
                 *[(sid, n, "state/queue.jsonl") for sid, n in by_source(queued).items()])},
             {"title": "Every record goes one of three ways", "rows": rows(
                 ("Already in a dossier: a dossier lists it as a source", len(to_dossier),
                  "dossier_source_refs() and not in state/queue.jsonl"),
                 ("Queued as a candidate", len(queued), "row in state/queue.jsonl"),
                 ("Not queued: no rule caught it", len(not_queued),
                  "neither in the queue nor behind a dossier"))},
             {"title": "Why each candidate was queued",
              "note": "A record can be caught by several rules, so these add up to more than the candidates.",
              "rows": rows(
                  ("Tagged multi-agent by someone else", arms.get("label", 0), "arm label"),
                  ("Matched a keyword", arms.get("keyword", 0), "arm keyword"),
                  ("Unasked: nobody asked the multi-agent question", arms.get("unasked", 0),
                   f"arm unasked: AIID, dated {UNCLASSIFIED_CUTOFF} or later, no {MA_FIELD} label"),
                  ("Added by hand", arms.get(MANUAL, 0), "arm manual"))},
             {"title": "Flagged", "rows": rows(
                 ("Flagged by a tag or a keyword: never dismissed on the record text alone",
                  flagged, "is_flagged(arms): label or keyword"),
                 ("Not flagged", len(queued) - flagged, ""))}],
         "files": ["state/queue.jsonl", "incidents/"],
         "rule": "stage_prefilter(): union of the label, keyword and unasked arms; records behind a dossier are left out"},
        {"id": "notqueued", "n": len(not_queued), "in": len(not_queued), "out": [],
         "stop": [{"label": "no rule caught it", "n": len(not_queued)}], "held": 0,
         "pop": not_queued, "groups": [],
         "files": ["records/<source>.jsonl", "state/queue.jsonl"],
         "rule": "records neither in state/queue.jsonl nor behind a dossier"},
        {"id": "readrec", "n": len(read_any), "in": len(to_readrec),
         "out": [E("outscope", oos_record, "out of scope: record text"),
                 E("readsrc", to_readsrc, "sent on to the source")],
         "stop": [], "held": len(unread), "held_label": "not read yet",
         "pop": to_readrec,
         "groups": [{"title": "Read so far", "rows": rows(
             ("Read: there is a reading", len(read_any), "a row in context/<source>.jsonl"),
             ("Not read yet", len(unread), "no context row"))},
             {"title": "What the reading of the record settled", "rows": rows(
                 ("Out of scope: one agent or none, and not flagged", len(oos_record),
                  "out_of_scope(readiness()) at depth record"),
                 ("Sent on: several agents, cannot tell, or flagged", len(to_readsrc),
                  "every other read record, including those already read deeper"))}],
         "files": ["context/<source>.jsonl", "state/queue.jsonl"],
         "rule": "queued records, not added by hand; read = has a context row"},
        {"id": "readsrc", "n": len(read_deeper), "in": len(to_readsrc),
         "out": [E("outscope", oos_source, "out of scope: confirmed"),
                 E("ready", src_ready, "ready to judge")],
         "stop": [], "held": len(wait_source) + len(unresolved),
         "held_label": "waiting for a source reading",
         "pop": to_readsrc,
         "groups": [{"title": "Source read, by how deep", "rows": rows(
             *[(DEPTH_WORDS.get(d, d), n, d) for d, n in
               sorted(depth_rows.items(), key=lambda x: READ_DEPTH.index(x[0]))])},
             {"title": "Waiting here", "rows": rows(
                 ("Only the record text has been read", len(wait_source),
                  "best_depth() record or unreadable, not out of scope"),
                 ("Read deeper, but a needed fact is still unread", len(unresolved),
                  "readiness() scope not_ready at depth above record"))}],
         "files": ["context/<source>.jsonl"],
         "rule": "best_depth() above record: secondary, curator, primary_partial or primary_full"},
        {"id": "outscope", "n": len(oos_record) + len(oos_source),
         "in": len(oos_record) + len(oos_source), "out": [],
         "stop": [{"label": "out of scope", "n": len(oos_record) + len(oos_source)}],
         "held": 0, "pop": oos_record | oos_source,
         "groups": [{"title": "Why, and on what reading", "rows": rows(
             ("No agent, on the record text", sum(1 for k in oos_record if agent_count(k) == "none"),
              "agent_count none, depth record"),
             ("One agent, on the record text", sum(1 for k in oos_record if agent_count(k) == "one"),
              "agent_count one, depth record"),
             ("No agent, confirmed from a source", sum(1 for k in oos_source if agent_count(k) == "none"),
              "agent_count none, depth above record"),
             ("One agent, confirmed from a source", sum(1 for k in oos_source if agent_count(k) == "one"),
              "agent_count one, depth above record"))}],
         "files": ["context/<source>.jsonl", "state/readiness.jsonl"],
         "rule": "out_of_scope(readiness()): agents stated, agent_count one or none"},
        {"id": "ready", "n": len(ready), "in": len(ready),
         "out": [E("extract", ready, "ready to judge")], "stop": [], "held": 0,
         "pop": ready,
         "groups": [{"title": "How firm", "rows": rows(
             ("Original source read in full", levels.get("ready", 0), "scope ready"),
             ("Facts from a partial or secondary reading", levels.get("provisional", 0),
              "scope provisional"),
             ("Added by hand: in scope on the curator's word", len(bypass), "arm manual"))}],
         "files": ["state/readiness.jsonl"],
         "rule": "readiness() scope ready or provisional, not out of scope"},
        {"id": "extract", "n": len(extracted), "in": len(ready),
         "out": [E("gate1", extracted, "facts extracted")], "stop": [],
         "held": len(ready - extracted), "held_label": "no facts extracted yet",
         "pop": ready,
         "groups": [{"title": "Model's confidence", "rows": rows(
             *[(c, n, f"confidence {c}") for c, n in sorted(conf.items())])}],
         "files": ["proposals/extract_gate.<date>.jsonl"],
         "rule": "distinct ready records with an extract_gate proposal: proposal_rows('extract_gate')"},
        {"id": "gate1", "n": len(derived), "in": len(extracted),
         "out": [E("review", derived, "labels derived"),
                 E("instances", by_rule, "in scope by the rules", True)],
         "stop": [], "held": len(extracted - derived), "held_label": "derive not run on it yet",
         "pop": extracted,
         "groups": [{"title": "What the rules settled", "rows": rows(
             *[(STATUS_WORDS[s], split[s], f"status {s}") for s in rules.STATUSES])},
             {"title": "Of which", "rows": rows(
                 ("In scope by the attack presumption", presumed, "by_presumption true"))}],
         "files": ["state/verdicts.jsonl", "pipeline/derive.py"],
         "rule": f"state/verdicts.jsonl, rules {rules.RULES_VERSION}"},
        {"id": "review", "n": len(derived), "in": len(derived),
         "out": [E("dossiers", promoted, "promoted to a dossier")], "stop": [],
         "held": len(waiting_person), "held_label": "waiting for a person",
         "pop": derived,
         "groups": [{"title": "By what the rules said", "rows": rows(
             *[(STATUS_WORDS[s], split[s], f"status {s}") for s in rules.STATUSES])},
             {"title": "Status", "rows": rows(
                 ("A person has written a dossier", len(promoted), "listed in a dossier's sources"),
                 ("Waiting for a person", len(waiting_person), "no dossier yet"))}],
         "files": ["state/verdicts.jsonl", "incidents/"],
         "rule": "records with a derived label; promoted = a dossier lists the record"},
        {"id": "dossiers", "n": len(in_dossiers), "in": len(in_dossiers),
         "out": [E("check", in_dossiers, "checked"),
                 E("instances", by_person, "in scope by a person", True)],
         "stop": [], "held": 0, "pop": in_dossiers,
         "groups": [{"title": "The person's verdict", "rows": rows(
             ("In scope", d_scope["in"], "multi_agent: true"),
             ("Out of scope", d_scope["out"], "multi_agent: false"),
             ("Unclear", d_scope["unclear"], "multi_agent: null"))},
             {"title": "How well checked", "rows": rows(
                 *[(v.replace("_", " "), n, f"verification {v}") for v, n in sorted(d_ver.items())])},
             {"title": "Files", "rows": rows(
                 ("Dossiers: one file can list several records", len(index_rows), "incidents/<ID>.md"))}],
         "files": ["incidents/"],
         "rule": "records listed in a dossier's sources"},
        {"id": "check", "n": len(in_dossiers), "in": len(in_dossiers),
         "out": [E("index", in_dossiers, "passed on")], "stop": [], "held": 0,
         "pop": in_dossiers, "groups": [],
         "files": ["pipeline/run.py"], "rule": "run.py check validates every dossier"},
        {"id": "index", "n": len(in_dossiers), "in": len(in_dossiers), "out": [],
         "stop": [{"label": "in the finished table", "n": len(in_dossiers)}], "held": 0,
         "pop": in_dossiers,
         "groups": [{"title": "Table", "rows": rows(
             ("Rows: one per dossier", len(index_rows), "out/incident_index.csv"))}],
         "files": ["out/incident_index.csv"], "rule": "index_rows(): one row per dossier"},
        {"id": "instances", "n": len(has_inst), "in": len(in_scope), "out": [],
         "stop": [{"label": "patterns proposed", "n": len(has_inst)},
                  {"label": "patterns already in the dossier", "n": len(listed)}],
         "held": len(due), "held_label": "in scope, no pattern yet",
         "pop": in_scope,
         "groups": [{"title": "Records in scope", "rows": rows(
             ("In scope by the rules, no dossier yet", len(by_rule), "verdict in_scope"),
             ("In scope by a person", len(by_person), "dossier multi_agent true, ours"))},
             {"title": "Of which", "rows": rows(
                 ("A pattern was proposed", len(has_inst), "assign_instances proposal"),
                 ("The dossier already lists patterns", len(listed), "dossier instances"),
                 ("No pattern yet", len(due), "neither"),
                 ("Rows in the to-do list (one per dossier, not per record)", due_rows,
                  "state/instances_due.jsonl"))}],
         "files": ["proposals/assign_instances.<date>.jsonl", "state/instances_due.jsonl"],
         "rule": "proposal_rows('assign_instances') over records in scope"},
    ]
    for nd in nodes:
        nd["by_source"] = by_source(nd.pop("pop"))
        nd.setdefault("held_label", "")

    # conservation: per node, and the splits that the map states in words
    checks = []

    def check(text, lhs, rhs):
        checks.append({"eq": text, "lhs": lhs, "rhs": rhs, "ok": lhs == rhs})

    incoming = {}
    for nd in nodes:
        for e in nd["out"]:
            incoming[e["to"]] = incoming.get(e["to"], 0) + e["n"]
    for nd in nodes:
        if not nd.get("origin"):
            check(f"{nd['id']}: in = sum of the edges into it", nd["in"],
                  incoming.get(nd["id"], 0))
        outs = sum(e["n"] for e in nd["out"] if not e["branch"])
        stops = sum(s["n"] for s in nd["stop"])
        check(f"{nd['id']}: in = out + ends here + waiting", nd["in"],
              outs + stops + nd["held"])
        check(f"{nd['id']}: by source adds up", sum(nd["by_source"].values()), nd["in"])
    check("records = already in a dossier + queued + not queued", len(allkeys),
          len(to_dossier) + len(queued) + len(not_queued))
    check("queued = sent to reading + added by hand", len(queued),
          len(to_readrec) + len(bypass))
    check("read the record = read + not read yet", len(to_readrec),
          len(read_any) + len(unread))
    check("derived = in scope + out of scope + needs a person", len(derived),
          sum(split.values()))
    check("in scope = proposed + already listed + waiting", len(in_scope),
          len(has_inst) + len(listed) + len(due))
    check("dossier verdicts add up", len(in_dossiers), sum(d_scope.values()))
    # fails when a queued record got a dossier before reaching review: rerun prefilter
    check("records behind a dossier = the Dossiers box", len(attested), len(in_dossiers))

    counts = {"records": len(allkeys), "queued": len(queued),
              "not_queued": len(not_queued), "in_dossier_already": len(to_dossier),
              "read_record": len(read_any), "read_source": len(read_deeper),
              "out_of_scope": len(oos_record) + len(oos_source), "ready": len(ready),
              "extracted": len(extracted), "derived": len(derived),
              "dossier_records": len(in_dossiers), "in_scope": len(in_scope),
              "instance_records": len(has_inst), "promoted_early": len(early)}
    return nodes, checks, counts


def pipeline_map(reg, records, queue, proposals, index_rows):
    """The numbers the dataflow map (mvp/pipeline/pipeline_patch.html) prints. Every
    count on the map is a number of records; `flow` carries them and `checks` the
    equations that must hold. See map_flow."""
    context = load_context()
    flow, checks, counts = map_flow(reg, records, queue, context, index_rows)
    arms = arm_counts(queue)
    verdicts = {s: 0 for s in rules.STATUSES}
    for v in read_verdicts().values():
        if v.get("status") in verdicts:
            verdicts[v["status"]] += 1
    scope = {"in": 0, "out": 0, "unclear": 0}
    verification, failure_modes = {}, {}
    for path in all_dossiers():
        meta, _ = read_dossier(path)
        key = {True: "in", False: "out"}.get(meta.get("multi_agent"), "unclear")
        scope[key] += 1
        v = meta.get("verification", "")
        verification[v] = verification.get(v, 0) + 1
        fm = meta.get("failure_mode") or "none"
        if key == "in":
            failure_modes[fm] = failure_modes.get(fm, 0) + 1
    gold = {"rows": 0, "in": 0, "out": 0, "unclear": 0, "ceiling": None}
    gold_path = MVP / "gold" / "multiagent_gold.csv"
    if gold_path.exists():
        for row in read_csv(gold_path):
            gold["rows"] += 1
            if row.get("review_verdict") in gold:
                gold[row["review_verdict"]] += 1
    acc = OUT / "gate1_accuracy.json"
    if acc.exists():
        ceiling = json.loads(acc.read_text(encoding="utf-8"))["predictors"].get(
            "ceiling_hand_curation") or {}
        gold["ceiling"] = ceiling.get("precision")
        gold["ceiling_n"] = ceiling.get("n")
    per_source = {}
    for (sid, _rid) in records:
        per_source[sid] = per_source.get(sid, 0) + 1
    return {
        "sources": len(reg),
        "sources_fetchable": sum(1 for r in reg.values()
                                 if r["role"] != "reference" and r["adapter"] != MANUAL),
        "sources_reference": sum(1 for r in reg.values() if r["role"] == "reference"),
        "sources_automatic": sum(1 for r in reg.values() if r["adapter"] == "aiid"),
        "sources_by_hand": sum(1 for r in reg.values() if r["adapter"] == "work_order"),
        "sources_unbuilt": sum(1 for r in reg.values()
                               if r["adapter"] in ("forummagnum", "companyscope")),
        "records": len(records), "records_by_source": per_source,
        "queue": len(queue), "queue_arms": arms,
        "flow": flow, "checks": checks, "flow_counts": counts,
        "sources_with_records": len(per_source),
        "manual": per_source.get(MANUAL, 0),
        "prefilter_rules": {
            "keywords": list(KEYWORD_TERMS), "cutoff": UNCLASSIFIED_CUTOFF,
            "label_values": sorted(MA_POSITIVE),
            "where": f"mvp/pipeline/run.py:{inspect.getsourcelines(stage_prefilter)[1]}"},
        "aiid_snapshot": aiid_snapshot(),
        "gate_proposals": len(proposal_rows("extract_gate")),
        "instance_proposals": len(proposal_rows("assign_instances")),
        "verdicts": verdicts,
        "verdicts_rules": rules.RULES_VERSION,
        "instances_due": len(instances_due()),
        "dossiers": len(all_dossiers()), "dossier_scope": scope,
        "dossier_verification": verification, "dossier_failure_modes": failure_modes,
        "risks": len(read_csv(TAXONOMY / "risks.csv")),
        "instances": len(read_csv(TAXONOMY / "instances.csv")),
        "gold": gold,
        "artifacts": {node: [{"label": label, "path": path,
                              "exists": (MVP / path).exists()}
                             for label, path in items]
                      for node, items in MAP_ARTIFACTS.items()},
    }


def aiid_snapshot():
    """Is there an AIID snapshot to reuse, from when, and how big."""
    src = RAW / "aiid"
    path = src / "incidents.jsonl"
    if not path.exists():
        return {"present": False, "fetched": "", "records": 0}
    with open(path, encoding="utf-8") as f:
        n = sum(1 for line in f if line.strip())
    fetched = aiid_fetched_at(src) if (src / "FETCHED.md").exists() else ""
    return {"present": True, "fetched": fetched, "records": n}


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

        presumed = meta.get("instances_presumed") or []
        if not isinstance(presumed, list):
            problems.append(f"{rel}: instances_presumed must be a list")
            presumed = []
        if presumed:
            if set(presumed) != PRESUMABLE_INSTANCES or len(presumed) != 2:
                problems.append(f"{rel}: instances_presumed is {presumed!r}; it is either "
                                f"empty or exactly I28 and I29, the pair an attack with "
                                f"unreported multiplicity is presumed to show")
            if meta.get("multi_agent") is not True:
                problems.append(f"{rel}: instances_presumed is set but multi_agent is not "
                                f"true; the presumption applies only to in-scope attacks")
            if meta.get("failure_mode"):
                problems.append(f"{rel}: instances_presumed is set alongside failure_mode "
                                f"{meta.get('failure_mode')!r}; an attack admitted by the "
                                f"presumption carries no failure mode")
            overlap = sorted(set(presumed) & set(meta.get("instances") or []))
            if overlap:
                problems.append(f"{rel}: {overlap} is both quoted and presumed; a quoted "
                                f"I28 or I29 replaces the presumed pair")

        for key in meta:
            if re.fullmatch(r"e[1-5](_.*)?", str(key)):
                problems.append(f"{rel}: {key!r} is an evidence score; "
                                f"scoring is parked and no score belongs in a dossier")

        for name in SECTIONS:
            if not re.search(rf"^## {re.escape(name)}\s*$", body, re.M):
                problems.append(f"{rel}: missing section '## {name}'")

    # --- keys, hashes and provenance on every file row ---------------------
    problems.extend(check_rows())

    # --- the context layer -------------------------------------------------
    context = load_context()
    for (sid, rid), ctx in sorted(context.items()):
        where = f"mvp/context/{sid}.jsonl {rid}"
        if (sid, rid) not in records:
            problems.append(f"{where}: no such record")
        if ctx.get("agent_count") not in AGENT_COUNTS:
            problems.append(f"{where}: agent_count {ctx.get('agent_count')!r} "
                            f"not in {AGENT_COUNTS}")
        if not ctx.get("read"):
            problems.append(f"{where}: no `read` entry; a context row records a reading")
        for r in ctx.get("read") or []:
            if r.get("depth") not in READ_DEPTH:
                problems.append(f"{where}: read depth {r.get('depth')!r} not in {READ_DEPTH}")
            elif r.get("depth") == "curator" and ctx.get("manual") is not True:
                problems.append(f"{where}: read depth 'curator' belongs to a manual row; "
                                f"this row has no `manual: true`")
        method = str((ctx.get("provenance") or {}).get("method", ""))
        if "manual" in ctx:
            rec = records.get((sid, rid)) or {}
            if ctx["manual"] is not True:
                problems.append(f"{where}: manual is {ctx['manual']!r}; it is true or absent")
            elif sid != MANUAL or not (rec.get("meta") or {}).get("manual"):
                problems.append(f"{where}: manual is true but the record is not a "
                                f"manual record")
            elif method != "manual":
                problems.append(f"{where}: a manual row has provenance method "
                                f"{method!r}, not 'manual'")
        for name in CONTEXT_FACTS:
            f = (ctx.get("facts") or {}).get(name)
            if f is None or f.get("status") not in FACT_STATUS:
                problems.append(f"{where}: fact {name!r} is missing or has no valid status")
            elif (f["status"] == "stated" and not f.get("quote")
                  and not method.startswith("seeded:") and method != "manual"):
                problems.append(f"{where}: fact {name!r} is stated with no quote")

    # A verdict needs a reading behind it. A dossier that asserts scope either way
    # must rest on a source read for the gate facts.
    warnings = []
    for path in all_dossiers():
        meta, _ = read_dossier(path)
        if meta.get("multi_agent") not in (True, False):
            continue
        ctxs = [context.get((s.get("source_id"), str(s.get("record_id"))))
                for s in meta.get("sources") or []]
        levels = [readiness(c, flagged=True)["scope"] for c in ctxs]
        best = min((READY_LEVELS.index(v["level"]) for v in levels), default=2)
        rel = path.relative_to(ROOT)
        deepest = max((best_depth(c) for c in ctxs if c),
                      key=READ_DEPTH.index, default="unreadable")
        if deepest == "curator" and meta.get("verification") == "verified":
            problems.append(f"{rel}: verification is 'verified' but the deepest reading "
                            f"behind it is the curator's own write-up; read the primary "
                            f"source or lower the verification")
        if READY_LEVELS[best] == "not_ready":
            problems.append(f"{rel}: multi_agent is {meta.get('multi_agent')} but no source "
                            f"has been read far enough to decide scope "
                            f"({levels[0]['why'] if levels else 'no sources'})")
        elif READY_LEVELS[best] == "provisional" and meta.get("verification") == "verified":
            problems.append(f"{rel}: verification is 'verified' but scope rests on a partial "
                            f"or secondary reading; read the primary source in full or "
                            f"lower the verification")
        elif READY_LEVELS[best] == "provisional":
            warnings.append(f"{rel}: scope rests on a partial or secondary reading")
    for wline in warnings:
        info(f"  warn  {wline}")

    if problems:
        for p in problems:
            info(f"  FAIL  {p}")
        info(f"check failed: {len(problems)} problem(s) over "
             f"{len(all_dossiers())} dossier(s)")
        return 1
    info(f"  ok    check: {len(all_dossiers())} dossiers, no problems")
    return 0


RAW_REF_KEYS = ("path", "id_field", "id", "fetched_at")


def check_rows():
    """Every record row: a record_key that matches its pair, a raw_ref, a content_hash
    that is record_hash of its substance, and no version identical to the one before.
    Every queue, readiness, verdict and instances-due row: a record_key that matches its
    pair. Every context and proposal row: a record_key, if it has one, that matches it. A context or proposal row a skill wrote without one is allowed;
    run.py falls back on the pair."""
    problems = []

    def key_ok(where, row, required):
        if "record_key" not in row:
            if required:
                problems.append(f"{where}: no record_key")
            return
        if row.get("source_id") is None or row.get("source_record_id") is None:
            return
        want = record_key(row["source_id"], row["source_record_id"])
        if row["record_key"] != want:
            problems.append(f"{where}: record_key {row['record_key']!r} does not match "
                            f"its source_id and source_record_id ({want!r})")

    for path in sorted(RECORDS.glob("*.jsonl")) if RECORDS.exists() else []:
        last = {}
        for n, row in enumerate(read_jsonl(path), 1):
            where = f"{path.relative_to(ROOT)}:{n}"
            key_ok(where, row, required=True)
            ref = row.get("raw_ref")
            if not isinstance(ref, dict) or any(k not in ref for k in RAW_REF_KEYS):
                problems.append(f"{where}: raw_ref is missing or lacks one of "
                                f"{list(RAW_REF_KEYS)}")
            if row.get("content_hash") != record_hash(row):
                problems.append(f"{where}: content_hash is not the hash of the record's "
                                f"substance")
            pair = (row.get("source_id"), str(row.get("source_record_id")))
            if pair in last and last[pair] == row.get("content_hash"):
                problems.append(f"{where}: a version identical to the one before it")
            last[pair] = row.get("content_hash")
    for path, required in ((STATE / "queue.jsonl", True), (STATE / "readiness.jsonl", True),
                           (STATE / VERDICTS, True), (STATE / INSTANCES_DUE, True)):
        for n, row in enumerate(read_jsonl(path), 1):
            key_ok(f"{path.relative_to(ROOT)}:{n}", row, required)
    for folder in (CONTEXT, PROPOSALS):
        for path in sorted(folder.glob("*.jsonl")) if folder.exists() else []:
            for n, row in enumerate(read_jsonl(path), 1):
                key_ok(f"{path.relative_to(ROOT)}:{n}", row, required=False)
    return problems


# ---------------------------------------------------------------------- viz

PAGES = ("input_workflow.html", "pipeline_patch.html")


def render_page(name, payload):
    """A page template with the pipeline state put in; None if there is no template."""
    template = Path(__file__).resolve().parent / name
    if not template.exists():
        return None
    html = template.read_text(encoding="utf-8")
    if "__DATA__" not in html:
        die(f"{template}: the __DATA__ placeholder is gone")
    return html.replace("__DATA__", payload)


def stage_viz():
    """Render the two pages: the stage-by-stage workflow, and the dataflow map."""
    state_path = STATE / "pipeline.json"
    if not state_path.exists():
        info("  skip  viz: no pipeline state; run index first")
        return
    payload = state_path.read_text(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    for name in PAGES:
        html = render_page(name, payload)
        if html is None:
            info(f"  skip  viz: no template for {name}")
            continue
        target = OUT / name
        target.write_text(html, encoding="utf-8")
        info(f"  ok    viz: {target.relative_to(ROOT)}")


# ------------------------------------------------------------------- update
#
# One runner for both front ends. `update` on the command line and `serve` walk the
# same steps through UpdateRun; they differ only in `wait`, the function called when
# a step needs a person. The CLI's says what is needed and goes on; the server's
# blocks until the page sends a signal.

STEPS = [
    # (id, title, map nodes the page lights up)
    ("sources", "Sources", ["sources"]),
    ("discover", "Discover", ["discover", "orders"]),
    ("fetch", "Fetch", ["fetch"]),
    ("manual", "Manual incidents", ["manual"]),
    ("normalise", "Normalise", ["normalise"]),
    ("prefilter", "Prefilter", ["prefilter"]),
    ("read", "Read", ["readrec", "readsrc"]),
    ("ready", "Readiness", ["ready"]),
    ("judge", "Judge", ["extract", "instances", "proposals"]),
    ("derive", "Derive", ["gate1", "gate2", "evtype"]),
    ("review", "Review", ["review", "dossiers"]),
    ("check", "Check", ["check"]),
    ("index", "Index", ["index"]),
]

ACTION_LABELS = {
    "continue": "Done, continue", "skip": "Skip for now", "retry": "Try again",
    "use_snapshot": "Use the snapshot", "cancel": "Cancel the run",
}

FETCH_FAILED = ("The AIID fetch failed. It needs the AIID token (~/.config/aiid/token, "
                "--token-file or $AIID_API_TOKEN) and network access. Try again, or carry "
                "on with the snapshot already on disk.")


class StepOutcome(Exception):
    """Raised by a step to end in a state other than `done`."""

    def __init__(self, state, text="", command="", actions=()):
        super().__init__(text)
        self.state, self.text, self.command, self.actions = state, text, command, actions


def _now():
    return datetime.now().isoformat(timespec="seconds")


def current_map():
    """The map's numbers for this instance's tree, as the page prints them."""
    return pipeline_state(index_rows())["map"]


# Subtrees of the map that are not counts: left out of a run's trace.
TRACE_SKIP = {"artifacts", "prefilter_rules"}


def flat_numbers(tree, prefix=""):
    """The numeric leaves of the map, under dotted keys. Booleans, strings, lists and
    None are not numbers here."""
    out = {}
    for key, value in tree.items():
        if not prefix and key in TRACE_SKIP:
            continue
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flat_numbers(value, name + "."))
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            out[name] = value
    return out


def write_json_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def claim_log_file(folder, run_id):
    """A new file in `folder` for the run's retained log: the run id with `:` as `-`,
    and a suffix if another run already holds that name. Never an existing file."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    base = str(run_id).replace(":", "-")
    for n in itertools.count(1):
        path = folder / (f"{base}.json" if n == 1 else f"{base}-{n}.json")
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            continue
        return path


def proposal_keys():
    """(source_id, source_record_id) of every proposal row: by record_key when the row
    has one, else by the pair."""
    keys = set()
    for path in sorted(PROPOSALS.glob("*.jsonl")) if PROPOSALS.exists() else []:
        for row in read_jsonl(path):
            if row.get("record_key"):
                keys.add(split_key(row["record_key"]))
            elif row.get("source_id") is not None:
                keys.add((row["source_id"], str(row.get("source_record_id", ""))))
    return keys


class UpdateRun:
    """One update run: its options, its steps and their states, as the page sees them.

    `wait(run, step)` is called when a step needs a person; it returns an action id
    from the step's prompt. `on_change(run)` is called after every change of state.

    `data["map"]` is the map of this run's own tree, recomputed when the run starts and
    each time a step changes state after doing work; `data["trace"]` gets one entry per
    recomputation, with the numbers and what changed. The whole snapshot is kept in a
    retained log, state/runs/<run id>.json (`save_log`).
    """

    def __init__(self, discover=False, refetch=False, manual_dir="", token_file=None,
                 wait=None, on_change=None):
        self.options = {"discover": bool(discover), "refetch": bool(refetch),
                        "manual_dir": manual_dir or ""}
        self.token_file = token_file
        self.wait = wait or cli_wait
        self.on_change = on_change or (lambda run: None)
        self.lock = threading.RLock()
        self.cancelled = False
        self.log_path = None             # the retained log, claimed on the first save
        self.ended = None                # when the run stopped, for the retained log
        self.data = {
            "id": _now(), "state": "running", "test": False,
            "options": dict(self.options),
            "current": None, "map": None, "trace": [],
            "steps": [{"id": sid, "title": title, "nodes": nodes, "state": "pending",
                       "log": [], "counts": [], "prompt": None,
                       "started": None, "ended": None}
                      for sid, title, nodes in STEPS],
        }

    # -- state -------------------------------------------------------------
    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.data))

    def step(self, sid):
        return next(s for s in self.data["steps"] if s["id"] == sid)

    def run_file(self):
        """Where `serve` keeps this run: the RUN_FILE of the module instance the run
        belongs to, so a test run's state stays in its workspace."""
        return RUN_FILE

    # -- hooks: no-ops here; the test run (testenv.py) fills them in ------------
    def prompt_for(self, step, outcome):
        """What the page shows when a step needs a person."""
        return {"text": outcome.text, "command": outcome.command,
                "actions": [{"id": a, "label": ACTION_LABELS[a]} for a in outcome.actions]}

    def answered(self, step, action):
        """Called with the person's answer, before the step runs again or moves on."""

    def _changed(self):
        self.on_change(self)

    def set_run_state(self, state):
        with self.lock:
            self.data["state"] = state
        self._changed()

    # -- the map, the trace and the retained log ----------------------------
    def begin(self):
        """The trace's start entry: the map before any step. Once per run; `run`
        calls it, and a caller may call it earlier to have the map at once."""
        with self.lock:
            if self.data["trace"]:
                return
        self._refresh(None, "start")

    def _refresh(self, sid, event):
        """Recompute the map of this run's tree and add a trace entry. Called when a
        step's state changes after work, never per log line. A map that cannot be
        computed keeps the previous one and says why in the entry: it never fails a
        step. Computed outside the lock, assigned inside it."""
        new_map, error = None, None
        try:
            new_map = current_map()
            numbers = flat_numbers(new_map)
        except (Exception, SystemExit) as e:     # noqa: BLE001 - incl. die()
            new_map = None
            error = (e.code if isinstance(e, SystemExit) and isinstance(e.code, str)
                     else f"{type(e).__name__}: {e}")
        with self.lock:
            trace = self.data["trace"]
            before = trace[-1]["numbers"] if trace else None
            if new_map is None:
                numbers = dict(before or {})
                if self.data["map"] is None:
                    self.data["map"] = {}
            else:
                self.data["map"] = new_map
            changed = {} if before is None else {
                k: [before.get(k), numbers.get(k)] for k in sorted(set(before) | set(numbers))
                if before.get(k) != numbers.get(k)}
            entry = {"at": _now(), "step": sid, "event": event, "numbers": numbers,
                     "changed": changed}
            if error is not None:
                entry["error"] = error
            trace.append(entry)
        self._changed()
        self.save_log()

    def log_file(self):
        """This run's retained log: state/runs/<run id>.json, claimed once."""
        with self.lock:
            if self.log_path is None:
                self.log_path = claim_log_file(RUNS, self.data["id"])
            return self.log_path

    def log_data(self):
        """What the retained log holds: the full snapshot, with when it started and
        ended."""
        snap = self.snapshot()
        snap["started"], snap["ended"] = snap["id"], self.ended
        return snap

    def save_log(self):
        """Write the retained log, atomically. A log that cannot be written is said on
        stderr and never stops the run."""
        try:
            write_json_atomic(self.log_file(), self.log_data())
        except OSError as e:
            print(f"  warn  the run log was not saved: {e}", file=sys.stderr)

    def finish(self):
        """Mark the run as stopped and keep its log: at the end of `run`, and by a
        runner whose thread died."""
        self.ended = _now()
        self.save_log()

    # -- the walk ----------------------------------------------------------
    def run(self):
        """Walk every step. Returns the final run state."""
        self.begin()
        for sid, _title, _nodes in STEPS:
            if self.cancelled:
                break
            if not self._run_step(sid):
                break
        with self.lock:
            if self.cancelled:
                self.data["state"] = "cancelled"
            elif self.data["state"] != "failed":
                self.data["state"] = "done"
                self.data["current"] = None
        self._changed()
        self.finish()
        return self.data["state"]

    def _run_step(self, sid):
        """Run one step until it settles. False stops the run."""
        step = self.step(sid)
        fn = getattr(self, f"step_{sid}")
        override = None
        while True:
            with self.lock:
                self.data["current"] = sid
                self.data["state"] = "running"
                # a rerun keeps the earlier attempt's log, so the person sees both
                step.update(state="running", prompt=None, counts=[],
                            started=step["started"] or _now(), ended=None)
            self._changed()
            self.save_log()
            info(f"[{sid}]")
            _LOCAL.sink = _StepLog(self, step)
            outcome = None
            try:
                fn(step, override)
            except StepOutcome as o:
                outcome = o
            except SystemExit as e:          # a stage called die()
                msg = e.code if isinstance(e.code, str) else f"exit status {e.code}"
                info(f"  FAIL  {msg}")
                outcome = StepOutcome("failed", f"The step stopped: {msg}",
                                      actions=("retry", "cancel"))
            except Exception as e:           # noqa: BLE001 - a step must not kill a run
                info(f"  FAIL  {type(e).__name__}: {e}")
                for line in traceback.format_exc().splitlines()[-4:]:
                    info(f"        {line}")
                outcome = StepOutcome("failed", f"The step stopped: {type(e).__name__}: {e}",
                                      actions=("retry", "cancel"))
            finally:
                _LOCAL.sink = None
            override = None
            if outcome is None:
                self._settle(step, "done")
                return True
            if outcome.state in ("skipped", "placeholder"):
                self._settle(step, outcome.state)
                return True
            # waiting or failed: a person is needed
            prompt = self.prompt_for(step, outcome)
            with self.lock:
                step.update(state=outcome.state, prompt=prompt)
                self.data["state"] = outcome.state
            self._refresh(sid, outcome.state)
            action = self.wait(self, step) if not self.cancelled else "cancel"
            with self.lock:
                step["log"].append(f"  ->    {action}")
            if action == "cancel" or self.cancelled:
                self.cancelled = True
                self._settle(step, "failed" if outcome.state == "failed" else "skipped")
                return False
            _LOCAL.sink = _StepLog(self, step)
            try:
                self.answered(step, action)
            finally:
                _LOCAL.sink = None
            self._refresh(sid, f"answered:{action}")
            if action == "skip":
                self._settle(step, "skipped")
                return True
            if action == "stop":                 # the CLI does not retry
                self._settle(step, outcome.state, keep_prompt=True)
                with self.lock:
                    self.data["state"] = "failed"
                return False
            if action == "continue":
                override = "recheck"
            elif action == "use_snapshot":
                override = "use_snapshot"
            # retry, continue, use_snapshot: run the step again

    def _settle(self, step, state, keep_prompt=False):
        with self.lock:
            step["state"] = state
            step["ended"] = _now()
            if not keep_prompt:
                step["prompt"] = None
            if self.data["state"] in ("waiting", "failed") and not keep_prompt:
                self.data["state"] = "running"
        self._refresh(step["id"], state)

    def count(self, step, label, n):
        with self.lock:
            step["counts"].append([label, n])

    # -- the steps ---------------------------------------------------------
    def step_sources(self, step, _o):
        reg = registry()
        roles = {}
        for r in reg.values():
            roles[r["role"]] = roles.get(r["role"], 0) + 1
        info(f"  ok    sources: {len(reg)} in {REGISTRY.relative_to(ROOT)}")
        self.count(step, "Sources", len(reg))
        for role in ("baseline", "discovery", "reference"):
            if role in roles:
                self.count(step, {"baseline": "Baseline", "discovery": "Discovery",
                                  "reference": "Reference only"}[role], roles[role])

    def step_discover(self, step, _o):
        if not self.options["discover"]:
            info("  skip  discover: not asked for (--discover)")
            raise StepOutcome("skipped")
        info("  todo  discover: not built yet; no source is searched. Skipped.")
        n = stage_discover([s for s, r in registry().items() if r["role"] == "discovery"])
        self.count(step, "To-do notes written", n)
        raise StepOutcome("placeholder")

    def step_fetch(self, step, override):
        reg = registry()
        baseline = [s for s, r in reg.items() if r["role"] == "baseline"]
        refetch = self.options["refetch"] and override != "use_snapshot"
        if override == "use_snapshot":
            info("  note  using the snapshot already on disk")
        try:
            done = stage_fetch(baseline, force=refetch, token_file=self.token_file)
        except (SystemExit, Exception) as e:     # noqa: BLE001
            msg = e.code if isinstance(e, SystemExit) else f"{type(e).__name__}: {e}"
            info(f"  FAIL  fetch: {msg}")
            raise StepOutcome("failed", FETCH_FAILED,
                              actions=("retry", "use_snapshot")) from None
        snap = aiid_snapshot()
        self.count(step, "Fetched now", len(done))
        self.count(step, "AIID records in the snapshot", snap["records"])

    def step_manual(self, step, _o):
        if not self.options["manual_dir"]:
            info("  skip  manual: no directory given (--manual DIR)")
            raise StepOutcome("skipped")
        files, incidents = ingest_manual(self.options["manual_dir"])
        self.count(step, "Files", files)
        self.count(step, "Incidents", incidents)

    def step_normalise(self, step, _o):
        reg = registry()
        ids = sorted(s for s, r in reg.items()
                     if (r["role"] == "baseline" or s == MANUAL) and (RAW / s).exists())
        new = stage_normalise(ids)
        records = latest_records()
        self.count(step, "New or changed", new)
        self.count(step, "Records", len(records))

    def step_prefilter(self, step, _o):
        rows = stage_prefilter()
        by_arm = arm_counts(rows)
        self.count(step, "Candidates", len(rows))
        for arm, label in (("label", "Tagged by someone else"),
                           ("keyword", "Matched a keyword"),
                           ("unasked", "Recent, never asked if multi-agent"),
                           (MANUAL, "Added by hand")):
            if arm in by_arm:
                self.count(step, label, by_arm[arm])

    def step_read(self, step, override):
        queue = read_jsonl(STATE / "queue.jsonl")
        context = load_context()
        unread = record_only = deeper = 0
        for row in queue:
            ctx = context.get(row_pair(row))
            if ctx is None:
                unread += 1
            elif best_depth(ctx) in ("unreadable", "record"):
                record_only += 1
            else:
                deeper += 1
        self.count(step, "No reading yet", unread)
        self.count(step, "Record text read", record_only)
        self.count(step, "Source read", deeper)
        info(f"  ok    read: {unread} of {len(queue)} queued record(s) have no reading")
        if unread and override != "recheck":
            raise StepOutcome(
                "waiting", f"{unread} queued record(s) have not been read yet. In Claude "
                f"Code, run /classify-incidents; its step 0 reads them and writes "
                f"mvp/context/. One run of this command also does the judging, so "
                f"you will normally not need to run it again at Judge. When it has "
                f"finished and reported back, continue: the count below is taken "
                f"again and shows what is still unread.",
                command="/classify-incidents", actions=("continue", "skip"))

    def step_ready(self, step, _o):
        summary = stage_readiness()
        scope = summary.get("queue", {}).get("scope", {})
        for lvl, label in (("ready", "Ready"), ("provisional", "Provisional"),
                           ("not_ready", "Not ready")):
            self.count(step, label, scope.get(lvl, 0))

    def judgeable(self):
        """Queued records with scope decidable and not already out of scope."""
        queue = read_jsonl(STATE / "queue.jsonl")
        context = load_context()
        out = []
        for row in queue:
            key = row_pair(row)
            verdict = readiness(context.get(key), flagged=is_flagged(row.get("arms")))
            if verdict["scope"]["level"] in ("ready", "provisional") \
                    and not out_of_scope(verdict):
                out.append(key)
        return out

    def step_judge(self, step, override):
        keys = self.judgeable()
        have = set(proposal_rows("extract_gate"))
        missing = [k for k in keys if k not in have]
        self.count(step, "Can be judged", len(keys))
        self.count(step, "Without a proposal", len(missing))
        info(f"  ok    judge: {len(keys)} record(s) can be judged, "
             f"{len(missing)} without a proposal")
        if missing and override != "recheck":
            raise StepOutcome(
                "waiting", f"{len(missing)} record(s) are ready to judge and have no "
                f"proposal. In Claude Code, run /classify-incidents: it skips what is "
                f"already done and judges the rest. If a run from the Read step is "
                f"still going, wait for it to finish and report back. Then continue: "
                f"the count below is taken again and shows what still has no "
                f"proposal.",
                command="/classify-incidents", actions=("continue", "skip"))

    def step_derive(self, step, _o):
        split = stage_derive()
        self.count(step, "In scope", split["in_scope"])
        self.count(step, "Out of scope", split["out_of_scope"])
        self.count(step, "For a person to review", split["review"])

    def step_review(self, step, override):
        attested = dossier_source_refs()
        proposals = [k for k in proposal_keys() if k not in attested]
        context = load_context()
        manual = sorted(k for k, c in context.items()
                        if c.get("manual") is True and k not in attested)
        due = stage_instances_due()
        self.count(step, "Proposals awaiting a person", len(proposals))
        self.count(step, "Hand-added incidents without a dossier", len(manual))
        self.count(step, "In scope, no instance proposal", len(due))
        info(f"  ok    review: {len(proposals)} proposal(s) and {len(manual)} "
             f"hand-added incident(s) await a person; {len(due)} record(s) in scope "
             f"have no instance proposal")
        for sid, rid in manual:
            info(f"  todo  python mvp/pipeline/run.py promote {record_key(sid, rid)}")
        for sid, rid in sorted(proposals)[:50]:
            info(f"  todo  review the proposal for {record_key(sid, rid)}")
        for r in due[:50]:
            info(f"  todo  assign instances to {r['record_key']} (/classify-incidents, "
                 f"call 2)")
        if (proposals or manual or due) and override != "recheck":
            parts = []
            if proposals:
                parts.append(f"{len(proposals)} proposal(s) in mvp/proposals/ await "
                             f"review")
            if manual:
                parts.append(f"{len(manual)} hand-added incident(s) have no dossier")
            text = "; ".join(parts) + ". " if parts else ""
            if proposals or manual:
                text += ("Promote what passes the inclusion test with `python "
                         "mvp/pipeline/run.py promote <source_id>:<record_id>` (the log "
                         "lists them), fill in the dossier by hand. ")
            if due:
                text += (f"{len(due)} record(s) in scope have no instance proposal "
                         f"(`python mvp/pipeline/run.py instances-due` lists them): run "
                         f"/classify-incidents, which assigns their instances. ")
            raise StepOutcome("waiting", text + "Then continue.",
                              command="/classify-incidents" if due else "",
                              actions=("continue", "skip"))

    def step_check(self, step, _o):
        problems_before = len(step["log"])
        rc = stage_check()
        fails = sum(1 for line in step["log"][problems_before:] if "FAIL" in line)
        self.count(step, "Dossiers", len(all_dossiers()))
        self.count(step, "Problems", fails)
        if rc:
            raise StepOutcome(
                "failed", f"The check found {fails} problem(s), listed in the log. Fix "
                f"them, then try again.", actions=("retry", "cancel"))

    def step_index(self, step, _o):
        state = stage_index()
        stage_viz()
        # the map itself is refreshed when the step settles, like every other step's
        self.count(step, "Dossiers", len(state["incidents"]))
        self.count(step, "Queued", len(state["queue"]))


class _StepLog:
    """The thread's sink: appends to a step's log and tells the runner."""

    def __init__(self, run, step):
        self.run, self.step = run, step

    def append(self, line):
        with self.run.lock:
            self.step["log"].append(line)
        self.run._changed()


def cli_wait(run, step):
    """The command line does not wait: say what is needed and go on."""
    prompt = step["prompt"] or {}
    if step["state"] == "failed":
        info(f"  stop  {prompt.get('text', '')}")
        return "stop"
    info(f"  note  {prompt.get('text', '')}")
    info("        Not waiting: the run goes on without it.")
    return "skip"


def stage_update(discover=False, manual_dir="", refetch=False, token_file=None):
    if manual_dir and not Path(manual_dir).expanduser().is_dir():
        die(f"--manual {manual_dir!r} is not a directory")
    opts = [o for o, on in (("--discover", discover), ("--refetch", refetch),
                            (f"--manual {manual_dir}", manual_dir)) if on]
    info(f"update {' '.join(opts)}".rstrip() + ": "
         + " -> ".join(sid for sid, _t, _n in STEPS))
    run = UpdateRun(discover=discover, refetch=refetch,
                    manual_dir=str(Path(manual_dir).expanduser().resolve())
                    if manual_dir else "",
                    token_file=token_file)
    try:
        state = run.run()
    except BaseException as e:           # ctrl-c, or a bug: the log still says so
        with run.lock:
            run.data["state"] = "cancelled" if isinstance(e, KeyboardInterrupt) \
                else "failed"
        run.finish()
        raise
    info(f"{state}.")
    info(f"log: {run.log_file().relative_to(ROOT)}")
    return 0 if state == "done" else 1


# --------------------------------------------------------------------- runs
#
# The retained logs: state/runs/<run id>.json, real runs only. A test run keeps none.
# Read-only here.

def run_logs():
    """(path, log) of every retained run, newest first."""
    out = []
    for path in sorted(RUNS.glob("*.json")) if RUNS.is_dir() else []:
        try:
            out.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue
    out.sort(key=lambda pl: (str(pl[1].get("id", "")), pl[0].name), reverse=True)
    return out


def stage_runs(ref=None):
    logs = run_logs()
    if ref is None:
        if not logs:
            info(f"no retained runs in {RUNS.relative_to(ROOT)}/")
        for path, log in logs:
            opts = " ".join(k if v is True else f"{k}={v}"
                            for k, v in (log.get("options") or {}).items()
                            if v not in (False, "", None))
            info(f"{path.stem:24s} {'test' if log.get('test') else 'real':4s} "
                 f"{log.get('state', '?'):9s} {opts}".rstrip())
        return 0
    hits = [(p, log) for p, log in logs if ref in (p.stem, log.get("id"))]
    if not hits:
        die(f"no retained run {ref!r}; `run.py runs` lists them")
    if len(hits) > 1:
        die(f"{ref!r} names {len(hits)} runs: "
            + ", ".join(str(p.relative_to(ROOT)) for p, _ in hits) + "; give the file name")
    path, log = hits[0]
    info(f"{path.relative_to(ROOT)}: {'test' if log.get('test') else 'real'} run, "
         f"{log.get('state', '?')}")
    for entry in log.get("trace") or []:
        at = str(entry.get("at", ""))[11:] or entry.get("at", "")
        changes = ", ".join(f"{k} {'-' if a is None else a} -> {'-' if b is None else b}"
                            for k, (a, b) in (entry.get("changed") or {}).items())
        if entry.get("error"):
            changes = (changes + "; " if changes else "") + f"map not computed: {entry['error']}"
        info(f"{at:8s}  {entry.get('step') or '-':10s} {entry.get('event', ''):18s} "
             f"{changes or 'no change'}".rstrip())
    return 0


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("update", help="run every step, saying what needs a person")
    up.add_argument("--discover", action="store_true",
                    help="search the discovery sources (not built yet: reported, skipped)")
    up.add_argument("--manual", metavar="DIR", default="",
                    help="add the .txt/.md incident write-ups in DIR")
    up.add_argument("--refetch", action="store_true",
                    help="fetch AIID again instead of reusing the snapshot (needs the "
                         "token and network)")
    up.add_argument("--token-file")

    sv = sub.add_parser("serve", help="the front end, on http://127.0.0.1:<port>/")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--token-file")

    tr = sub.add_parser("testrun", help="a dry run of update on made-up incidents, in a "
                                        "scratch folder; answers every prompt itself")
    tr.add_argument("--discover", action="store_true")
    tr.add_argument("--refetch", action="store_true",
                    help="the first fetch fails on purpose; the run tries again")
    tr.add_argument("--manual", action="store_true",
                    help="include the sample hand-written write-up")
    tr.add_argument("--skip", nargs="+", action="extend", default=[], metavar="STEP",
                    help="answer `skip` at these steps instead of continuing")

    rs = sub.add_parser("runs", help="list the retained run logs, or show one run's trace")
    rs.add_argument("run", nargs="?", help="a run id, or its log's file name")

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
    p.add_argument("ref", nargs="+",
                   help="<source_id>:<record_id>, e.g. aiid:1604: the same string as "
                        "the record_key field every record, queue, readiness, context "
                        "and proposal row carries")
    p.add_argument("--force", action="store_true",
                   help="scaffold even if the record is not ready to classify")

    sub.add_parser("readiness")
    sub.add_parser("derive", help="derive the labels from the extract_gate proposals, "
                                  "by rule, into state/verdicts.jsonl")
    sub.add_parser("instances-due", help="list the records in scope that have no "
                                         "instance proposal")

    sub.add_parser("index")
    sub.add_parser("viz")
    sub.add_parser("check")

    args = ap.parse_args()

    if args.cmd == "update":
        sys.exit(stage_update(args.discover, args.manual, args.refetch, args.token_file))
    elif args.cmd == "serve":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import serve
        serve.serve(sys.modules[__name__], args.port, args.token_file)
    elif args.cmd == "testrun":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import testenv
        sys.exit(testenv.cli(sys.modules[__name__], discover=args.discover,
                             refetch=args.refetch, manual=args.manual, skip=args.skip))
    elif args.cmd == "runs":
        sys.exit(stage_runs(args.run))
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
        stage_promote(args.ref, args.force)
    elif args.cmd == "readiness":
        stage_readiness()
    elif args.cmd == "derive":
        stage_derive()
    elif args.cmd == "instances-due":
        stage_instances_due()
    elif args.cmd == "index":
        stage_index()
    elif args.cmd == "viz":
        stage_viz()
    elif args.cmd == "check":
        sys.exit(stage_check())


if __name__ == "__main__":
    main()
