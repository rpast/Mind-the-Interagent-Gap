#!/usr/bin/env python3
"""Fetch a whole collection from the AI Incident Database GraphQL API.

The token is never read from the command line. In order of preference:

    1. --token-file PATH       (overrides everything else)
    2. ~/.config/aiid/token    (the default; chmod 600)
    3. $AIID_API_TOKEN
    4. an interactive prompt (getpass, not echoed)

Usage:
    python3 build/fetch_aiid.py
    python3 build/fetch_aiid.py --collection reports

See build/fetch_aiid.md.

Writes <out-dir>/<collection>.jsonl (raw records) and <collection>.csv (flattened).
Standard library only.
"""

import argparse
import csv
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request

ENDPOINT = "https://incidentdatabase.ai/api/graphql"
DEFAULT_TOKEN_FILE = "~/.config/aiid/token"

INTROSPECT = """
query Introspect {
  __schema {
    queryType { fields { name type { ...TypeRef } } }
    types {
      name
      kind
      fields {
        name
        type { ...TypeRef }
        args { name defaultValue type { ...TypeRef } }
      }
    }
  }
}
fragment TypeRef on __Type {
  kind name
  ofType { kind name
    ofType { kind name
      ofType { kind name
        ofType { kind name } } } }
}
"""


def named_type(t):
    """Unwrap NON_NULL/LIST wrappers down to the named type."""
    while t and t.get("name") is None:
        t = t.get("ofType")
    return t or {}


def is_required(arg):
    return arg["type"].get("kind") == "NON_NULL" and arg.get("defaultValue") is None


class PayloadTooLarge(Exception):
    """The server refused the page because the response exceeded its size cap."""


class GraphQLError(Exception):
    def __init__(self, errors, data=None):
        self.errors = errors
        self.data = data
        super().__init__("; ".join(e.get("message", str(e)) for e in errors))


class Client:
    def __init__(self, token, endpoint=ENDPOINT, timeout=120):
        self.token = token
        self.endpoint = endpoint
        self.timeout = timeout

    def query(self, query, variables=None, retries=3):
        body = json.dumps({"query": query, "variables": variables or {}}).encode()
        req = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "mind-the-interagent-gap/fetch_aiid",
            },
            method="POST",
        )
        last = None
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = json.load(resp)
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:500]
                if exc.code in (401, 403):
                    raise SystemExit(f"Auth rejected ({exc.code}). Check the token.\n{detail}")
                if "ResponseSizeTooLarge" in detail or "payload size exceeded" in detail:
                    raise PayloadTooLarge(detail)
                last = f"HTTP {exc.code}: {detail}"
            except urllib.error.URLError as exc:
                last = f"network error: {exc.reason}"
            time.sleep(2 ** attempt)
        else:
            raise SystemExit(f"Request failed after {retries} attempts. {last}")

        if payload.get("errors"):
            raise GraphQLError(payload["errors"], payload.get("data"))
        return payload["data"]


class Schema:
    def __init__(self, data):
        schema = data["__schema"]
        self.query_fields = {f["name"]: f for f in schema["queryType"]["fields"]}
        self.types = {t["name"]: t for t in schema["types"] if t.get("name")}

    def root_type(self, collection):
        if collection not in self.query_fields:
            options = ", ".join(sorted(n for n in self.query_fields if n.endswith("s")))
            raise SystemExit(f"No root query field '{collection}'. Candidates: {options}")
        name = named_type(self.query_fields[collection]["type"]).get("name")
        if name not in self.types or not self.types[name].get("fields"):
            raise SystemExit(f"Could not introspect fields of type '{name}'.")
        return name

    def split_fields(self, type_name):
        """(scalar names, [(object field name, its type name)]) for one type."""
        scalars, objects = [], []
        for field in self.types[type_name]["fields"]:
            base = named_type(field["type"])
            if base.get("kind") in ("SCALAR", "ENUM"):
                scalars.append(field["name"])
            else:
                objects.append((field["name"], base.get("name")))
        return scalars, objects


class SelectionBuilder:
    """Expand a type into a GraphQL selection set, recursing into linked objects."""

    def __init__(self, schema, depth, exclude):
        self.schema = schema
        self.depth = depth
        self.exclude = set(exclude)
        self.skipped_args = []   # fields needing arguments we cannot supply
        self.truncated = []      # objects dropped at the depth limit
        self.cycles = []         # objects dropped to break a cycle

    def excluded(self, path, name):
        return name in self.exclude or path in self.exclude

    def build(self, type_name, depth=None, path="", stack=()):
        depth = self.depth if depth is None else depth
        parts = []
        for field in self.schema.types[type_name]["fields"]:
            name = field["name"]
            full = f"{path}{name}"
            if self.excluded(full, name):
                continue
            if any(is_required(a) for a in field.get("args") or []):
                self.skipped_args.append(full)
                continue

            base = named_type(field["type"])
            kind, base_name = base.get("kind"), base.get("name")

            if kind in ("SCALAR", "ENUM"):
                parts.append(name)
                continue
            if kind not in ("OBJECT", "INTERFACE") or base_name not in self.schema.types:
                continue
            if depth <= 0:
                self.truncated.append(full)
                continue
            if base_name in stack:
                self.cycles.append(f"{full} ({base_name})")
                continue

            sub = self.build(base_name, depth - 1, f"{full}.", stack + (type_name,))
            parts.append(f"{name} {{ {sub} }}")

        return " ".join(parts) if parts else "__typename"

    def report(self):
        for label, items in (
            ("needs arguments, skipped", self.skipped_args),
            ("beyond --depth, skipped", self.truncated),
            ("cyclic, skipped", self.cycles),
        ):
            if items:
                print(f"  {label}: {', '.join(sorted(set(items)))}", file=sys.stderr)


def page_query(collection, selection, with_sort, sort_field):
    sort_arg = f", sort: {{ {sort_field}: ASC }}" if with_sort else ""
    return f"""
query Page($limit: Int!, $skip: Int!) {{
  {collection}(pagination: {{ limit: $limit, skip: $skip }}{sort_arg}) {{
    {selection}
  }}
}}
"""


def fetch_all(client, collection, selection, limit, sort_field, max_records=None):
    """Page through a collection, shrinking the page size if the server balks at it."""
    with_sort = bool(sort_field)
    ceiling, streak, reported = limit, 0, 0
    rows = []
    while True:
        skip = len(rows)  # the page size can change mid-run, so derive the offset
        q = page_query(collection, selection, with_sort, sort_field)
        try:
            data = client.query(q, {"limit": limit, "skip": skip})
        except PayloadTooLarge:
            if limit <= 1:
                raise SystemExit(
                    f"A single record (offset {skip}) exceeds the server's 6 MB "
                    "response cap.\nNarrow the selection, e.g. "
                    "--exclude reports,embedding,tsne or --depth 0."
                )
            limit, streak = max(1, limit // 2), 0
            print(f"  response too large at offset {skip}; page size -> {limit}",
                  file=sys.stderr)
            continue
        except GraphQLError as exc:
            if with_sort and "sort" in str(exc).lower():
                print(f"  sort unsupported ({exc}); retrying unsorted", file=sys.stderr)
                with_sort = False
                continue
            raise SystemExit(f"GraphQL error: {exc}")

        batch = data.get(collection) or []
        rows.extend(batch)
        done = len(batch) < limit or (max_records and len(rows) >= max_records)
        if done or len(rows) - reported >= 100:
            print(f"  fetched {len(rows)} {collection}", file=sys.stderr)
            reported = len(rows)
        if done:
            break

        # One oversized record should not pin the page size low for the rest of the run.
        streak += 1
        if limit < ceiling and streak >= 10:
            limit, streak = min(ceiling, max(limit + 1, limit * 3 // 2)), 0
            print(f"  page size -> {limit}", file=sys.stderr)

        time.sleep(0.2)
    return rows[:max_records] if max_records else rows


def flatten(value):
    if value is None:
        return ""
    if isinstance(value, list):
        if all(not isinstance(v, (list, dict)) for v in value):
            return "; ".join("" if v is None else str(v) for v in value)
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def write_outputs(rows, out_dir, collection):
    os.makedirs(out_dir, exist_ok=True)
    jsonl = os.path.join(out_dir, f"{collection}.jsonl")
    with open(jsonl, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    columns = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    csv_path = os.path.join(out_dir, f"{collection}.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: flatten(row.get(k)) for k in columns})
    return jsonl, csv_path


def read_token_file(path, required):
    """Read a token from a file. A missing file is fatal only when asked for by name."""
    full = os.path.realpath(os.path.expanduser(path))
    if not os.path.exists(full):
        if required:
            raise SystemExit(f"No such token file: {full}")
        return None, f"{full} does not exist"
    if os.path.isdir(full):
        raise SystemExit(f"{full} is a directory, not a token file.")
    try:
        if os.stat(full).st_mode & 0o077:
            print(f"warning: {full} is readable by others; chmod 600 it", file=sys.stderr)
        with open(full, encoding="utf-8") as fh:
            raw = fh.read()
    except PermissionError:
        raise SystemExit(f"Cannot read {full}: permission denied.")
    token = raw.strip()
    if not token:
        raise SystemExit(f"{full} is empty.")
    return token, full


def resolve_token(token_file):
    """Return (token, where-it-came-from). Prompts only as a last resort."""
    if token_file:
        token, where = read_token_file(token_file, required=True)
        return token, f"--token-file {where}"

    token, where = read_token_file(DEFAULT_TOKEN_FILE, required=False)
    if token:
        return token, where
    reason = where

    env = os.environ.get("AIID_API_TOKEN", "").strip()
    if env:
        return env, "$AIID_API_TOKEN"

    if not sys.stdin.isatty():
        raise SystemExit(
            f"No token ({reason}, $AIID_API_TOKEN unset). "
            f"Put it in {DEFAULT_TOKEN_FILE} or pass --token-file."
        )
    print(f"note: no token file ({reason}) and $AIID_API_TOKEN is unset", file=sys.stderr)
    return getpass.getpass("AIID API token: ").strip(), "interactive prompt"


def print_fields(schema, type_name, depth, indent="  ", stack=()):
    scalars, objects = schema.split_fields(type_name)
    needs_args = {
        f["name"]: [a["name"] for a in f.get("args") or [] if is_required(a)]
        for f in schema.types[type_name]["fields"]
    }
    print(f"{indent}scalars: {', '.join(scalars) or '(none)'}")
    for name, base in objects:
        if needs_args.get(name):
            marker = f"  [needs args: {', '.join(needs_args[name])} - not fetched]"
        elif base in stack:
            marker = "  [cyclic - not fetched]"
        elif depth <= 0:
            marker = "  [beyond --depth]"
        else:
            marker = ""
        print(f"{indent}{name}: {base}{marker}")
        expandable = (
            base in schema.types
            and schema.types[base].get("fields")
            and depth > 0
            and base not in stack
            and not needs_args.get(name)
        )
        if expandable:
            print_fields(schema, base, depth - 1, indent + "    ", stack + (type_name,))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--collection", default="incidents", help="root query field (default: incidents)")
    ap.add_argument("--token-file",
                    help=f"file holding the token (default: {DEFAULT_TOKEN_FILE}, then $AIID_API_TOKEN)")
    ap.add_argument("--out-dir", default="resources/aiid", help="output directory")
    ap.add_argument("--limit", type=int, default=100, help="page size (default 100)")
    ap.add_argument("--max-records", type=int, help="stop after N records (for a trial run)")
    ap.add_argument("--depth", type=int, default=1,
                    help="how many levels of linked objects to expand (default 1; 0 = scalars only)")
    ap.add_argument("--exclude", default="",
                    help="comma-separated fields to drop, by name or dotted path "
                         "(e.g. embedding,tsne,reports.embedding)")
    ap.add_argument("--sort-field", default="incident_id", help="field to sort by; empty string to disable")
    ap.add_argument("--fields", help="comma-separated whitelist of top-level fields")
    ap.add_argument("--list-fields", action="store_true", help="print the discovered schema and exit")
    ap.add_argument("--print-query", action="store_true", help="print the generated query and exit")
    ap.add_argument("--check-token", action="store_true",
                    help="report where the token resolves from and exit; makes no API call")
    ap.add_argument("--endpoint", default=ENDPOINT)
    args = ap.parse_args()

    token, where = resolve_token(args.token_file)
    if args.check_token:
        print(f"token source: {where}")
        print(f"token length: {len(token)} chars")
        return
    print(f"token source: {where}", file=sys.stderr)

    client = Client(token, endpoint=args.endpoint)
    print(f"Introspecting {args.collection}...", file=sys.stderr)
    schema = Schema(client.query(INTROSPECT))
    type_name = schema.root_type(args.collection)

    if args.list_fields:
        print(f"type {type_name}")
        print_fields(schema, type_name, args.depth)
        return

    exclude = [f.strip() for f in args.exclude.split(",") if f.strip()]
    if args.fields:
        wanted = {f.strip() for f in args.fields.split(",") if f.strip()}
        known = {f["name"] for f in schema.types[type_name]["fields"]}
        unknown = wanted - known
        if unknown:
            raise SystemExit(f"Not fields of {type_name}: {', '.join(sorted(unknown))}")
        exclude += [n for n in known if n not in wanted]

    builder = SelectionBuilder(schema, args.depth, exclude)
    selection = builder.build(type_name)
    scalars, objects = schema.split_fields(type_name)
    print(f"  type {type_name}: {len(scalars)} scalars, {len(objects)} linked objects, "
          f"depth {args.depth}", file=sys.stderr)
    builder.report()

    if args.print_query:
        print(page_query(args.collection, selection, bool(args.sort_field), args.sort_field))
        return

    sort_field = args.sort_field if args.sort_field in scalars else ""
    rows = fetch_all(client, args.collection, selection, args.limit, sort_field, args.max_records)
    jsonl, csv_path = write_outputs(rows, args.out_dir, args.collection)
    print(f"\n{len(rows)} records\n  {jsonl}\n  {csv_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
