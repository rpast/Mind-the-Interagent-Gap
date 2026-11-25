#!/usr/bin/env python3
"""The input-layer update routine.

Stages, in the order an update runs them:

    sources    load the source registry
    discover   search non-AIID sources for incidents AIID does not have
               (placeholder: not built yet; `discover` alone writes the work orders)
    fetch      pull the baseline source into 0.2/raw/<source>/, verbatim
    manual     copy hand-written incident write-ups into 0.2/raw/manual/
    normalise  raw -> 0.2/records/<source>.jsonl, append-only, content-hashed
    prefilter  screen records into a candidate queue, recall first
    read       (claude code skill /classify-incidents, step 0: the readings)
    readiness  say, per record, whether enough has been read to classify it
    judge      (claude code skill /classify-incidents; see 0.2/docs/classifiers.md)
    derive     the labels, by rule (derive.py), from the newest extract_gate proposal
               of each record -> 0.2/ledger/ledger.csv
    review     two spreadsheets in 0.2/review/: a person decides scope on sheet 1, then
               says on sheet 2 which in-scope records get a dossier; this step reads
               the filled sheets, logs the decisions, scaffolds the dossiers, and writes
               fresh sheets (`review` alone does the same). `promote` still makes one
               dossier by hand; `instances-due` lists the records a person put in
               scope with no risk-instance proposal
    check      validate the layer; exits non-zero on any problem
    index      regenerate 0.2/out/incident_index.csv and 0.2/state/pipeline.json
    viz        render the pipeline flowchart, 0.2/out/pipeline_flow.html

    report     the published report, 0.2/out/index_report.html, built from what
               the last `index` wrote. Not part of `update`: run it on its own

    update [--discover] [--manual DIR] [--refetch] [--token-file F]
    serve  [--port 8765]     the front end on http://127.0.0.1:<port>/
    testrun [--refetch] [--manual] [--discover] [--skip STEP ...]
                             the same steps on made-up incidents in a scratch folder
                             (see 0.2/testenv/README.md); never touches the real tree
    runs [RUN]               the retained logs of real runs, newest first; with RUN, its trace:
                             how the map's numbers changed, step by step

`update` runs them all, step by step. A step that needs a person (a skill run, a
review) is reported with what is needed, and the run goes on; `serve` runs the same
steps and waits for the person instead. Each stage is also runnable alone.

AIID is the baseline source: the snapshot in 0.2/raw/aiid/ is reused unless
--refetch. Everything else is a discovery source, searched for what AIID does not
carry, or a write-up the curator adds by hand with --manual.
"""
from __future__ import annotations

import argparse
import copy
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

# The review sheets are spreadsheets. Without openpyxl the review step says so, skips
# the sheets, and the rest of the run goes on.
try:
    import openpyxl
except ImportError:  # pragma: no cover
    openpyxl = None

# The labelling rules live in one file beside this one, derive.py, and nowhere else.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import derive as rules  # noqa: E402
# The ledger, one row per record, holds every step's output: ledger.py.
import ledger  # noqa: E402
# The two review sheets and their logs: decide.py. It works on this module instance.
import decide  # noqa: E402


class _Here:
    """This module instance, as decide.py sees it: every name looked up in this
    instance's globals, so a test instance pointed elsewhere by set_paths is seen as it
    is now. (A test instance is not in sys.modules, so it cannot be named there.)"""
    def __getattr__(self, name):
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(name) from None


THIS = _Here()

# Every path the stages read or write. They live in module globals, set in one place.
# The test run (testenv.py) loads a second instance of this module and points that
# one at a scratch workspace; this instance is set once, here, and never re-pointed.
PATH_NAMES = ("TREE", "ROOT", "REGISTRY", "MIG_KEYS", "TAXONOMY", "RAW", "RECORDS",
              "INCIDENTS", "PROPOSALS", "CONTEXT", "STATE", "OUT", "RUN_FILE", "RUNS",
              "REVIEW", "LEDGER")


def set_paths(tree_dir):
    global TREE, ROOT, REGISTRY, MIG_KEYS, TAXONOMY, RAW, RECORDS, INCIDENTS, PROPOSALS, \
        CONTEXT, STATE, OUT, RUN_FILE, RUNS, REVIEW, LEDGER
    TREE = Path(tree_dir).resolve()
    ROOT = TREE.parent
    REGISTRY = TREE / "registry" / "sources.csv"
    MIG_KEYS = TREE / "registry" / "mig_keys.csv"   # our key, MIG-nnnn, per record
    TAXONOMY = TREE / "taxonomy"
    RAW = TREE / "raw"
    RECORDS = TREE / "records"
    INCIDENTS = TREE / "incidents"
    PROPOSALS = TREE / "proposals"
    CONTEXT = TREE / "context"
    STATE = TREE / "state"
    OUT = TREE / "out"
    RUN_FILE = STATE / "run.json"
    RUNS = STATE / "runs"           # one retained log per run: <run id>.json
    REVIEW = TREE / "review"         # the two sheets a person fills in, and their logs
    LEDGER = TREE / "ledger" / "ledger.csv"   # one row per record: every step's output


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
    "mig_key", "source_key", "title", "canonical_source", "sources", "occurrence_date",
    "occurrence_date_precision", "first_seen", "last_verified", "systems",
    "actor_count", "interaction_kind", "evidence_type", "multi_agent",
    "multi_agent_basis", "multi_agent_label_source", "external_labels",
    "failure_mode", "failure_mode_source", "instances", "instances_presumed",
    "verification",
]

# The multi-agent-attack presumption carries to the instance layer: an attack whose
# source does not say what multiplicity contributed is presumed to show both of
# these until the source settles it. See 0.2/docs/definitions.md.
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

# Every AIID record dated on or after this day is queued unless an outside rater has
# already answered "not multi-agent" on it (outside_says_no). AIID's own multi-agent
# label (CSETv1) stops in 2024, so from here on almost every record is unlabelled and
# read by us. An outside "yes" flags a record; it never puts it in scope.
RECENT_FROM = "2024-01-01"

MA_FIELD = "Multiple AI Interaction"
MA_POSITIVE = {"yes", "maybe"}
# The source whose taxonomies carry MA_FIELD.
MA_SOURCE = "aiid"

# Why a queued record is in the queue: one of these, in this order of precedence.
BASIS_RECENT = "recent"
BASIS_FROZEN = "frozen"
BASIS_MANUAL = "manual"
BASES = [BASIS_RECENT, BASIS_FROZEN, BASIS_MANUAL]


# The context layer: what a source says, read for the facts the gates need.
# See 0.2/docs/context_layer.md. A fact is `stated`, `not_stated` (the source was
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

# Why a queued record is flagged as a likely multi-agent case: an outside label calls
# it multi-agent (`label`), or a keyword matches (`keyword`). A flagged record may not
# be dismissed as single-agent on its record text alone.
FLAGS = ["label", "keyword"]

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


# ----------------------------------------------------------------- MIG keys
#
# Two keys name an incident. `source_key` is the key its source uses (AIID's incident
# number, AI Village's AIV-02), blank when the source has none (a hand-added record).
# `mig_key`, MIG-nnnn, is ours: given once to every record that reaches the decide-scope
# sheet, never changed and never given again. 0.2/registry/mig_keys.csv holds one row per
# key: the record it was given to. A dossier carries the key of its canonical record. A
# record a dossier also cites is shown under the dossier's key; a key it had before is
# retired, kept in the registry so old log rows still resolve, and never reused.
# Internally the pipeline still joins its own files on record_key, the source pair.

MIG_COLS = ["mig_key", "source_id", "source_record_id", "assigned_on", "basis"]
MIG_PATTERN = r"MIG-\d{4}"


def source_key(source_id, source_record_id):
    """The key the source itself uses for the record; blank for a hand-added record,
    whose id is our own slug."""
    return "" if source_id == MANUAL else str(source_record_id)


def read_mig_registry():
    return read_csv(MIG_KEYS) if MIG_KEYS.exists() else []


def canonical_pair(meta):
    """The source pair a dossier's mig_key belongs to: its first source of the canonical
    source."""
    refs = [(s.get("source_id"), str(s.get("record_id"))) for s in meta.get("sources") or []]
    return next((r for r in refs if r[0] == meta.get("canonical_source")),
                refs[0] if refs else None)


def mig_index():
    """{pair: mig_key} for every record that has a key, and {mig_key: pair} for every key
    ever given (a dossier's key -> its canonical pair). A record a dossier cites shows
    under the dossier's key."""
    by_pair, by_key = {}, {}
    for r in read_mig_registry():
        pair = (r["source_id"], str(r["source_record_id"]))
        by_pair.setdefault(pair, r["mig_key"])
        by_key[r["mig_key"]] = pair
    for path in all_dossiers():
        meta, _ = read_dossier(path)
        key = meta.get("mig_key") or path.stem
        for s in meta.get("sources") or []:
            by_pair[(s.get("source_id"), str(s.get("record_id")))] = key
        pair = canonical_pair(meta)
        if pair and key not in by_key:
            by_key[key] = pair
    return by_pair, by_key


def mig_key_of(pair, index=None):
    by_pair, _ = index or mig_index()
    return by_pair.get(tuple(pair), "")


def next_mig_number(index=None):
    by_pair, by_key = index or mig_index()
    used = [int(k[4:]) for k in list(by_key) + list(by_pair.values())
            if re.fullmatch(MIG_PATTERN, k or "")]
    return max(used, default=0) + 1


def assign_mig_keys(pairs, basis="decide scope"):
    """Give a MIG key to each pair that has none, in record order, and append them to the
    registry. Returns {pair: new key}."""
    index = mig_index()
    by_pair, _ = index
    todo = sorted({tuple(p) for p in pairs if tuple(p) not in by_pair},
                  key=lambda p: natural(record_key(*p)))
    if not todo:
        return {}
    n = next_mig_number(index)
    new = {}
    MIG_KEYS.parent.mkdir(parents=True, exist_ok=True)
    fresh = not MIG_KEYS.exists()
    with open(MIG_KEYS, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MIG_COLS, lineterminator="\n")
        if fresh:
            w.writeheader()
        for pair in todo:
            key = f"MIG-{n:04d}"
            n += 1
            new[pair] = key
            w.writerow({"mig_key": key, "source_id": pair[0], "source_record_id": pair[1],
                        "assigned_on": TODAY, "basis": basis})
    return new


def keyed_pair(fields, by_key):
    """The record a row names by mig_key, source_id and source_key: by the source's own
    key when there is one (a record a dossier also cites shows under the dossier's key,
    so the key alone would name the dossier's canonical record), else by the MIG key
    (a hand-added record has no source key). None when neither resolves."""
    sid, skey = fields.get("source_id", ""), fields.get("source_key", "")
    if sid and skey:
        return (sid, str(skey))
    return by_key.get(fields.get("mig_key", ""))


def key_fields(pair, index=None):
    """The three columns a person sees for a record: mig_key, source_id, source_key."""
    return {"mig_key": mig_key_of(pair, index), "source_id": pair[0],
            "source_key": source_key(*pair)}


def check_mig_registry(problems):
    """Every key once, of the MIG pattern, given to one record that exists; every record
    one key at most; every dossier's key in the registry, given to one of the records the
    dossier cites (its canonical record when it was made; a source linked later may
    become canonical without changing the key)."""
    rel = MIG_KEYS.relative_to(ROOT) if MIG_KEYS.is_relative_to(ROOT) else MIG_KEYS
    if not MIG_KEYS.exists():
        if all_dossiers():
            problems.append(f"{rel}: missing; every dossier's mig_key must be in it")
        return
    with open(MIG_KEYS, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f), [])
    if header != MIG_COLS:
        problems.append(f"{rel}: the header is {header}, it must be {MIG_COLS}")
        return
    records = latest_records()
    keys, pairs = {}, {}
    for n, r in enumerate(read_csv(MIG_KEYS), 2):
        pair = (r["source_id"], str(r["source_record_id"]))
        if not re.fullmatch(MIG_PATTERN, r["mig_key"]):
            problems.append(f"{rel}:{n}: {r['mig_key']!r} is not MIG-nnnn")
        if r["mig_key"] in keys:
            problems.append(f"{rel}:{n}: {r['mig_key']} is given twice")
        if pair in pairs:
            problems.append(f"{rel}:{n}: {record_key(*pair)} already has "
                            f"{pairs[pair]}; a record has one key")
        if pair not in records:
            problems.append(f"{rel}:{n}: {record_key(*pair)} is no record")
        if not parse_iso(r["assigned_on"])[0]:
            problems.append(f"{rel}:{n}: assigned_on {r['assigned_on']!r} is not a date")
        keys[r["mig_key"]] = pair
        pairs.setdefault(pair, r["mig_key"])
    for path in all_dossiers():
        meta, _ = read_dossier(path)
        key = meta.get("mig_key")
        cited = {(s.get("source_id"), str(s.get("record_id")))
                 for s in meta.get("sources") or []}
        if key not in keys:
            problems.append(f"{path.relative_to(ROOT)}: mig_key {key!r} is not in {rel}")
        elif keys[key] not in cited:
            problems.append(f"{path.relative_to(ROOT)}: mig_key {key} was given to "
                            f"{record_key(*keys[key])}, which the dossier does not cite")


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


def frontmatter_text(meta):
    ordered = {k: meta[k] for k in REQUIRED_KEYS if k in meta}
    ordered.update({k: v for k, v in meta.items() if k not in ordered})
    fm = yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True,
                        default_flow_style=False, width=88)
    return f"---\n{fm}---\n"


def write_dossier(path, meta, sections):
    parts = [frontmatter_text(meta)]
    for name in SECTIONS:
        parts.append(f"\n## {name}\n\n{sections.get(name, '').rstrip()}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(parts), encoding="utf-8")


def write_dossier_body(path, meta, body):
    """Write the frontmatter again and keep the body exactly as it is."""
    path.write_text(frontmatter_text(meta) + body, encoding="utf-8")


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
        f"not already in `0.2/records/`, and save what you find to "
        f"`0.2/raw/{row['source_id']}/` as JSON lines with at least "
        f"`source_record_id`, `title`, `text`, `date` and `url`. Then run "
        f"`python 0.2/pipeline/run.py normalise {row['source_id']}`.\n"
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
        f"# AIID snapshot\n\nFetched {TODAY} by `0.2/pipeline/run.py fetch aiid`.\n",
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
    ledger_load()
    return total


# ------------------------------------------------------------------- ledger
#
# Each step writes its own columns of ledger/ledger.csv (ledger.py). The readers below
# give the rest of the pipeline the rows it used to read from the queue and verdicts
# files (until 0.2), rebuilt from the ledger.

def ledger_load(backfill=False):
    """The load columns, for every record's newest version. A record's `loaded_on` is
    set the first time it reaches the ledger and never changed. `backfill` (the one-off
    migration only) sets a missing one from the record's fetch date instead of today."""
    old = ledger.read(LEDGER)
    updates = {}
    for (sid, rid), rec in latest_records().items():
        key = record_key(sid, rid)
        first = (old.get(key) or {}).get("loaded_on") \
            or (rec.get("fetched_at", "") if backfill else TODAY)
        updates[key] = {
            "record_key": key, "source_id": sid, "source_key": source_key(sid, rid),
            "title": rec.get("title", ""), "date": rec.get("date", ""),
            "url": rec.get("url", ""), "loaded_on": first,
            "fetched_at": rec.get("fetched_at", ""),
            "content_hash": rec.get("content_hash", ""),
            "external_ma_label": [f"{l.get('namespace') or l.get('source')}={l.get('value')}"
                                  for l in rec.get("external_labels") or []
                                  if l.get("field") == MA_FIELD]}
    ledger.write(LEDGER, "load", updates)
    info(f"  ok    ledger: {len(updates)} records -> {LEDGER.relative_to(ROOT)}")
    return len(updates)


def prefilter_columns(q):
    """A queue row as the ledger's prefilter columns."""
    return {"queued": True, "queue_basis": q.get("basis", ""), "flags": q.get("flags", ""),
            "keyword_terms": q.get("keyword_terms", ""),
            "label_values": q.get("label_values", "")}


def read_queue():
    """The queued records, as the queue rows the prefilter makes: in (source_id,
    source_record_id) order, with the record's date, title and url."""
    rows = []
    for key, r in ledger.read(LEDGER).items():
        if r["queued"] != "true":
            continue
        sid, rid = split_key(key)
        rows.append({"source_id": sid, "source_record_id": rid, "record_key": key,
                     "date": r["date"], "title": r["title"], "basis": r["queue_basis"],
                     "flags": r["flags"], "label_values": r["label_values"],
                     "keyword_terms": r["keyword_terms"], "url": r["url"]})
    rows.sort(key=lambda q: (q["source_id"], q["source_record_id"]))
    return rows


def reading_columns(pair, ctx):
    """A context row as the ledger's reading columns: depth, count, each fact's status."""
    facts = ctx.get("facts") or {}
    return {"read_depth": best_depth(ctx), "agent_count": ctx.get("agent_count", ""),
            **{f"{f}_status": (facts.get(f) or {}).get("status", "unread")
               for f in CONTEXT_FACTS},
            "context_ref": f"context/{pair[0]}.jsonl"}


def derive_columns(gate, v, gate_ref=""):
    """One record's extract_gate answers and the verdict the rules derived from them, as
    the ledger's derive columns."""
    labels = rules.labels_of(v)
    return {
        "gate_prompt": v.get("prompt", ""), "gate_run_date": v.get("run_date", ""),
        **{f: gate.get(f) for f in ledger.GATE_FIELDS}, "gate_ref": gate_ref,
        "rules_version": v.get("rules_version", ""),
        "is_attack": bool(gate) and rules.is_security(gate),
        "presumption_fires": bool(gate) and rules.presumption_fires(gate),
        "counterfactual": labels.get("counterfactual_resolved"),
        "by_presumption": bool(v.get("by_presumption")),
        "gate1": v.get("gate1", ""), "rules_status": v.get("status", ""),
        "why_a_person": v.get("review_why") or [],
        "labels_settled": "labels" in v,
        "rules_multi_agent": labels.get("multi_agent"),
        "rules_evidence_type": labels.get("evidence_type"),
        "rules_failure_mode": labels.get("failure_mode"),
        "rules_instances_presumed": labels.get("instances_presumed") or [],
        "scope_proposed": rules_say(v),
        "scope_why": ("not settled: " + "; ".join(v["review_why"]) if v.get("review_why")
                      else f"settled by the rules: {v.get('status', '')}"),
    }


def verdict_of(key, r):
    """A ledger row's derive columns as the verdict derive.py returned."""
    sid, rid = split_key(key)
    labels = {"multi_agent": ledger.as_bool(r["rules_multi_agent"]),
              "counterfactual_resolved": r["counterfactual"] or None,
              "evidence_type": r["rules_evidence_type"] or None,
              "failure_mode": r["rules_failure_mode"] or None,
              "instances_presumed": ledger.as_list(r["rules_instances_presumed"])}
    return {"record_key": key, "source_id": sid, "source_record_id": rid,
            "prompt": r["gate_prompt"], "run_date": r["gate_run_date"],
            "status": r["rules_status"], "gate1": r["gate1"],
            "review_why": ledger.as_list(r["why_a_person"]),
            "by_presumption": r["by_presumption"] == "true",
            "rules_version": r["rules_version"],
            ("labels" if r["labels_settled"] == "true" else "labels_if_confirmed"): labels}


# Reading a dossier into the ledger's incident columns: done once for every dossier when
# the columns were built (0.2/docs/plan.md, P3a), and since then only for a dossier the
# ledger has never held (decide.place_incidents). A label counts as decided when the
# dossier says a person set it: multi_agent_label_source `ours`, failure_mode_source
# `ours`, or the field in set_by_person. Every other label is a proposal, waiting for a
# person's `ok` (the curator's choice of 2026-11-25).

def label_token(label, meta):
    """A dossier label as ledger text. `none` is an explicit empty answer (no failure
    mode, no instances); blank means no value at all."""
    if label == "incident_scope":
        return {True: "in", False: "out"}.get(meta.get("multi_agent"),
                                              str(meta.get("multi_agent") or ""))
    if label == "failure_mode":
        return meta.get("failure_mode") or "none"
    if label == "instances":
        return meta.get("instances") or "none"
    if label == "evidence_type":
        return meta.get("evidence_type") or ""
    return ""


def label_decided(label, meta):
    by_person = set(meta.get(SET_BY_PERSON) or [])
    return {"incident_scope": meta.get("multi_agent_label_source") == "ours"
            or "multi_agent" in by_person,
            "failure_mode": meta.get("failure_mode_source") == "ours"
            or "failure_mode" in by_person,
            "instances": "instances" in by_person,
            "evidence_type": "evidence_type" in by_person}.get(label, False)


def adoptable_instances(prop):
    """An assign_instances proposal's high and medium instances: ids, and a short why."""
    keep = [i for i in (prop or {}).get("instances") or []
            if i.get("confidence") in ("high", "medium")]
    return ([i.get("instance_id") for i in keep],
            "; ".join(f"{i.get('instance_id')} {i.get('confidence')}" for i in keep))


def incident_columns(meta, body, row, inst_prop):
    """One dossier as the ledger's incident columns. `row` is its canonical record's
    ledger row (the rules' proposals), `inst_prop` that record's instance proposal."""
    origin = ("written by Claude from the readings" if "Written by Claude" in body
              else "carried over from the PoC")
    ids, ids_why = adoptable_instances(inst_prop)
    rules_prop = {
        "incident_scope": (row.get("scope_proposed", ""), row.get("scope_why", "")),
        "failure_mode": ((row.get("rules_failure_mode") or "none") if row.get("rules_status")
                         else "", f"rules {row.get('rules_version')} from "
                                  f"{row.get('gate_prompt')}" if row.get("rules_status") else ""),
        "instances": (ids or ("none" if inst_prop else ""),
                      f"assign_instances: {ids_why}" if inst_prop else ""),
        "evidence_type": (row.get("rules_evidence_type", ""),
                          f"rules {row.get('rules_version')} from {row.get('gate_prompt')}"
                          if row.get("rules_status") else ""),
    }
    out = {"incident_title": meta.get("title", ""),
           "occurrence_date": str(meta.get("occurrence_date") or ""),
           "occurrence_date_precision": meta.get("occurrence_date_precision", ""),
           "actor_count": str(meta.get("actor_count") or ""),
           "interaction_kind": meta.get("interaction_kind", ""),
           "systems": meta.get("systems") or [],
           "instances_presumed": meta.get("instances_presumed") or [],
           "verification": meta.get("verification", ""),
           "last_verified": str(meta.get("last_verified") or "")}
    for label in ledger.INCIDENT_LABELS:
        value = label_token(label, meta)
        if label_decided(label, meta):
            proposed, why = rules_prop.get(label, ("", ""))
            out.update({f"{label}_proposed": proposed, f"{label}_why": why,
                        f"{label}_decision": value, f"{label}_final": value})
        else:
            source = meta.get("failure_mode_source") or ""
            why = source if label == "failure_mode" and source.startswith("classifier:") \
                else origin if value else ""
            out.update({f"{label}_proposed": value, f"{label}_why": why})
    return out


def dedupe_inputs(rows=None):
    """What dedupe.py works on: every record by key, and {incident_key: its records}."""
    import dedupe
    rows = ledger.read(LEDGER) if rows is None else rows
    recs = {record_key(*p): r for p, r in latest_records().items()}
    incidents = {}
    for k, r in rows.items():
        if r["incident_key"]:
            incidents.setdefault(r["incident_key"], []).append(k)
    return dedupe, rows, recs, incidents


def stage_dedupe(measure=False):
    """Propose duplicate_of for every record that could be decided in and is not yet
    part of an incident: an existing incident's key, or `new`. With `measure`, report
    how the rules do on the incidents the curator merged instead."""
    dedupe, rows, recs, incidents = dedupe_inputs()
    index = dedupe.Index(recs)
    if measure:
        others = [m[0] for m in incidents.values() if len(m) == 1] + \
                 [k for k, r in rows.items() if r["scope_proposed"] == "in"
                  and not r["incident_key"]]
        hits, misses, alarms = dedupe.measure(recs, incidents, index, others)
        info(f"  dedupe: merged records found {len(hits)} of {len(hits) + len(misses)}; "
             f"false alarms {len(alarms)} of {len(others)}")
        for k, inc, got, why in misses:
            info(f"    miss   {k} (of {inc}) -> {got}: {why}")
        for k, got, why in alarms:
            info(f"    alarm  {k} -> {got}: {why}")
        return {"hits": len(hits), "misses": len(misses), "alarms": len(alarms)}
    updates = {}
    for k, r in rows.items():
        if r["incident_key"] or not (r["rules_status"] or r["source_id"] == MANUAL):
            continue
        got, why, _ = dedupe.propose(k, recs[k], incidents, recs, index)
        updates[k] = {"duplicate_of_proposed": got, "duplicate_of_why": why}
    ledger.write(LEDGER, "dedupe", updates)
    dup = sum(1 for u in updates.values() if u["duplicate_of_proposed"] != "new")
    info(f"  ok    dedupe: {len(updates)} record(s), {dup} proposed as a duplicate of an "
         f"existing incident -> {LEDGER.relative_to(ROOT)}")
    return {"records": len(updates), "duplicates": dup}


def proposal_files(prompt_id):
    """(source_id, source_record_id) -> the proposals file its newest row is in."""
    out = {}
    for path in sorted(PROPOSALS.glob(f"{prompt_id}.*.jsonl")) if PROPOSALS.exists() else []:
        for row in read_jsonl(path):
            if row.get("record_key") or row.get("source_id") is not None:
                out[row_pair(row)] = f"proposals/{path.name}"
    return out


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
    return TREE / "registry" / "labels" / "navigator_multiagent.tsv"


def read_navigator():
    """The Navigator's behaviour facet, copied off the rendered page by hand on
    2026-11-09. See 0.2/registry/labels/README.md."""
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
# The files are copied verbatim to 0.2/raw/manual/; ORIGINS.json beside them records
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
    """Copy a directory of write-ups into 0.2/raw/manual/, verbatim.

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
    Every other fact stays unread. See 0.2/docs/context_layer.md.
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

def frozen_path():
    return TREE / "registry" / "frozen_pre2024.csv"


def read_frozen():
    """The frozen pre-2024 list: record_key -> row. Hand-curated; empty if absent."""
    path = frozen_path()
    return {r["record_key"]: r for r in read_csv(path)} if path.exists() else {}


def split_flags(value):
    """The flags of a queue row, as a list."""
    return [f for f in str(value or "").split(";") if f]


def basis_counts(queue):
    """Queue rows per basis."""
    out = {}
    for row in queue:
        if row.get("basis"):
            out[row["basis"]] = out.get(row["basis"], 0) + 1
    return out


def flag_counts(queue):
    """Queue rows per flag. A row with both flags counts under both."""
    out = {}
    for row in queue:
        for flag in split_flags(row.get("flags")):
            out[flag] = out.get(flag, 0) + 1
    return out


def outside_says_no(rec):
    """An outside rater answered the multi-agent question and nobody said yes or maybe:
    at least one MA_FIELD label, and no label in MA_POSITIVE or on the Navigator's
    `behaviour` facet. A disagreement between annotators counts as yes."""
    labels = rec.get("external_labels") or []
    answered = any(l.get("field") == MA_FIELD and l.get("value") not in (None, "")
                   for l in labels)
    positive = any(str(l.get("value", "")).lower() in MA_POSITIVE
                   or l.get("field") == "behaviour" for l in labels)
    return answered and not positive


def stage_prefilter():
    """Queue a record for one reason (its `basis`) and flag it for another.

    Basis, one per queued record:

      recent   an AIID record dated on or after RECENT_FROM that no outside rater has
               answered "no" on (outside_says_no). Unlabelled records are queued; an
               outside "yes" or "maybe" is queued and flagged.
      frozen   its record_key is on the frozen pre-2024 list (registry/frozen_pre2024.csv)
      manual   added by hand (update --manual)

    Flags, any number, computed live for every queued record:

      label    an external label says yes or maybe (MA_POSITIVE), or the Navigator's
               multi-agent facet lists it
      keyword  the recall-first regex net, KEYWORD_TERMS

    A flagged record may not be dismissed as single-agent on its record text alone.
    A flag never queues a record by itself.

    Until 2026-11-17 there were three arms (label, keyword, unasked). CSETv1 stops in
    2024, so for 2024 onwards they came to "every AIID record not answered no".
    Decided by the curator 2026-11-18: where an outside rater has already answered the
    multi-agent question for a 2024+ record, its answer is acted on: "no" leaves the
    record out, "yes" or "maybe" queues and flags it. Only unlabelled records are
    queued for our own reading. Since 2024 the only outside activity is the Navigator
    list, copied by hand.
    """
    records = latest_records()
    if not records:
        info("  skip  prefilter: no records; run normalise first")
        return []
    known = dossier_source_refs()
    frozen = read_frozen()
    rows = []
    for (sid, rid), rec in sorted(records.items()):
        if (sid, rid) in known:
            continue
        key = record_key(sid, rid)
        if sid == MANUAL or (rec.get("meta") or {}).get("manual"):
            basis = BASIS_MANUAL
        elif sid == MA_SOURCE and rec.get("date", "") >= RECENT_FROM:
            if outside_says_no(rec):
                continue
            basis = BASIS_RECENT
        elif key in frozen:
            basis = BASIS_FROZEN
        else:
            continue
        label_hits = [l for l in rec.get("external_labels", [])
                      if str(l.get("value", "")).lower() in MA_POSITIVE
                      or l.get("field") == "behaviour"]
        flags = ["label"] if label_hits else []
        haystack = f"{rec.get('title', '')} {rec.get('text', '')}"
        terms = [t for t, rx in KEYWORD_RE if rx.search(haystack)]
        if terms:
            flags.append("keyword")
        rows.append({
            "source_id": sid,
            "source_record_id": rid,
            "record_key": key,
            "date": rec.get("date", ""),
            "title": rec.get("title", ""),
            "basis": basis,
            "flags": ";".join(flags),
            "label_values": ";".join(
                f"{l.get('namespace') or l.get('source')}={l.get('value')}"
                for l in label_hits),
            "keyword_terms": ";".join(terms),
            "url": rec.get("url", ""),
        })
    ledger.write(LEDGER, "prefilter", {r["record_key"]: prefilter_columns(r) for r in rows})
    info(f"  ok    prefilter: {len(rows)} candidates of {len(records)} records "
         f"-> {LEDGER.relative_to(ROOT)}")
    for basis, n in sorted(basis_counts(rows).items()):
        info(f"          {basis}: {n}")
    for flag, n in sorted(flag_counts(rows).items()):
        info(f"          flagged {flag}: {n}")
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


def is_flagged(flags):
    """A queued record whose `flags` field is not empty is flagged."""
    return bool(split_flags(flags))


def queue_flags(queue=None):
    """(source_id, source_record_id) -> flagged, for every queued record."""
    queue = read_queue() if queue is None else queue
    return {row_pair(r): is_flagged(r.get("flags")) for r in queue}


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

    `flagged`: the record has a label or keyword flag (a dossier's sources count
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


def write_reading_columns(context=None):
    """Every record's reading, from its newest context row, into the ledger. A context
    row for a record the ledger does not hold is reported and left out."""
    context = load_context() if context is None else context
    known = ledger.read(LEDGER)
    updates, stray = {}, []
    for pair, ctx in context.items():
        key = record_key(*pair)
        if key in known:
            updates[key] = reading_columns(pair, ctx)
        else:
            stray.append(key)
    ledger.write(LEDGER, "readiness", updates)
    if stray:
        info(f"  warn  ledger: {len(stray)} context row(s) for records not loaded, "
             f"e.g. {stray[0]}")
    return len(updates)


def out_of_scope(verdict):
    """The single-agent shortcut held: scope settled, nothing else arises."""
    return verdict["scope"]["level"] == "ready" \
        and verdict["evidence_type"]["level"] == "not_needed"


def stage_readiness():
    """Report, for every record awaiting a decision, whether it can be classified."""
    records = latest_records()
    context = load_context()
    queue = read_queue()
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
    write_reading_columns(context)
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
# (derive.py), every time, into the ledger's derive columns: never edited by hand
# and never written back into a proposal.

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
    refs = proposal_files("extract_gate")
    rows, split, updates = [], {s: 0 for s in rules.STATUSES}, {}
    for (sid, rid), gate in sorted(gates.items()):
        v = rules.derive(gate, manual=(sid == MANUAL))
        split[v["status"]] += 1
        v = {"record_key": record_key(sid, rid), "source_id": sid,
             "source_record_id": rid,
             "prompt": f"{gate.get('prompt_id', '')}@{gate.get('prompt_version', '')}",
             "run_date": gate.get("run_date", ""), **v}
        rows.append(v)
        updates[v["record_key"]] = derive_columns(gate, v, refs.get((sid, rid), ""))
    ledger.write(LEDGER, "derive", updates)
    write_reading_columns()
    presumed = sum(1 for r in rows if r["by_presumption"])
    info(f"  ok    derive: {len(rows)} verdict(s), rules {rules.RULES_VERSION} -> "
         f"{LEDGER.relative_to(ROOT)}")
    info(f"          in scope {split['in_scope']}  out of scope {split['out_of_scope']}  "
         f"review {split['review']}  (of the review items, {presumed} would be in scope "
         f"only by the attack presumption if a person confirms them)")
    return split


def read_verdicts():
    """Every record's verdict, rebuilt from the ledger's derive columns, keyed
    (source_id, source_record_id)."""
    return {split_key(k): verdict_of(k, r) for k, r in ledger.read(LEDGER).items()
            if r["rules_status"]}


def instances_due():
    """Records a person has put in scope that have no instance proposal. One row
    per record:

      dossier  a dossier with multi_agent true and label source `ours`, an empty
               `instances` list, and no assign_instances proposal for any of its
               sources. The record named is its canonical source's.
      decided  a record a person decided `in` on sheet 1 (0.2/review/), whatever the
               rules said, with no assign_instances proposal and no dossier that
               already lists instances. It need not be promoted yet.

    Risk instances are proposed only after a person decides scope: a record the
    rules settle in_scope is not due until a person decides it in.
    """
    have = set(proposal_rows("assign_instances"))
    records = latest_records()
    person = {k: r.get("decision") for k, r in scope_newest(records).items()}
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
                    "dossier": meta.get("mig_key", path.stem)})
    for key, v in sorted(read_verdicts().items()):
        if person.get(record_key(*key)) != "in":
            continue
        why = "decided"
        if key in have or key in seen or key in listed:
            continue
        out.append({"record_key": record_key(*key), "source_id": key[0],
                    "source_record_id": key[1], "why": why, "dossier": ""})
    return out


def stage_instances_due():
    rows = instances_due()
    STATE.mkdir(parents=True, exist_ok=True)
    write_jsonl(STATE / INSTANCES_DUE, rows)
    info(f"  ok    instances-due: {len(rows)} record(s) a person put in scope with no "
         f"risk-instance proposal -> {(STATE / INSTANCES_DUE).relative_to(ROOT)}")
    for r in rows:
        why = {"dossier": f"dossier {r['dossier']}", "decided": "decided in by a person"}[r["why"]]
        info(f"          {r['record_key']:28s} {why}")
    return rows


# ------------------------------------------------------------------ promote

class PromoteRefused(Exception):
    """promote_one will not scaffold this record; the message says why."""


def stage_promote(refs, force=False):
    records = latest_records()
    context = load_context()
    made = []
    for ref in refs:
        try:
            doc_id = promote_one(ref, records, context, made, force)
        except PromoteRefused as e:
            die(str(e))
        if doc_id:
            made.append(doc_id)
    if made:
        info("  note  a scaffold is not a record: fill every _pending_ section, verify "
             "against the primary source, and set multi_agent yourself.")
    return made


def promote_one(ref, records, context, made, force=False):
    """Scaffold the dossier of one record. Returns its id, or None when that dossier
    already exists. Raises PromoteRefused for a record it will not scaffold: the CLI
    turns that into die(); the review step reports it and goes on. `made` holds the
    ids made earlier in the same call, so two hand-added records do not share an id."""
    if re.fullmatch(MIG_PATTERN, ref):
        pair = mig_index()[1].get(ref)
        if pair is None:
            raise PromoteRefused(f"no record has the key {ref}")
        ref = record_key(*pair)
    if ":" not in ref:
        raise PromoteRefused(
            f"promote takes a MIG key or <source_id>:<record_id>, got {ref!r}")
    sid, rid = split_key(ref)
    rec = records.get((sid, rid))
    if rec is None:
        raise PromoteRefused(f"no record {ref}; run normalise first")
    flagged = queue_flags().get((sid, rid), True)
    scope = readiness(context.get((sid, rid)), flagged=flagged)["scope"]
    if scope["level"] == "not_ready" and not force:
        raise PromoteRefused(
            f"{ref} is not ready to classify ({scope['why']}). Enrich it first - "
            f"see 0.2/docs/context_layer.md - or pass --force to scaffold anyway.")
    # The record's own MIG key, given when it reached the decide-scope sheet; a record
    # promoted by hand without a verdict (a hand-added one) gets its key now.
    doc_id = mig_key_of((sid, rid)) or assign_mig_keys([(sid, rid)], "promote")[(sid, rid)]
    path = dossier_path(doc_id)
    if path.exists():
        info(f"  skip  {doc_id}: already exists")
        return None
    ok, precision = parse_iso(rec.get("date") or "")
    meta = {
        "mig_key": doc_id,
        "source_key": source_key(sid, rid),
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
    info(f"  ok    {doc_id}: scaffolded from {ref}")
    return doc_id


# ------------------------------------------------------------ review sheets
#
# The two sheets in 0.2/review/ and their logs are decide.py's. What stays here: the
# helpers both sheets use, the records' evidence columns sheet 1 shows, and read_log,
# which gives the rest of the pipeline the record decisions in the shape it reads. The
# rules never put anything in scope: a decision `in` is a person's.

HELP_SHEET = "How to fill this in"
META_SHEET = "_meta"
OPENPYXL_HINT = "install openpyxl: pip install -r requirements.txt"
NOTHING_LEFT = "(nothing is left on this sheet)"
# Decisions logged since the current update run began (an update run resets it): the
# review step can run more than once in a run, and says the total.
REVIEW_DECIDED = {"scope": 0, "promote": 0, "edit": 0}
HAND_ADDED_REASON = "added by hand: in scope on the curator's word"


def natural(key):
    """Sort key: aiid:99 before aiid:1015."""
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", str(key))]


def read_log(kind):
    """A person's record decisions, in the shape the scope and promote logs had until
    0.2 (decide.py holds the real log, review/record_decisions_log.csv):

      scope    one row per scope decision: decision is in, out or unclear
      promote  one row per duplicate_of or dossier decision: decision `yes` when the
               record was given an incident (new or an existing one), `no` when a
               person said it gets no dossier

    Each row carries record_key, from its MIG key."""
    _, by_key = mig_index()
    out = []
    for r in decide.read_log(THIS, "record"):
        if kind == "scope" and r["label"] == "scope":
            decision = r["final"]
        elif kind == "promote" and r["label"] in ("duplicate_of", "dossier"):
            decision = "no" if r["label"] == "dossier" else "yes"
        else:
            continue
        pair = by_key.get(r["mig_key"])
        out.append({**r, "decision": decision, "note": r.get("reason", ""),
                    "record_key": record_key(*pair) if pair else ""})
    return out


def newest_by_key(rows):
    """The newest row per record_key: the log is append-only, a later row wins."""
    return {r["record_key"]: r for r in rows if r.get("record_key")}


def scope_newest(records=None):
    """record_key -> the newest scope decision. A hand-added record is in scope on the
    curator's word, which is a person's verdict: it counts as decided `in` unless the
    log says otherwise."""
    rows = newest_by_key(read_log("scope"))
    records = latest_records() if records is None else records
    for sid, rid in records:
        if sid == MANUAL:
            key = record_key(sid, rid)
            rows.setdefault(key, {"record_key": key, "decision": "in",
                                  "reason": HAND_ADDED_REASON, "decided_on": "",
                                  "sheet_generated_on": ""})
    return rows


def rules_say(verdict):
    """What the rules would say about scope: in, out or unclear. Not a decision."""
    if verdict.get("gate1") == "curator":
        return "in"
    return {True: "in", False: "out"}.get(rules.labels_of(verdict).get("multi_agent"),
                                          "unclear")


def asks_a_person(verdict, gate):
    """Whether sheet 1 asks a person to judge this record. The sheet lists every record
    with no scope decision, so the ones the rules leave out can be sample-checked, but it
    asks only where a judgement matters: the rules would put the record in, or the
    model's confidence is low."""
    return rules_say(verdict) == "in" or (gate or {}).get("confidence") == "low"


def review_state(records=None):
    """What each sheet lists, from the files on disk: the keys, and what they rest on."""
    verdicts = read_verdicts()
    attested = dossier_source_refs()
    scope = scope_newest(records)
    promo = newest_by_key(read_log("promote"))
    keys = {record_key(*pair): pair for pair in verdicts}
    on_scope = sorted((k for k, p in keys.items() if k not in scope and p not in attested),
                      key=natural)
    on_promote = sorted((k for k, p in keys.items()
                         if scope.get(k, {}).get("decision") == "in"
                         and p not in attested
                         and promo.get(k, {}).get("decision") != "no"), key=natural)
    gates = proposal_rows("extract_gate")
    scope_ask = [k for k in on_scope if asks_a_person(verdicts[keys[k]], gates.get(keys[k]))]
    # Sheet 1 shows more than it asks: every record with a verdict, decided or not, and
    # every record a dossier cites, so a person can read what was extracted for each.
    # Only the rows in `scope` take a decision.
    shown = sorted(set(keys) | {record_key(*p) for p in attested}, key=natural)
    return {"verdicts": verdicts, "attested": attested, "scope_log": scope,
            "promote_log": promo, "scope": on_scope, "scope_ask": scope_ask,
            "scope_shown": shown, "promote": on_promote}


def cut(text, n=300):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def sheet_value(value):
    """A model answer as cell text: lists joined with '; ', booleans as true/false."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    return str(value)


def reading_cell(fact):
    """One fact of a context row as cell text: status, then the reading, then the quote."""
    if not fact:
        return ""
    text = fact.get("status") or ""
    if fact.get("text"):
        text += f": {fact['text']}"
    if fact.get("quote"):
        text += f' | "{fact["quote"]}"'
    return text


def instances_cell(rows):
    """Instance proposals as cell text: id, confidence and quote (or why rejected)."""
    out = []
    for i in rows or []:
        what = i.get("quote") or i.get("why") or ""
        conf = f" {i['confidence']}" if i.get("confidence") else ""
        out.append(f"{i.get('instance_id', '')}{conf}" + (f': "{what}"' if i.get("quote")
                                                          else f": {what}" if what else ""))
    return "\n".join(out)


def dossiers_by_source():
    """(source_id, source_record_id) -> the frontmatter of the dossier that cites it."""
    out = {}
    for path in all_dossiers():
        meta, _ = read_dossier(path)
        for s in meta.get("sources") or []:
            out[(s.get("source_id"), str(s.get("record_id")))] = meta
    return out


def scope_sheet_rows(state, records):
    gates = proposal_rows("extract_gate")
    inst = proposal_rows("assign_instances")
    context = load_context()
    dossiers = dossiers_by_source()
    asked, open_ = set(state["scope_ask"]), set(state["scope"])
    index = mig_index()
    rows = []
    for key in state["scope_shown"]:
        pair = split_key(key)
        v, rec, gate = state["verdicts"].get(pair, {}), records.get(pair, {}), gates.get(pair, {})
        ctx, prop, dos = context.get(pair) or {}, inst.get(pair) or {}, dossiers.get(pair)
        log = state["scope_log"].get(key) or {}
        ask = ("dossier" if pair in state["attested"] else "decided" if key not in open_
               else "yes" if key in asked else "check")
        say = rules_say(v) if v else ""
        labels = rules.labels_of(v)
        quotes = [q for q in (gate.get("quotes") or {}).values() if q][:2]
        answers = {}
        for field in MODEL_FIELDS:
            answers[field] = sheet_value(gate.get(field))
            if field in QUOTED_FIELDS:
                answers[f"{field}_quote"] = (gate.get("quotes") or {}).get(field, "")
        rows.append({
            **answers,
            "prompt": gate.get("prompt_id", "") + (f"@{gate['prompt_version']}"
                                                   if gate.get("prompt_version") else ""),
            "is_attack": "yes" if gate and rules.is_security(gate) else "no",
            "presumption_fires": "yes" if gate and rules.presumption_fires(gate) else "no",
            "gate1": v.get("gate1", ""), "status": v.get("status", ""),
            "evidence_type": labels.get("evidence_type") or "",
            "failure_mode": labels.get("failure_mode") or "",
            "instances_presumed": "; ".join(labels.get("instances_presumed") or []),
            **key_fields(pair, index), "ask": ask,
            "title": rec.get("title", ""), "date": rec.get("date", ""),
            "url": rec.get("url", ""), "rules_say": say,
            "settled_by_rules": ("" if not v else "no" if v.get("status") == "review"
                                 else "yes"),
            "why_a_person": "; ".join(v.get("review_why") or []),
            "confidence": gate.get("confidence", ""),
            "counterfactual": rules.labels_of(v).get("counterfactual_resolved") or "",
            "by_presumption": "" if not v else "yes" if v.get("by_presumption") else "no",
            "key_quote": cut(" | ".join(quotes)),
            "decided": log.get("decision", ""), "decided_on": log.get("decided_on", ""),
            "decided_reason": log.get("reason", ""),
            "dossier_multi_agent": sheet_value(dos.get("multi_agent")) if dos else "",
            "dossier_failure_mode": (dos.get("failure_mode") or "") if dos else "",
            "dossier_instances": sheet_value(dos.get("instances")) if dos else "",
            "dossier_verification": (dos.get("verification") or "") if dos else "",
            "read_depth": best_depth(ctx) if ctx else "",
            "agent_count": ctx.get("agent_count", ""),
            **{f"{f}_reading": reading_cell((ctx.get("facts") or {}).get(f))
               for f in CONTEXT_FACTS},
            "instances_proposed": instances_cell(prop.get("instances")),
            "instances_rejected": instances_cell(prop.get("considered_and_rejected")),
            "instances_note": prop.get("uncertainty_reason", ""),
            "_pair": pair,
            "_order": ({"yes": 0, "check": 1, "decided": 2, "dossier": 3}[ask],
                       0 if say == "in" else 1 if v.get("status") == "review" else 2,
                       natural(key))})
    rows.sort(key=lambda r: r["_order"])
    return rows


# The model's answers to the extract_gate questions, in prompt order
# (0.2/prompts/extract_gate.v4.md). QUOTED_FIELDS also get a `<field>_quote` column.
MODEL_FIELDS = ["n_ai_agents", "agent_names", "interaction_present", "interaction_kind",
                "setting", "stakes", "environment_controlled_by",
                "single_agent_counterfactual", "multiplicity_role", "cooperation_occurred",
                "cooperation_expected", "objective_relation", "confidence",
                "uncertainty_reason"]
QUOTED_FIELDS = ["n_ai_agents", "agent_names", "interaction_present", "interaction_kind",
                 "setting", "stakes", "environment_controlled_by",
                 "single_agent_counterfactual", "multiplicity_role", "cooperation_occurred",
                 "cooperation_expected", "objective_relation"]
SCOPE_COLUMNS = (["mig_key", "source_id", "source_key", "ask", "title", "date", "url", "rules_say", "settled_by_rules",
                  "why_a_person", "confidence", "counterfactual", "by_presumption",
                  "key_quote", "decision", "reason",
                  "is_attack", "presumption_fires", "gate1", "status", "evidence_type",
                  "failure_mode", "instances_presumed", "prompt"]
                 + [c for f in MODEL_FIELDS if f != "confidence"
                    for c in ([f, f"{f}_quote"] if f in QUOTED_FIELDS else [f])]
                 + ["decided", "decided_on", "decided_reason", "dossier_multi_agent",
                    "dossier_failure_mode", "dossier_instances", "dossier_verification",
                    "read_depth", "agent_count"]
                 + [f"{f}_reading" for f in CONTEXT_FACTS]
                 + ["instances_proposed", "instances_rejected", "instances_note"])


def clean(value):
    """Cell text: no control characters, and nothing that Excel would read as a formula."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value if value is not None else ""))
    return " " + text if text.startswith("=") else text


def stage_review():
    """The review step (decide.py), in order: read sheet 1 (scope, duplicate_of), make
    the dossiers of the records decided in and new, join the duplicates to their
    incident; place the incidents in the ledger; read sheet 2 (the incidents' labels and
    facts); write every dossier's frontmatter from the ledger; propose duplicates; write
    both sheets again; say what is left. Without openpyxl the sheets are skipped."""
    decide.ensure_logs(THIS)
    records = latest_records()
    new_keys = assign_mig_keys(set(read_verdicts()) | {p for p in records if p[0] == MANUAL})
    if new_keys:
        info(f"  ok    gave {len(new_keys)} record(s) a MIG key "
             f"({min(new_keys.values())} to {max(new_keys.values())}) in "
             f"{MIG_KEYS.relative_to(ROOT)}")
    decided, fresh, unreadable = {"records": 0, "incidents": 0}, {}, set()
    sheets = {"records": decide.RECORDS, "incidents": decide.INCIDENTS}
    if openpyxl is None:
        info(f"  warn  {OPENPYXL_HINT}. The review sheets are skipped; the run goes on.")
    else:
        try:
            decided["records"], fresh = decide.read_records_sheet(THIS, records)
        except ValueError as e:
            unreadable.add("records")
            info(f"  FAIL  {decide.RECORDS['file']} cannot be read ({e}). It is left as it "
                 f"is and not rewritten; fix or delete it.")
    n = decide.place_incidents(THIS, fresh)
    decide.write_decision_columns(THIS)
    if openpyxl is not None:
        try:
            decided["incidents"] = decide.read_incidents_sheet(THIS)
        except ValueError as e:
            unreadable.add("incidents")
            info(f"  FAIL  {decide.INCIDENTS['file']} cannot be read ({e}). It is left as "
                 f"it is and not rewritten; fix or delete it.")
    rendered = decide.render(THIS)
    if rendered:
        info(f"  ok    wrote the labels and facts of {rendered} dossier(s) from the ledger")
    stage_dedupe()
    if openpyxl is not None:
        if "records" not in unreadable:
            decide.write_records_sheet(THIS, records)
        if "incidents" not in unreadable:
            decide.write_incidents_sheet(THIS)
    state = decide.records_state(THIS, records)
    open_labels = sum(1 for r in decide.canonical_rows(THIS).values()
                      if any(not r[f"{l}_decision"] for l in decide.LABELS))
    for kind, k in (("records", "scope"), ("incidents", "edit")):
        REVIEW_DECIDED[k] += decided[kind]
    result = {"openpyxl": openpyxl is not None, "incidents_total": n}
    for kind, left in (("records", len(state)), ("incidents", open_labels)):
        result[kind] = {"decided": decided[kind], "left": left,
                        "path": str((REVIEW / sheets[kind]["file"]).relative_to(ROOT))}
    result["records"]["asked"] = sum(1 for v in state.values() if v in ("yes", "duplicate"))
    where = lambda kind: result[kind]["path"] if openpyxl is not None \
        else "no sheet: openpyxl missing"
    info(f"  ok    records    decided this run {decided['records']:4d}   left "
         f"{len(state):4d} (asking you {result['records']['asked']})   {where('records')}")
    info(f"  ok    incidents  decided this run {decided['incidents']:4d}   with labels to "
         f"decide {open_labels:4d} of {n}   {where('incidents')}")
    return result


def check_review_logs(records, problems, warnings):
    """How the record decisions agree with the incidents (decide.check_logs checks the
    logs themselves): an incident given to a record rests on a scope decision `in`, and
    no incident in scope rests on a record a person decided out."""
    scope = scope_newest(records)
    for key, row in sorted(newest_by_key(read_log("promote")).items()):
        if row["label"] == "duplicate_of" and scope.get(key, {}).get("decision") != "in":
            problems.append(f"0.2/review/{decide.LOGS['record']}: {row['mig_key']} has "
                            f"duplicate_of {row['final']} but no newest scope decision `in`")
    real = newest_by_key(read_log("scope"))
    for path in all_dossiers():
        meta, _ = read_dossier(path)
        for s in meta.get("sources") or []:
            key = record_key(s.get("source_id"), str(s.get("record_id")))
            decision = real.get(key, {}).get("decision")
            rel_d = path.relative_to(ROOT)
            said = f"{s.get('source_id')} {source_key(s.get('source_id'), s.get('record_id'))}"
            if decision == "out" and meta.get("multi_agent") is True:
                problems.append(f"{rel_d}: in scope, but the newest scope decision for its "
                                f"source {said} is `out`. Decide again on sheet 1, or set "
                                f"incident_scope on sheet 2.")
            elif decision == "in" and meta.get("multi_agent") is False:
                warnings.append(f"{rel_d}: out of scope; the scope decision for its source "
                                f"{said} was `in`. The incident's decision is the later, "
                                f"fuller judgement.")


# ----------------------------------------------- the values a person types on a sheet
#
# How sheet 2 (decide.py) reads a fact a person changed: parse_edit, with the kind of
# value each field holds. Until 0.2 a third sheet edited the dossiers directly and named
# each field it set in the dossier's `set_by_person`; that key is no longer written, and
# check still validates it where an old dossier has it.

SET_BY_PERSON = "set_by_person"
# The dossier fields a person may set, and what kind of value each holds.
EDIT_FIELDS = {
    "title": "text", "multi_agent": "scope", "failure_mode": "choice",
    "instances": "list", "instances_presumed": "list", "evidence_type": "choice",
    "verification": "choice", "last_verified": "date", "actor_count": "text",
    "interaction_kind": "choice", "occurrence_date": "date", "systems": "list",
}
PERSON_SETTABLE = list(EDIT_FIELDS) + ["multi_agent_basis"]


def edit_choices():
    fms = [r["risk_id"] for r in read_csv(TAXONOMY / "risks.csv")
           if r["risk_id"].startswith("FM")]
    return {"multi_agent": ["true", "false", "unclear"], "failure_mode": fms,
            "evidence_type": EVIDENCE_TYPES, "verification": VERIFICATION,
            "interaction_kind": INTERACTION_KINDS}


def edit_text(field, value):
    """A dossier value as sheet text: the same value always gives the same text."""
    if field == "multi_agent":
        if value is True:
            return "true"
        if value is False:
            return "false"
        return str(value or "unclear")
    if EDIT_FIELDS.get(field) == "list":
        return "; ".join(str(v) for v in value or [])
    return "" if value is None else str(value)


def cell_text(value):
    """What a cell holds, as text. Excel turns a typed date into a date and a typed year
    into a number; both come back as the text they were typed as."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_edit(field, text, choices):
    """Sheet text -> (dossier value, its sheet text). Raises ValueError."""
    kind = EDIT_FIELDS[field]
    if kind == "scope":
        if text.lower() not in choices[field]:
            raise ValueError(f"multi_agent {text!r} is not one of true, false, unclear")
        value = {"true": True, "false": False}.get(text.lower(), "unclear")
    elif kind == "choice":
        if not text and field == "failure_mode":
            value = None
        elif text not in choices[field]:
            raise ValueError(f"{field} {text!r} is not one of {', '.join(choices[field])}")
        else:
            value = text
    elif kind == "list":
        value = [p.strip() for p in text.split(";") if p.strip()]
        if field.startswith("instances"):
            value = [v.upper() for v in value]
    elif kind == "date":
        if not text and field == "last_verified":
            value = ""
        elif not parse_iso(text)[0]:
            raise ValueError(f"{field} {text!r} is not an ISO date (2026, 2026-06 or "
                             f"2026-06-18)")
        else:
            value = text
    else:
        if not text and field == "title":
            raise ValueError("title is empty")
        value = int(text) if field == "actor_count" and text.isdigit() else text
    return value, edit_text(field, value)


def add_to_section(body, name, text):
    """The body with `text` added as a paragraph at the end of section `name`. A section
    holding only the _pending_ placeholder is replaced."""
    m = re.search(rf"^## {re.escape(name)}[ \t]*\n", body, re.M)
    if not m:
        return None
    nxt = re.search(r"^## ", body[m.end():], re.M)
    end = m.end() + nxt.start() if nxt else len(body)
    sec = body[m.end():end].strip()
    if sec == "_pending_":
        sec = ""
    new = "\n" + (sec + "\n\n" if sec else "") + text + "\n" + ("\n" if nxt else "")
    return body[:m.end()] + new + body[end:]


# -------------------------------------------------------------------- index

STAGES = [
    "1 Prefilter: not screened",
    "1 Prefilter: outside rater said no",
    "1 Prefilter: no rule queues it",
    "2 Reading: one agent or none",
    "2 Reading: not yet judged",
    "3 Rules: out, not decided by a person",
    "3 Rules: unsettled, not decided by a person",
    "4 Person: decided out",
    "4 Person: decided unclear",
    "5 Person: decided in, no dossier",
    "5 Person: decided in, awaiting duplicate_of",
    "6 Incident: out of scope",
    "6 Incident: scope unclear",
    "7 Incident: in the index",
]


def rules_reason(v, g):
    """Why the rules leave a record out or unsettled, from the verdict and the facts."""
    labels = rules.labels_of(v)
    n = rules.agent_count(g) if g else None
    cf = labels.get("counterfactual_resolved")
    if rules_say(v) == "out":
        if n is not None and n < 2:
            return f"The facts show fewer than two AI agents ({n}), so no agents interacted."
        if cf == "could":
            if g and rules.is_security(g) and g.get("multiplicity_role") == "incidental":
                return "The rules say out: the harm turned on one agent's capability."
            return "The rules say out: one capable agent could have produced this outcome."
        if not (g and rules.is_security(g)) and g.get("interaction_present") is not True:
            return "The rules say out: no interaction between AI agents is shown."
        return "The rules say out."
    return f"The rules could not settle scope ({', '.join(v.get('review_why') or []) or 'not settled'})."


def ledger_outcome():
    """Every record's stage, reason and in_index, from the ledger's other columns. One
    function, one place (0.2/docs/plan.md, 3.9)."""
    rows = ledger.read(LEDGER)
    canon = decide.canonical_rows(THIS)
    verdicts = read_verdicts()
    gates = proposal_rows("extract_gate")
    frozen = read_frozen()
    records = latest_records()
    updates = {}
    for key, r in rows.items():
        pair = split_key(key)
        inc = r["incident_key"]
        if inc:
            c = canon.get(inc, {})
            scope = decide.effective(c, "incident_scope")
            stage = {"in": "7 Incident: in the index", "out": "6 Incident: out of scope"}.get(
                scope, "6 Incident: scope unclear")
            how = "decided" if c.get("incident_scope_decision") else "proposed"
            why = (f"Incident {inc}, scope {scope or 'none'} ({how})"
                   + ("" if r["canonical"] == "true" else "; this record is a further source")
                   + ".")
            updates[key] = {"in_index": scope == "in", "stage": stage, "reason": why}
            continue
        rec = records.get(pair, {})
        if r["queued"] != "true":
            if pair[0] == MA_SOURCE and r["date"] >= RECENT_FROM and outside_says_no(rec):
                stage, why = "1 Prefilter: outside rater said no", (
                    "An outside rater answered the multi-agent question no, and none said "
                    "yes or maybe; for 2024+ records the project acts on that answer.")
            elif pair[0] == MA_SOURCE and r["date"] < RECENT_FROM and key not in frozen:
                stage, why = "1 Prefilter: not screened", (
                    "Dated before 2024 and not on the frozen pre-2024 list, so the "
                    "pipeline never screened it.")
            else:
                stage, why = "1 Prefilter: no rule queues it", (
                    "No prefilter rule queues it (not a recent AIID record, not on the "
                    "frozen list, not added by hand).")
        elif r["agent_count"] in ("one", "none") and not r["rules_status"]:
            stage, why = "2 Reading: one agent or none", (
                ("No AI agent acts in the event." if r["agent_count"] == "none"
                 else "Only one AI agent acts in the event.")
                + f" A multi-agent incident needs two or more ({r['read_depth']} reading).")
        elif not r["rules_status"] and pair[0] != MANUAL:
            stage, why = "2 Reading: not yet judged", "Queued, but its reading is not complete."
        elif r["scope_final"] == "out":
            stage, why = "4 Person: decided out", "A person decided it is not a multi-agent incident."
        elif r["scope_final"] == "unclear":
            stage, why = "4 Person: decided unclear", ("A person decided the source was read "
                                                      "and does not say.")
        elif r["scope_final"] == "in" and r["dossier_final"] == "no":
            stage, why = "5 Person: decided in, no dossier", "Decided in, then given no dossier."
        elif r["scope_final"] == "in":
            stage, why = "5 Person: decided in, awaiting duplicate_of", (
                "Decided in; new incident or an existing one is not decided yet.")
        else:
            v = verdicts.get(pair)
            stage = ("3 Rules: out, not decided by a person" if v and rules_say(v) == "out"
                     else "3 Rules: unsettled, not decided by a person")
            why = rules_reason(v, gates.get(pair, {})) if v else "No verdict."
        updates[key] = {"in_index": False, "stage": stage, "reason": why}
    ledger.write(LEDGER, "outcome", updates)
    return updates


def ledger_stages():
    """{stage: records}, in STAGES order, from the ledger; empty before the first index."""
    if not LEDGER.exists():
        return {}
    counts = {}
    for r in ledger.read(LEDGER).values():
        if r["stage"]:
            counts[r["stage"]] = counts.get(r["stage"], 0) + 1
    return {s: counts[s] for s in STAGES if s in counts}


def stage_index():
    if LEDGER.exists():
        decide.place_incidents(THIS)
        out = ledger_outcome()
        n_in = len({r["incident_key"] for k, r in ledger.read(LEDGER).items()
                    if r["in_index"] == "true"})
        info(f"  ok    ledger: stage and reason of {len(out)} records; {n_in} incidents in "
             f"the index")
    rows = index_rows()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "incident_index.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["mig_key"])
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
            "mig_key": meta.get("mig_key", ""),
            "source_key": meta.get("source_key") or "",
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
    rows.sort(key=lambda r: (r["occurrence_date"], r["mig_key"]))
    return rows


def pipeline_state(index_rows):
    reg = registry()
    records = latest_records()
    queue = read_queue()
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

    return {
        "generated": TODAY,
        "generated_at": datetime.now().isoformat(timespec="minutes"),
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
             "detail": {**basis_counts(queue),
                        **{f"flagged {f}": n for f, n in flag_counts(queue).items()}}},
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
                   ("source_id", "source_record_id", "record_key", "date", "title",
                    "basis", "flags", "label_values", "keyword_terms", "url")} for row in queue],
        "registry": [{"source_id": r["source_id"], "name": r["name"],
                      "role": r["role"], "access_method": r["access_method"],
                      "adapter": r["adapter"], "status": r["status"],
                      "external_ma_label": r["external_ma_label"],
                      "reuse_status": r["reuse_status"]}
                     for r in sorted(reg.values(), key=lambda x: (x["role"], x["source_id"]))],
    }


# Where each step of the dataflow map keeps what it makes. Paths are relative to 0.2/.
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
    "prefilter": [("The queue of candidates: column queued", "ledger/ledger.csv")],
    "outscope": [("The readings that settled it", "context/"),
                 ("The readiness report", "state/readiness.jsonl")],
    "readrec": [("Readings, one file per source", "context/"),
                ("The instructions the model follows", "prompts/enrich_context.v2.md")],
    "readsrc": [("Readings, one file per source", "context/"),
                ("The instructions the model follows", "prompts/enrich_context.v2.md")],
    "ready": [("The readiness report", "state/readiness.jsonl"),
              ("How the rule works", "docs/context_layer.md")],
    "taxonomy": [("The risk instances", "taxonomy/instances.csv"),
                 ("Risks, risk instances and their links", "taxonomy/")],
    "extract": [("The instructions the model follows", "prompts/extract_gate.v4.md"),
                ("Where its output will be saved", "proposals/")],
    "gate1": [("The written rule", "docs/definitions.md"),
              ("The rule in code", "pipeline/derive.py"),
              ("Where its answers are saved", "ledger/ledger.csv")],
    "gate2": [("The written rule", "docs/definitions.md"),
              ("The rule in code", "pipeline/derive.py"),
              ("Where its answers are saved", "ledger/ledger.csv")],
    "evtype": [("The four evidence types", "taxonomy/evidence_types.csv"),
               ("The rule in code", "pipeline/derive.py"),
               ("Where its answers are saved", "ledger/ledger.csv")],
    "instances": [("The named patterns", "taxonomy/instances.csv"),
                  ("The instructions the model follows", "prompts/assign_instances.v2.md"),
                  ("Where its output will be saved", "proposals/"),
                  ("Records in scope still without one", "state/instances_due.jsonl")],
    "proposals": [("The suggestions", "proposals/")],
    "scope": [("The sheet to fill in", "review/1_records.xlsx"),
              ("The decisions so far", "review/record_decisions_log.csv"),
              ("How to fill it in", "review/README.md")],
    "review": [("The sheet to fill in", "review/1_records.xlsx"),
               ("The decisions so far", "review/record_decisions_log.csv"),
               ("The incident files a person writes", "incidents/")],
    "dossiers": [("The incident files", "incidents/"),
                 ("The sheet for their labels and facts", "review/2_incidents.xlsx"),
                 ("Where the labels live", "ledger/ledger.csv")],
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
    verdict = readiness(ctx, flagged=is_flagged(row.get("flags")))
    level = verdict["scope"]["level"]
    if row.get("basis") == BASIS_MANUAL and level in ("ready", "provisional") \
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
    # the Fetch box's breakdown: which fetched records the pipeline looks at
    f_dossier = fetched & to_dossier
    f_recent = {k for k in fetched & queued if qrows[k].get("basis") == BASIS_RECENT}
    f_frozen = {k for k in fetched & queued if qrows[k].get("basis") == BASIS_FROZEN}
    f_old = {k for k in fetched & not_queued
             if k[0] == MA_SOURCE and records[k].get("date", "") < RECENT_FROM}
    f_said_no = {k for k in fetched & not_queued - f_old
                 if k[0] == MA_SOURCE and outside_says_no(records[k])}
    f_other = (fetched & not_queued) - f_old - f_said_no

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
    derived_att = derived & attested
    early = (queued & attested) - derived_att   # a dossier before reaching Decide scope

    # the person's two decisions (0.2/review/): scope on sheet 1, promote on sheet 2.
    # A decision `in` has priority: the record goes on to Human review, and from there
    # to the dossiers. Then a record already in a dossier goes straight to the dossiers.
    # Of the rest, a decision `out` or `unclear` ends here, and the others are left.
    scope_log = scope_newest(records)
    promo_log = newest_by_key(read_log("promote"))
    decision = lambda k: (scope_log.get(record_key(*k)) or {}).get("decision")
    dec_in = {k for k in derived if decision(k) == "in"}
    a_only = derived_att - dec_in
    rest = derived - dec_in - a_only
    dec_out = {k for k in rest if decision(k) == "out"}
    dec_unc = {k for k in rest if decision(k) == "unclear"}
    left = rest - dec_out - dec_unc
    promoted = dec_in & attested
    promo_no = {k for k in dec_in - attested
                if (promo_log.get(record_key(*k)) or {}).get("decision") == "no"}
    review_left = dec_in - attested - promo_no
    rs = review_state(records)
    said = lambda k: rules_say(verdicts[k])

    # dossier facts, per record
    dossier_of, dmeta = {}, {}
    for path in all_dossiers():
        meta, _ = read_dossier(path)
        dmeta[meta.get("mig_key", path.stem)] = meta
        for s in meta.get("sources") or []:
            dossier_of[(s.get("source_id"), str(s.get("record_id")))] = \
                meta.get("mig_key", path.stem)
    in_dossiers = to_dossier | derived_att
    # From the Dossiers box on, the map counts incidents, not records: the records
    # one dossier lists are one incident. Keyed (canonical source, mig_key), so
    # by_source counts each incident once, under its canonical source.
    d_keys = {(dmeta.get(m, {}).get("canonical_source") or "unknown", m)
              for m in {dossier_of[k] for k in in_dossiers if k in dossier_of}}
    d_in = {d for d in d_keys if dmeta.get(d[1], {}).get("multi_agent") is True}
    d_flagged = d_keys - d_in
    merged = len(in_dossiers) - len(d_keys)
    scope_word = {True: "in", False: "out"}
    d_scope = {"in": 0, "out": 0, "unclear": 0}   # per record, for the conservation check
    for k in in_dossiers:
        meta = dmeta.get(dossier_of.get(k), {})
        d_scope[scope_word.get(meta.get("multi_agent"), "unclear")] += 1
    # the same facts counted per dossier file, the unit a person reads
    f_scope, f_ver, f_claude = {"in": 0, "out": 0, "unclear": 0}, {}, 0
    for path in all_dossiers():
        meta, body = read_dossier(path)
        f_scope[scope_word.get(meta.get("multi_agent"), "unclear")] += 1
        v = meta.get("verification") or "not set"
        f_ver[v] = f_ver.get(v, 0) + 1
        f_claude += "Written by Claude" in (body or "")

    # risk instances: proposed only after a person decides scope. On the main path
    # they come between Decide scope and Human review, for the records decided in;
    # a person's in-scope dossier with no instances is due too (the Dossiers box).
    inst = proposal_rows("assign_instances")
    by_person = {k for k in in_dossiers
                 if dmeta.get(dossier_of.get(k), {}).get("multi_agent") is True
                 and dmeta.get(dossier_of.get(k), {}).get("multi_agent_label_source") == "ours"}
    in_scope = dec_in | by_person

    def inst_split(keys):
        has = {k for k in keys if k in inst}
        lst = {k for k in keys - has if dmeta.get(dossier_of.get(k), {}).get("instances")}
        return has, lst, keys - has - lst
    has_inst, listed, due = inst_split(in_scope)
    dec_has, dec_listed, dec_due = inst_split(dec_in)
    dos_has, dos_listed, dos_due = inst_split(by_person)
    due_rows = len(instances_due())

    def agent_count(k):
        return (context.get(k) or {}).get("agent_count") or "not said"

    depth_rows = {}
    for k in read_deeper:
        d = best_depth(context.get(k))
        depth_rows[d] = depth_rows.get(d, 0) + 1
    DEPTH_WORDS = {"secondary": "the database's own page, read in full; the article it cites not read",
                   "curator": "the curator's own write-up",
                   "primary_partial": "the original source, read in part",
                   "primary_full": "the original source, read in full"}
    conf = {}
    for k in extracted:
        c = gates[k].get("confidence") or "not given"
        conf[c] = conf.get(c, 0) + 1
    basis = basis_counts([qrows[k] for k in queued])
    flag_n = flag_counts([qrows[k] for k in queued])
    flagged = sum(1 for k in queued if is_flagged(qrows[k].get("flags")))
    levels = {}
    for k in src_ready:
        lv = verdicts_r[k]["scope"]["level"]
        levels[lv] = levels.get(lv, 0) + 1
    STATUS_WORDS = {"in_scope": "The rules' answer: in (settled by the rules)",
                    "out_of_scope": "The rules' answer: out (settled by the rules)",
                    "review": "No answer from the rules: needs a person"}
    split = {s: sum(1 for k in derived if status_of[k] == s) for s in rules.STATUSES}
    # the attack presumption: on a settled "in" it decided the answer; on a review row it
    # only shapes the label the rules would give if a person confirmed the facts
    presumed = {s: sum(1 for k in derived if status_of[k] == s
                       and verdicts[k].get("by_presumption")) for s in rules.STATUSES}
    prompts_used = {}
    for k in derived:
        p = verdicts[k].get("prompt") or "not recorded"
        prompts_used[p] = prompts_used.get(p, 0) + 1

    # derive.py runs three rules in turn on each record: Gate 1 (is it multi-agent?),
    # then the evidence type (every record), then Gate 2 (only a record Gate 1 let in).
    # The map draws them in that order; each box shows its own rule's answer, and the
    # last one passes the rules' final answers to Decide scope.
    lab = {k: rules.labels_of(verdicts[k]) for k in derived}
    G1_WORDS = {"in": "In: more than one agent was needed",
                "out": "Out: one agent could have done it, or the agents did not act on each other",
                "review": "Unclear: a fact Gate 1 turns on is unclear",
                "curator": "Added by hand: in on the curator's word"}
    g1 = {}
    for k in derived:
        a = verdicts[k].get("gate1") or "not recorded"
        g1[a] = g1.get(a, 0) + 1
    ET_WORDS = {"real_world": "Real world", "synthetic": "Synthetic: a simulation somebody built",
                "lab": "Lab: a narrow test", "theoretical": "Theoretical: an argument on paper",
                "none": "None: the facts do not settle it"}
    et = {}
    for k in derived:
        v = lab[k].get("evidence_type") or "none"
        et[v] = et.get(v, 0) + 1
    asked2 = {k for k in derived
              if lab[k].get("multi_agent") is True or verdicts[k].get("gate1") == "curator"}
    FM_WORDS = {"FM1": "FM1 Miscoordination", "FM2": "FM2 Conflict", "FM3": "FM3 Collusion",
                "none": "None of the three"}
    fm = {}
    for k in asked2:
        v = lab[k].get("failure_mode") or "none"
        fm[v] = fm.get(v, 0) + 1
    whys = {}
    for k in derived:
        for w in verdicts[k].get("review_why") or []:
            w = "confidence not high" if w.startswith("confidence") else w
            whys[w] = whys.get(w, 0) + 1
    WHY_WORDS = {"confidence not high": "The model was not highly confident",
                 "interaction_present": "Gate 1: unclear whether the agents acted on each other",
                 "single_agent_counterfactual": "Gate 1: unclear whether one agent could have done it",
                 "cooperation_occurred": "Gate 2: unclear whether they cooperated",
                 "cooperation_expected": "Gate 2: unclear whether cooperation was expected",
                 "objective_relation": "Gate 2: unclear how their goals relate",
                 "evidence type not derivable": "Evidence type: the facts do not settle it"}

    def decided_as(k):
        if k in dec_in:
            return "in"
        if k in a_only:
            return "dossier"
        return decision(k) if k in dec_out | dec_unc else "left"

    cross = {}
    for k in derived:
        cross[(said(k), decided_as(k))] = cross.get((said(k), decided_as(k)), 0) + 1
    DECIDED_WORDS = {"in": "a person decided in", "out": "a person decided out",
                     "unclear": "a person decided unclear",
                     "dossier": "already in a dossier", "left": "still to decide"}
    cross_rows = [(f"The rules said {r}: {DECIDED_WORDS[d]}", cross[(r, d)],
                   f"rules_say {r}; {d}")
                  for r in ("in", "out", "unclear")
                  for d in ("in", "out", "unclear", "dossier", "left") if cross.get((r, d))]

    E = lambda to, keys, label, branch=False: {"to": to, "n": len(keys), "label": label,
                                               "branch": branch}
    nodes = [
        {"id": "fetch", "n": len(fetched), "origin": True, "in": len(fetched),
         "out": [E("normalise", fetched, "records collected")], "stop": [], "held": 0,
         "pop": fetched,
         "groups": [{"title": "Records per source", "rows": rows(
             *[(f"{sid}", n, f"records/{sid}.jsonl") for sid, n in by_source(fetched).items()])},
             {"title": "Which records the pipeline looks at",
              "note": f"AIID is fetched in full, but only incidents dated {RECENT_FROM} or "
                      "later are looked at, and of those only the ones no outside rater "
                      "has already answered \"no\" on: where an outside answer exists, it "
                      "is acted on. An earlier incident is looked at only if it is on the "
                      "frozen list: pre-2024 candidates analysed before 2026-11-17.",
              "rows": rows(
                  (f"Dated {RECENT_FROM} or later: queued as candidates", len(f_recent),
                   "queue_basis recent in ledger/ledger.csv"),
                  (f"Dated {RECENT_FROM} or later, an outside rater said not multi-agent",
                   len(f_said_no), "outside_says_no(): a Multiple AI Interaction label, none yes or maybe"),
                  ("Before 2024, on the frozen list: queued as candidates", len(f_frozen),
                   "basis frozen: registry/frozen_pre2024.csv"),
                  ("Already in a dossier: a dossier lists it as a source", len(f_dossier),
                   "dossier_source_refs()"),
                  ("Not looked at: before 2024 and not on the frozen list", len(f_old),
                   f"AIID, dated before {RECENT_FROM}, not queued in ledger/ledger.csv"),
                  *([("Not looked at: a source the prefilter does not queue", len(f_other),
                      "not queued in ledger/ledger.csv, not behind a dossier")] if f_other else []))}],
         "files": ["raw/aiid/", "records/<source>.jsonl", "registry/frozen_pre2024.csv"],
         "rule": "records of every source but manual: latest_records(). Looked at: "
                 f"AIID dated {RECENT_FROM} or later, or on registry/frozen_pre2024.csv"},
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
                 E("ready", bypass, "added by hand: on the curator's word")],
         "stop": [s for s in (
             {"label": "not looked at: before 2024 and not on the frozen list (see Fetch)",
              "n": len(not_queued - f_said_no)},
             {"label": "an outside rater said not multi-agent (see Fetch)",
              "n": len(f_said_no)}) if s["n"]],
         "held": 0, "pop": allkeys,
         "groups": [
             {"title": "Candidates per source", "rows": rows(
                 *[(sid, n, "ledger/ledger.csv") for sid, n in by_source(queued).items()])},
             {"title": "Every record goes one of three ways", "rows": rows(
                 ("Already in a dossier: a dossier lists it as a source", len(to_dossier),
                  "dossier_source_refs() and not queued in ledger/ledger.csv"),
                 ("Queued as a candidate", len(queued), "queued true in ledger/ledger.csv"),
                 ("Not queued: before 2024 and not on the frozen list, or an outside "
                  "rater said not multi-agent", len(not_queued),
                  "neither in the queue nor behind a dossier"))},
             {"title": "Why each candidate was queued",
              "note": "Each candidate has exactly one reason, so these add up to the candidates.",
              "rows": rows(
                  (f"Recent: an AIID record dated {RECENT_FROM} or later that no outside rater answered no on",
                   basis.get(BASIS_RECENT, 0), "basis recent"),
                  ("Frozen: a pre-2024 record on the hand-kept list",
                   basis.get(BASIS_FROZEN, 0), "basis frozen: registry/frozen_pre2024.csv"),
                  ("Added by hand", basis.get(BASIS_MANUAL, 0), "basis manual"))},
             {"title": "Flagged",
              "note": "A flag never queues a record by itself. A record can carry both flags, so the two counts can add up to more than the flagged.",
              "rows": rows(
                  ("Tagged multi-agent by someone else", flag_n.get("label", 0), "flag label"),
                  ("Matched a keyword", flag_n.get("keyword", 0), "flag keyword"),
                  ("Flagged by a tag or a keyword: never dismissed on the record text alone",
                   flagged, "is_flagged(flags): flags is not empty"),
                  ("Not flagged", len(queued) - flagged, ""))}],
         "files": ["ledger/ledger.csv", "registry/frozen_pre2024.csv", "incidents/"],
         "rule": "stage_prefilter(): queued = recent AIID, frozen pre-2024 or manual; flagged = an outside label or a keyword; records behind a dossier are left out"},
        {"id": "readrec", "n": len(read_any), "in": len(to_readrec),
         "out": [E("outscope", oos_record, "screened out on the record text"),
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
         "files": ["context/<source>.jsonl", "ledger/ledger.csv"],
         "rule": "queued records, not added by hand; read = has a context row"},
        {"id": "readsrc", "n": len(read_deeper), "in": len(to_readsrc),
         "out": [E("outscope", oos_source, "screened out on the source"),
                 E("ready", src_ready, "ready for the questions")],
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
         "stop": [{"label": "screened out: one agent or none", "n": len(oos_record) + len(oos_source)}],
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
         "out": [E("extract", ready, "ready for the questions")], "stop": [], "held": 0,
         "pop": ready,
         "groups": [{"title": "How firm", "rows": rows(
             ("Original source read in full", levels.get("ready", 0), "scope ready"),
             ("Facts from a partial or secondary reading", levels.get("provisional", 0),
              "scope provisional"),
             ("Added by hand: in scope on the curator's word", len(bypass), "basis manual"))}],
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
         "out": [E("evtype", derived, "Gate 1's answers")],
         "stop": [], "held": len(extracted - derived), "held_label": "derive not run on it yet",
         "pop": extracted,
         "groups": [{"title": "Gate 1's answer",
                     "note": "Gate 1 alone, before the evidence type and Gate 2. The rules' "
                             "final answer, after all three, is on the Gate 2 box.",
                     "rows": rows(
             *[(G1_WORDS.get(a, a), n, f"gate1 {a}") for a, n in sorted(g1.items())])},
             {"title": "The attack presumption",
              "note": "An attack by many agents counts as in scope by default when the "
                      "source does not say what the number of agents added. These rows "
                      "rest on that default. A row that needs a person is not an answer: "
                      "it shows what the rules would say if a person confirmed the facts.",
              "rows": rows(
                  ("Settled in by the presumption", presumed["in_scope"],
                   "status in_scope, by_presumption true"),
                  ("Needs a person; would be in by the presumption if confirmed",
                   presumed["review"], "status review, by_presumption true"))},
             {"title": "Which prompt extracted the facts",
              "note": "Each answer rests on the facts of one extract_gate run. Older "
                      "answers keep the prompt version they were made with.",
              "rows": rows(*[(p, n, "verdict prompt") for p, n in sorted(prompts_used.items())])}],
         "files": ["ledger/ledger.csv", "pipeline/derive.py"],
         "rule": f"ledger/ledger.csv column gate1, rules {rules.RULES_VERSION}"},
        {"id": "evtype", "n": len(derived), "in": len(derived),
         "out": [E("gate2", derived, "with an evidence type, or none")],
         "stop": [], "held": 0, "pop": derived,
         "groups": [{"title": "Evidence type, by the rules",
                     "note": "Worked out for every record, in or out. On a record that "
                             "needs a person it is what the rules would give if the facts "
                             "were confirmed. None sends an in-scope record to a person.",
                     "rows": rows(
             *[(ET_WORDS.get(v, v), n, f"evidence_type {v}") for v, n in sorted(et.items())])}],
         "files": ["ledger/ledger.csv", "pipeline/derive.py"],
         "rule": "labels_of(verdict).evidence_type over the records Gate 1 answered"},
        {"id": "gate2", "n": len(derived), "in": len(derived),
         "out": [E("scope", derived, "the rules' answers")],
         "stop": [], "held": 0, "pop": derived,
         "groups": [{"title": "Failure type, for the records Gate 1 let in",
                     "note": "Gate 2 runs on a record Gate 1 let in, on one it would let in "
                             "once an unclear fact is confirmed, and on one added by hand; "
                             "the others pass through it unchanged.",
                     "rows": rows(
                         *[(FM_WORDS.get(v, v), n, f"failure_mode {v}") for v, n in sorted(fm.items())],
                         ("Not asked: Gate 1 did not let it in", len(derived) - len(asked2),
                          "multi_agent not true"))},
                    {"title": "What the rules settled",
                     "note": "The rules' final answer, after Gate 1, the evidence type and "
                             "Gate 2. It goes to a person on the scope sheet as a suggestion.",
                     "rows": rows(
                         *[(STATUS_WORDS[s], split[s], f"status {s}") for s in rules.STATUSES])},
                    {"title": "Why a person is needed",
                     "note": "A record can have several reasons, so these can add up to more "
                             "than the records that need a person.",
                     "rows": rows(*[(WHY_WORDS.get(w, w), n, f"review_why {w}")
                                    for w, n in sorted(whys.items(), key=lambda x: -x[1])])}],
         "files": ["ledger/ledger.csv", "pipeline/derive.py"],
         "rule": f"labels_of(verdict).failure_mode and status, rules {rules.RULES_VERSION}"},
        {"id": "scope", "n": len(derived), "in": len(derived),
         "out": [E("instances", dec_in, "decided in"),
                 E("dossiers", a_only, "already in a dossier")],
         "stop": [{"label": "decided out by a person", "n": len(dec_out)},
                  {"label": "can't tell: unclear", "n": len(dec_unc)}],
         "held": len(left), "held_label": "left to decide",
         "pop": derived,
         "groups": [{"title": "What the rules said, and what a person decided",
                     "note": "The rules never put a record in scope: only a person's "
                             "decision does. `The rules said` is a suggestion.",
                     "rows": rows(*cross_rows)},
                    {"title": "What the rules said", "rows": rows(
                        *[(STATUS_WORDS[s], split[s], f"status {s}") for s in rules.STATUSES])},
                    {"title": "The sheet", "rows": rows(
                        ("Rows on the sheet left to decide", len(rs["scope"]),
                         "review/1_records.xlsx"),
                        ("Of those, asking for your judgement", len(rs["scope_ask"]),
                         "ask = yes: the rules would put it in, or confidence is low"),
                        ("Decisions in the log, newest per record", len(
                            newest_by_key(read_log("scope"))), "review/record_decisions_log.csv"))}],
         "files": ["review/1_records.xlsx", "review/record_decisions_log.csv",
                   "ledger/ledger.csv"],
         "rule": "records with a derived label; decided = the newest scope row of "
                 "review/record_decisions_log.csv (a hand-added record counts as decided in); "
                 "run.py review reads the sheet"},
        {"id": "review", "n": len(dec_in), "in": len(dec_in),
         "out": [E("dossiers", promoted, "to an incident: a new dossier, or joined to one")],
         "stop": [{"label": "no dossier: a person said no", "n": len(promo_no)}],
         "held": len(review_left), "held_label": "awaiting duplicate_of",
         "pop": dec_in,
         "groups": [{"title": "Status", "rows": rows(
             ("Decided in by a person", len(dec_in), "newest scope decision in"),
             ("In an incident: a dossier lists the record", len(promoted),
              "duplicate_of new, or an incident's MIG key"),
             ("No dossier: a person said no", len(promo_no),
              "label dossier, no (0.1's promote no)"),
             ("Awaiting duplicate_of, on the records sheet", len(review_left),
              "review/1_records.xlsx"))}],
         "files": ["review/1_records.xlsx", "review/record_decisions_log.csv", "incidents/"],
         "rule": "records a person decided in; duplicate_of new makes the dossier, a MIG key "
                 "joins the record to that incident; run.py review reads the sheet"},
        {"id": "dossiers", "n": len(d_keys), "in": len(in_dossiers),
         "out": [E("check", d_keys, "one per incident, to the check")],
         "stop": [{"label": "merged: another source's report of an incident already counted",
                   "n": merged}], "held": 0, "pop": in_dossiers,
         "groups": [{"title": "Records and incidents",
                     "note": "A dossier is our file on one incident. One incident can be "
                             "told by several sources, so one dossier can list several "
                             "records. From here on the map counts incidents.",
                     "rows": rows(
                         ("Source records listed in a dossier", len(in_dossiers),
                          "dossier sources ∩ records"),
                         ("Unique incidents: dossiers", len(d_keys), "incidents/<mig_key>.md"),
                         ("Records merged into an incident already counted", merged,
                          "records - incidents"))},
             {"title": "Dossiers, by the person's verdict",
              "note": "Every dossier is a row of the index, whatever the verdict: an "
                      "\"out\" dossier records that someone looked, and why it was turned away.",
              "rows": rows(
                  ("In scope", f_scope["in"], "incident_scope in (ledger)"),
                  ("Out of scope", f_scope["out"], "incident_scope out (ledger)"),
                  ("Unclear", f_scope["unclear"], "incident_scope unclear (ledger)"))},
             {"title": "Dossiers, by how well they were checked",
              "note": "Verified means a person checked the dossier against the original "
                      "source. Unverified dossiers are not yet checked facts.",
              "rows": rows(
                  *[(v.replace("_", " "), n, f"verification {v}") for v, n in sorted(f_ver.items())],
                  ("Of all dossiers: written by Claude", f_claude,
                   "## Verification notes open with \"Written by Claude\""))},
             {"title": "Risk instances, for the records a person put in scope",
              "note": "Counted per record. A dossier in scope with no instances is on "
                      "the to-do list of /classify-incidents, call 2.",
              "rows": rows(
                  ("In scope in a person's dossier", len(by_person),
                   "dossier multi_agent true, ours"),
                  ("Risk instances proposed", len(dos_has), "assign_instances proposal"),
                  ("The dossier already lists them", len(dos_listed), "dossier instances"),
                  ("None yet", len(dos_due), "neither"))}],
         "files": ["incidents/", "review/2_incidents.xlsx", "ledger/ledger.csv"],
         "rule": "records listed in a dossier's sources, counted once per incident; their "
                 "labels and facts live in the ledger and are decided on sheet 2"},
        {"id": "check", "n": len(d_keys), "in": len(d_keys), "per": "incidents",
         "out": [E("index", d_keys, "passed the check")], "stop": [], "held": 0,
         "pop": d_keys, "groups": [],
         "files": ["pipeline/run.py"], "rule": "run.py check validates every dossier"},
        {"id": "index", "n": len(d_keys), "in": len(d_keys), "per": "incidents", "out": [],
         "stop": [{"label": "in scope: shown in the report", "n": len(d_in)},
                  {"label": "kept with an out-of-scope or unclear flag", "n": len(d_flagged)}],
         "held": 0, "pop": d_keys,
         "groups": [{"title": "Table", "rows": rows(
             ("Rows: one per incident", len(index_rows), "out/incident_index.csv"),
             ("In scope: in the report", len(d_in), "multi_agent: true"),
             ("Out of scope or unclear: kept, flagged, not in the report", len(d_flagged),
              "multi_agent: false or unclear"))},
             {"title": "Where every record ended", "note": "The ledger's stage column, set "
              "by run.py index: one stage per loaded record.", "rows": rows(
                  *[(s, n, "ledger stage") for s, n in ledger_stages().items()])}],
         "files": ["out/incident_index.csv", "ledger/ledger.csv"],
         "rule": "index_rows(): one row per dossier; ledger_outcome(): every record's stage"},
        {"id": "instances", "n": len(dec_has | dec_listed), "in": len(dec_in),
         "out": [E("review", dec_in, "to the duplicate_of decision")],
         "stop": [], "held": 0,
         "pop": dec_in,
         "groups": [{"title": "Records a person decided in", "rows": rows(
             ("Decided in on the records sheet", len(dec_in),
              "review/record_decisions_log.csv scope in"),
             ("Risk instances proposed", len(dec_has), "assign_instances proposal"),
             ("The dossier already lists them", len(dec_listed), "dossier instances"),
             ("None proposed yet", len(dec_due), "neither"))},
             {"title": "The to-do list", "rows": rows(
                 ("Rows in the to-do list, dossiers included (one per dossier, not per record)",
                  due_rows, "state/instances_due.jsonl"))}],
         "files": ["proposals/assign_instances.<date>.jsonl", "state/instances_due.jsonl"],
         "rule": "proposal_rows('assign_instances') over the records a person decided in"},
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
    check("derived = decided in + decided out + unclear + already in a dossier + left to decide",
          len(derived), len(dec_in) + len(dec_out) + len(dec_unc) + len(a_only) + len(left))
    check("left to decide = undecided rows on the decide-scope sheet", len(left),
          len(rs["scope"]))
    check("decided in = in an incident + no dossier + awaiting duplicate_of", len(dec_in),
          len(promoted) + len(promo_no) + len(rs["promote"]))
    stages = ledger_stages()
    if stages:
        check("ledger: every loaded record has one stage", len(allkeys), sum(stages.values()))
        check("ledger: incidents in the index = incidents in scope on the map", len(d_in),
              len({r["incident_key"] for r in ledger.read(LEDGER).values()
                   if r["in_index"] == "true"}))
    check("in scope = proposed + already listed + waiting", len(in_scope),
          len(has_inst) + len(listed) + len(due))
    check("dossier verdicts add up", len(in_dossiers), sum(d_scope.values()))
    check("dossier files by verdict = dossiers", len(index_rows), sum(f_scope.values()))
    # fails when a queued record got a dossier before reaching review: rerun prefilter
    check("records behind a dossier = the Dossiers box", len(attested), len(in_dossiers))
    check("incidents on the map = dossier files", len(d_keys), len(index_rows))

    counts = {"records": len(allkeys), "queued": len(queued),
              "not_queued": len(not_queued), "in_dossier_already": len(to_dossier),
              "read_record": len(read_any), "read_source": len(read_deeper),
              "out_of_scope": len(oos_record) + len(oos_source), "ready": len(ready),
              "extracted": len(extracted), "derived": len(derived),
              "dossier_records": len(in_dossiers), "incidents": len(d_keys),
              "incidents_in_scope": len(d_in), "in_scope": len(in_scope),
              "instance_records": len(has_inst), "promoted_early": len(early),
              "scope_decided_in": len(dec_in), "scope_decided_out": len(dec_out),
              "scope_decided_unclear": len(dec_unc), "scope_left": len(left),
              "review_left": len(review_left), "review_promoted": len(promoted),
              "review_not_promoted": len(promo_no),
              "verdict_split": dict(split), "verdict_prompts": dict(sorted(prompts_used.items()))}
    return nodes, checks, counts


def pipeline_map(reg, records, queue, proposals, index_rows):
    """The numbers the dataflow map (0.2/pipeline/pipeline_flow.html) prints. Every
    count on the map is a number of records; `flow` carries them and `checks` the
    equations that must hold. See map_flow."""
    context = load_context()
    flow, checks, counts = map_flow(reg, records, queue, context, index_rows)
    # the rules' answers over the records that reached Gate 1 (the gate1 box), not every
    # verdict in the ledger: a verdict can outlive a record's readiness
    verdicts = dict(counts.get("verdict_split") or {s: 0 for s in rules.STATUSES})
    verdict_rows_all = len(read_verdicts())
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
    gold_path = TREE / "gold" / "multiagent_gold.csv"
    if gold_path.exists():
        for row in read_csv(gold_path):
            gold["rows"] += 1
            if row.get("review_verdict") in gold:
                gold[row["review_verdict"]] += 1
    acc = OUT / "gate1_accuracy.json"
    if acc.exists():
        predictors = json.loads(acc.read_text(encoding="utf-8"))["predictors"]
        ceiling = predictors.get("ceiling_hand_curation") or {}
        gold["ceiling"] = ceiling.get("precision")
        gold["ceiling_n"] = ceiling.get("n")
        # the classifier score: model + rules on the gold rows. Its headline counts the
        # review items by the labels the rules would give if a person confirmed them;
        # `settled` is the rows the rules decided alone. Say which prompt it measured.
        classifier = predictors.get("classifier") or {}
        settled = predictors.get("classifier_settled") or {}
        run = json.loads(acc.read_text(encoding="utf-8")).get("classifier_run") or {}
        gold["classifier_precision"] = classifier.get("precision")
        gold["classifier_recall"] = classifier.get("recall")
        gold["classifier_n"] = classifier.get("n")
        gold["classifier_review_items"] = classifier.get("review_items", run.get("review_items"))
        gold["classifier_settled_n"] = settled.get("n")
        gold["classifier_settled_precision"] = settled.get("precision")
        gold["classifier_settled_recall"] = settled.get("recall")
        gold["classifier_rules"] = run.get("rules_version")
        m = re.search(r"(extract_gate)_v(\d+)", run.get("input") or "")
        gold["classifier_prompt"] = f"{m.group(1)}.v{m.group(2)}" if m else None
        gold["classifier_input"] = run.get("input")
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
        "queue": len(queue), "queue_basis": basis_counts(queue),
        "queue_flags": flag_counts(queue),
        "flow": flow, "checks": checks, "flow_counts": counts,
        "sources_with_records": len(per_source),
        "manual": per_source.get(MANUAL, 0),
        "prefilter_rules": {
            "keywords": list(KEYWORD_TERMS), "recent_from": RECENT_FROM,
            "label_values": sorted(MA_POSITIVE),
            "where": f"0.2/pipeline/run.py:{inspect.getsourcelines(stage_prefilter)[1]}"},
        "aiid_snapshot": aiid_snapshot(),
        "gate_proposals": len(proposal_rows("extract_gate")),
        "instance_proposals": len(proposal_rows("assign_instances")),
        "verdicts": verdicts,
        "verdict_rows_all": verdict_rows_all,
        "verdict_prompts": counts.get("verdict_prompts") or {},
        "verdicts_rules": rules.RULES_VERSION,
        "instances_due": len(instances_due()),
        "dossiers": len(all_dossiers()), "dossier_scope": scope,
        "dossier_verification": verification, "dossier_failure_modes": failure_modes,
        "risks": len(read_csv(TAXONOMY / "risks.csv")),
        "instances": len(read_csv(TAXONOMY / "instances.csv")),
        "instances_by_provenance": count_by(read_csv(TAXONOMY / "instances.csv"), "provenance"),
        "dossiers_by_canonical": count_by([read_dossier(p)[0] for p in all_dossiers()],
                                          "canonical_source"),
        "gold": gold,
        "last_run": last_run_summary(),
        "artifacts": {node: [{"label": label, "path": newest_prompt(path),
                              "exists": (TREE / newest_prompt(path)).exists()}
                             for label, path in items]
                      for node, items in MAP_ARTIFACTS.items()},
    }


def count_by(rows, field):
    """How many rows hold each value of `field`; a missing value counts as "not set"."""
    out = {}
    for row in rows:
        v = str(row.get(field) or "not set")
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


def newest_prompt(path):
    """A prompt path `prompts/<id>.vN.md` turned into the newest version of that prompt on
    disk, so the map never names a version that has been replaced. Other paths as given."""
    m = re.fullmatch(r"prompts/(.+)\.v\d+\.md", path)
    if not m:
        return path
    found = [(int(re.search(r"\.v(\d+)\.md$", p.name).group(1)), p.name)
             for p in (TREE / "prompts").glob(f"{m.group(1)}.v*.md")
             if re.search(r"\.v(\d+)\.md$", p.name)]
    return f"prompts/{max(found)[1]}" if found else path


def last_run_summary():
    """The newest retained update or test run log: its id, state and when it ended."""
    logs = sorted(RUNS.glob("*.json")) if RUNS.exists() else []
    for p in reversed(logs):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        return {"id": d.get("id"), "state": d.get("state"), "test": bool(d.get("test")),
                "ended": d.get("ended") or d.get("started")}
    return None


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
    reg = registry()
    records = latest_records()
    seen_ids = set()

    frozen_rel = frozen_path().relative_to(ROOT)
    seen_frozen = set()
    for n, row in enumerate(read_frozen().values(), 1):
        key = row.get("record_key", "")
        pair = (row.get("source_id"), str(row.get("source_record_id")))
        if key != record_key(*pair):
            problems.append(f"{frozen_rel}: record_key {key!r} does not match its "
                            f"source_id and source_record_id")
        if key in seen_frozen:
            problems.append(f"{frozen_rel}: duplicate record_key {key!r}")
        seen_frozen.add(key)
        if pair not in records:
            problems.append(f"{frozen_rel}: {key} resolves to no record")
        elif records[pair].get("date", "") >= RECENT_FROM:
            problems.append(f"{frozen_rel}: {key} is dated {RECENT_FROM} or later, so it "
                            f"is queued as recent and does not belong on the frozen list")

    # --- every dossier, one at a time (check_dossier) -----------------------
    context = load_context()
    env = check_env(records, reg, context)
    warnings = []
    for path in all_dossiers():
        meta, body = read_dossier(path)
        doc_id = meta.get("mig_key", "")
        if doc_id in seen_ids:
            problems.append(f"{path.relative_to(ROOT)}: duplicate mig_key {doc_id!r}")
        seen_ids.add(doc_id)
        p, w = check_dossier(path, meta, body, env)
        problems.extend(p)
        warnings.extend(w)
    check_mig_registry(problems)

    # --- keys, hashes and provenance on every file row ---------------------
    problems.extend(check_rows())

    # --- the context layer -------------------------------------------------
    for (sid, rid), ctx in sorted(context.items()):
        where = f"0.2/context/{sid}.jsonl {rid}"
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

    # --- the person's decision logs (0.2/review/) --------------------------
    check_review_logs(records, problems, warnings)
    # --- the ledger (0.2/ledger/ledger.csv) ---------------------------------
    check_ledger(records, problems, warnings)
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


def check_ledger(records, problems, warnings):
    """One row per loaded record, matching it; the column lists in step with run.py's;
    each owner's columns in step with what that step would write now. A step whose
    columns lag its inputs (new context rows, new proposals) is a warning: run it."""
    rel = LEDGER.relative_to(ROOT)
    if CONTEXT_FACTS != ledger.CONTEXT_FACTS:
        problems.append("ledger.CONTEXT_FACTS differs from run.CONTEXT_FACTS")
    if ledger.GATE_FIELDS != [f for f in MODEL_FIELDS if f != "uncertainty_reason"]:
        problems.append("ledger.GATE_FIELDS differs from run.MODEL_FIELDS")
    try:
        rows = ledger.read(LEDGER)
    except ledger.LedgerError as e:
        problems.append(str(e))
        return
    if not rows and records:
        problems.append(f"{rel}: missing; run normalise")
        return
    keys = {record_key(*p) for p in records}
    for k in sorted(keys - set(rows), key=natural)[:5]:
        problems.append(f"{rel}: no row for record {k}; run normalise")
    for k in sorted(set(rows) - keys, key=natural)[:5]:
        problems.append(f"{rel}: a row for {k}, which is not a loaded record")
    for (sid, rid), rec in records.items():
        r = rows.get(record_key(sid, rid))
        if r and r["content_hash"] != rec.get("content_hash"):
            warnings.append(f"{rel}: {record_key(sid, rid)} lags its newest record "
                            f"version; run normalise")
            break
    for k, r in rows.items():
        if not r["loaded_on"]:
            problems.append(f"{rel}: {k} has no loaded_on")
            break
    gates = proposal_rows("extract_gate")
    derived = {record_key(*p) for p in gates}
    have = {k for k, r in rows.items() if r["rules_status"]}
    if derived != have:
        warnings.append(f"{rel}: derive columns lag the extract_gate proposals "
                        f"({len(derived - have)} without, {len(have - derived)} stale); "
                        f"run derive")
    else:
        for pair, gate in gates.items():
            v = rules.derive(gate, manual=(pair[0] == MANUAL))
            if v["status"] != rows[record_key(*pair)]["rules_status"]:
                warnings.append(f"{rel}: {record_key(*pair)} status differs from the "
                                f"rules {rules.RULES_VERSION}; run derive")
                break
    read = {record_key(*p) for p in load_context()} & set(rows)
    if read != {k for k, r in rows.items() if r["read_depth"]}:
        warnings.append(f"{rel}: reading columns lag the context rows; run readiness")
    # The incidents: the ledger is the source of their labels and facts, the dossier's
    # frontmatter a copy written by review. A copy that differs was edited by hand.
    canon = decide.canonical_rows(THIS)
    for path in all_dossiers():
        meta, _ = read_dossier(path)
        inc = meta.get("mig_key")
        row = canon.get(inc)
        if row is None:
            problems.append(f"{rel}: no canonical row for incident {inc}; run review")
            continue
        if canonical_pair(meta) and record_key(*canonical_pair(meta)) != row["record_key"]:
            warnings.append(f"{rel}: {inc} is carried by {row['record_key']}, not its "
                            f"canonical record; run review")
        moved = decide.drift(THIS, meta, row)
        if moved:
            problems.append(f"{path.relative_to(ROOT)}: {', '.join(moved)} differ from the "
                            f"ledger. Labels and facts are changed on sheet 2 "
                            f"({decide.INCIDENTS['file']}), not in the dossier; run review "
                            f"to write the dossier from the ledger again")
    for k, r in rows.items():
        if r["canonical"] != "true" and any(r[c] for c in ledger.INCIDENT_COLUMNS):
            problems.append(f"{rel}: {k} holds incident columns but is not a canonical "
                            f"record")
            break
    decide.check_logs(THIS, problems)


def check_env(records=None, reg=None, context=None):
    """What check_dossier needs to know besides the dossier itself."""
    return {
        "instances": {r["instance_id"] for r in read_csv(TAXONOMY / "instances.csv")},
        "risks": {r["risk_id"] for r in read_csv(TAXONOMY / "risks.csv")},
        "reg": registry() if reg is None else reg,
        "records": latest_records() if records is None else records,
        "context": load_context() if context is None else context,
    }


def check_dossier(path, meta, body, env):
    """The rules one dossier must meet on its own (`stage_check` adds the rules that
    span dossiers). Returns (problems, warnings). Sheet 3 runs it on an edited dossier
    before writing it."""
    problems, warnings = [], []
    rel = path.relative_to(ROOT)
    taxonomy_instances, risks = env["instances"], env["risks"]
    reg, records, context = env["reg"], env["records"], env["context"]

    for key in REQUIRED_KEYS:
        if key not in meta:
            problems.append(f"{rel}: missing frontmatter key {key!r}")

    doc_id = meta.get("mig_key", "")
    if doc_id != path.stem:
        problems.append(f"{rel}: mig_key {doc_id!r} does not match the filename")
    if not re.fullmatch(MIG_PATTERN, doc_id or ""):
        problems.append(f"{rel}: mig_key {doc_id!r} is not MIG-nnnn")
    if "id" in meta:
        problems.append(f"{rel}: the key `id` is retired; the dossier's key is mig_key")
    pair = canonical_pair(meta)
    if pair and str(meta.get("source_key") if meta.get("source_key") is not None else "") \
            != source_key(*pair):
        problems.append(f"{rel}: source_key {meta.get('source_key')!r} is not the canonical "
                        f"record's key {source_key(*pair)!r}")

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

    # Until 0.2, the fields a person set on sheet 3. No longer written; validated where
    # an old dossier still has it.
    by_person = meta.get(SET_BY_PERSON, [])
    if not isinstance(by_person, list):
        problems.append(f"{rel}: {SET_BY_PERSON} must be a list of field names")
    else:
        for name in by_person:
            if name not in PERSON_SETTABLE:
                problems.append(f"{rel}: {SET_BY_PERSON} names {name!r}, which is not a "
                                f"field a person sets ({', '.join(PERSON_SETTABLE)})")
        if len(set(by_person)) != len(by_person):
            problems.append(f"{rel}: {SET_BY_PERSON} names a field twice")

    for key in meta:
        if re.fullmatch(r"e[1-5](_.*)?", str(key)):
            problems.append(f"{rel}: {key!r} is an evidence score; "
                            f"scoring is parked and no score belongs in a dossier")

    for name in SECTIONS:
        if not re.search(rf"^## {re.escape(name)}\s*$", body, re.M):
            problems.append(f"{rel}: missing section '## {name}'")

    # A verdict needs a reading behind it. A dossier that asserts scope either way
    # must rest on a source read for the gate facts.
    if meta.get("multi_agent") in (True, False):
        ctxs = [context.get((s.get("source_id"), str(s.get("record_id"))))
                for s in meta.get("sources") or []]
        levels = [readiness(c, flagged=True)["scope"] for c in ctxs]
        best = min((READY_LEVELS.index(v["level"]) for v in levels), default=2)
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
    return problems, warnings


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
    for path, required in ((STATE / "readiness.jsonl", True),
                           (STATE / INSTANCES_DUE, True)):
        for n, row in enumerate(read_jsonl(path), 1):
            key_ok(f"{path.relative_to(ROOT)}:{n}", row, required)
    for folder in (CONTEXT, PROPOSALS):
        for path in sorted(folder.glob("*.jsonl")) if folder.exists() else []:
            for n, row in enumerate(read_jsonl(path), 1):
                key_ok(f"{path.relative_to(ROOT)}:{n}", row, required=False)
    return problems


# ---------------------------------------------------------------------- viz

PAGES = ("pipeline_flow.html",)


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
    """Render the dataflow map, the pipeline flowchart."""
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


# ------------------------------------------------------------------- report
#
# The published report: a single page for readers, built from what the last `index`
# wrote. A step of its own, never run by `update`, `viz` or `serve`: a report is
# built when someone decides the index is worth reporting.

REPORT_PARTS = Path(__file__).resolve().parent / "report"
REPORT_PAGE = "index_report.html"


def report_data():
    """The report's data: the index rows, each dossier's canonical link, the taxonomy,
    the registry, and the dates and version the page shows."""
    state_path = STATE / "pipeline.json"
    if not LEDGER.exists() or not state_path.exists():
        die("report: no index yet; run `python 0.2/pipeline/run.py index` first")
    rows = ledger.read(LEDGER)
    sources = {}
    for r in rows.values():
        if r["incident_key"]:
            sources.setdefault(r["incident_key"], set()).add(r["source_id"])
    eff = decide.effective
    # Incidents in the index only: their scope is in. Out and unclear stay in the ledger,
    # flagged by their stage. A label not yet decided shows its proposal, the same way.
    inc = [dict(k=r["incident_key"], t=r["incident_title"], d=r["occurrence_date"],
                e=eff(r, "evidence_type"),
                fm="" if eff(r, "failure_mode") in ("", "none") else eff(r, "failure_mode"),
                i=[] if eff(r, "instances") in ("", "none") else ledger.as_list(eff(r, "instances")),
                v=r["verification"], c=r["source_id"],
                s=sorted(sources[r["incident_key"]]), u=r["url"])
           for r in sorted(rows.values(),
                           key=lambda r: (str(r["occurrence_date"]), r["incident_key"]))
           if r["canonical"] == "true" and r["in_index"] == "true"]
    risks = [dict(id=r["risk_id"], n=r["risk"], k=r["risk_type"], d=r["definition"])
             for r in read_csv(TAXONOMY / "risks.csv")]
    inst = [dict(id=r["instance_id"], n=r["instance"], r=r["risk_id"], p=r["provenance"],
                 d=r["definition"]) for r in read_csv(TAXONOMY / "instances.csv")]
    src = {r["source_id"]: dict(n=r["name"], u=r["url"]) for r in read_csv(REGISTRY)}
    state = json.loads(state_path.read_text(encoding="utf-8"))
    aiid_raw = RAW / "aiid"
    return dict(inc=inc, risks=risks, inst=inst, src=src,
                version=(REPORT_PARTS / "VERSION").read_text(encoding="utf-8").strip(),
                asof=str(state.get("generated_at", ""))[:10],
                refreshed=aiid_fetched_at(aiid_raw) if (aiid_raw / "FETCHED.md").exists() else "")


def stage_report():
    """Assemble 0.2/out/index_report.html from 0.2/pipeline/report/."""
    parts = {n: (REPORT_PARTS / n).read_text(encoding="utf-8")
             for n in ("head.html", "body.html", "app.js")}
    data = json.dumps(report_data(), ensure_ascii=False, separators=(",", ":"))
    # a "</" inside the data would end the script element early
    data = data.replace("</", "<\\/")
    html = (parts["head.html"] + parts["body.html"] + "<script>\nconst D = " + data + ";\n"
            + parts["app.js"] + "</script>\n")
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / REPORT_PAGE
    target.write_text(html, encoding="utf-8")
    info(f"  ok    report: {target.relative_to(ROOT)}")
    return target


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
    ("review", "Review", ["scope", "review", "dossiers"]),
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
        REVIEW_DECIDED.update(scope=0, promote=0, edit=0)
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
        by_basis = basis_counts(rows)
        by_flag = flag_counts(rows)
        self.count(step, "Candidates", len(rows))
        for basis, label in ((BASIS_RECENT, "Recent AIID records"),
                             (BASIS_FROZEN, "On the frozen pre-2024 list"),
                             (BASIS_MANUAL, "Added by hand")):
            if basis in by_basis:
                self.count(step, label, by_basis[basis])
        for flag, label in (("label", "Flagged: tagged by someone else"),
                            ("keyword", "Flagged: matched a keyword")):
            if flag in by_flag:
                self.count(step, label, by_flag[flag])

    def step_read(self, step, override):
        queue = read_queue()
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
                f"0.2/context/. One run of this command also does the judging, so "
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
        queue = read_queue()
        context = load_context()
        out = []
        for row in queue:
            key = row_pair(row)
            verdict = readiness(context.get(key), flagged=is_flagged(row.get("flags")))
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
        # reads the filled sheets, logs the decisions, makes the dossiers a person said
        # yes to, and writes both sheets again
        res = stage_review()
        attested = dossier_source_refs()
        on_sheets = set(decide.records_state(THIS))
        context = load_context()
        manual = sorted(k for k, c in context.items()
                        if c.get("manual") is True and k not in attested
                        and record_key(*k) not in on_sheets)
        due = stage_instances_due()
        sheets = res["openpyxl"]
        scope_left = res["records"]["asked"] if sheets else 0
        promote_left = 0
        self.count(step, "Decided on sheet 1 this run", REVIEW_DECIDED["scope"])
        self.count(step, "Records on sheet 1", res["records"]["left"])
        self.count(step, "Of those, asking for your judgement", res["records"]["asked"])
        self.count(step, "Decided on sheet 2 this run", REVIEW_DECIDED["edit"])
        self.count(step, "Incidents with labels to decide", res["incidents"]["left"])
        self.count(step, "Hand-added incidents without a dossier", len(manual))
        self.count(step, "Put in scope by a person, no risk-instance proposal", len(due))
        info(f"  ok    review: {res['records']['asked']} record(s) ask for a decision, "
             f"{res['incidents']['left']} incident(s) have labels to decide, {len(manual)} "
             f"hand-added incident(s) without a dossier; {len(due)} record(s) a person put "
             f"in scope have no risk-instance proposal")
        for sid, rid in manual:
            info(f"  todo  python 0.2/pipeline/run.py promote "
                 f"{mig_key_of((sid, rid)) or record_key(sid, rid)}")
        for r in due[:50]:
            info(f"  todo  assign instances to {r['record_key']} (/classify-incidents, "
                 f"call 2)")
        if (scope_left or promote_left or manual or due) and override != "recheck":
            parts = []
            if scope_left:
                parts.append(f"{scope_left} record(s) wait for a decision: fill "
                             f"scope_decision (ok, in, out, unclear) and, for in, "
                             f"duplicate_of_decision (ok, new, or a MIG key) in 0.2/review/"
                             f"{decide.RECORDS['file']}")
            if manual:
                parts.append(f"{len(manual)} hand-added incident(s) have no dossier: "
                             f"`python 0.2/pipeline/run.py promote <mig_key>` makes it")
            text = ("; ".join(parts) + ". ") if parts else ""
            if scope_left or promote_left:
                text += ("Save the sheets, then press Continue (on a command-line run, "
                         "run `python 0.2/pipeline/run.py review`, or this update again): "
                         "the filled sheets are read and fresh ones written. ")
            if due:
                text += (f"{len(due)} record(s) a person put in scope have no "
                         f"risk-instance proposal "
                         f"(`python 0.2/pipeline/run.py instances-due` lists them): run "
                         f"/classify-incidents, which assigns their instances. ")
            command = ("python 0.2/pipeline/run.py review" if scope_left or promote_left
                       else "/classify-incidents" if due else "")
            raise StepOutcome("waiting", text.strip(), command=command,
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
                   help="the record's MIG key, e.g. MIG-0058, as the review sheets show "
                        "it; or its internal record_key, <source_id>:<record_id>")
    p.add_argument("--force", action="store_true",
                   help="scaffold even if the record is not ready to classify")

    sub.add_parser("readiness")
    sub.add_parser("derive", help="derive the labels from the extract_gate proposals, "
                                  "by rule, into ledger/ledger.csv")
    dd = sub.add_parser("dedupe", help="propose, for each record not yet in an incident, "
                                       "the existing incident it duplicates, or new")
    dd.add_argument("--measure", action="store_true",
                    help="report how the rules do on the incidents the curator merged")
    sub.add_parser("instances-due", help="list the records a person put in scope "
                                         "that have no risk-instance proposal")
    sub.add_parser("review", help="read the filled review sheets in 0.2/review/, log the "
                                  "decisions, make the dossiers a person said yes to, and "
                                  "write both sheets again")

    sub.add_parser("index")
    sub.add_parser("viz")
    sub.add_parser("report", help="build the published report from the last index; "
                                  "not part of update")
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
    elif args.cmd == "dedupe":
        stage_dedupe(measure=args.measure)
    elif args.cmd == "derive":
        # a fresh verdicts file gives fresh sheets. This is the whole review step, not
        # only the writing: a sheet a person has filled in is read before it is replaced.
        stage_derive()
        stage_review()
    elif args.cmd == "review":
        stage_review()
    elif args.cmd == "instances-due":
        stage_instances_due()
    elif args.cmd == "index":
        stage_index()
    elif args.cmd == "viz":
        stage_viz()
    elif args.cmd == "report":
        stage_report()
    elif args.cmd == "check":
        sys.exit(stage_check())


if __name__ == "__main__":
    main()
