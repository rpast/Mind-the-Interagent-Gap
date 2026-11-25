# fetch_aiid.py

Pulls a whole collection out of the [AI Incident Database](https://incidentdatabase.ai)
GraphQL API (`https://incidentdatabase.ai/api/graphql`) and writes it to
`resources/aiid/`. Standard library only; no install step.

This is a **source fetch**, not a data edit. It writes to `resources/`, never to
`data/`. Screening AIID rows against the inclusion test in `docs/methodology.md`
and adding the survivors to `data/incidents.csv` stays a manual step.

## Token

The script reads `~/.config/aiid/token` by default. Create it once:

```bash
mkdir -p ~/.config/aiid && chmod 700 ~/.config/aiid
printf '%s' 'aiid_YOURTOKEN' > ~/.config/aiid/token
chmod 600 ~/.config/aiid/token
```

`printf` rather than `echo` so no trailing newline is stored, though the script
strips whitespace either way. It warns if the file is group- or world-readable.

Resolution order: `--token-file PATH` → `~/.config/aiid/token` → `$AIID_API_TOKEN`
→ an interactive prompt. The token is never passed on the command line, so it
does not land in shell history or in `ps` output.

Every run prints `token source: ...` to stderr, so you can always see which of
the four it used.

### If it prompts anyway

The prompt means the default file was not found at the path the script expanded.
Check what it is actually looking at — this makes no API call:

```bash
python3 build/fetch_aiid.py --check-token
ls -l ~/.config/aiid/
```

Usual causes:

- the token went to `~/.config/aiid` as a *file* instead of into
  `~/.config/aiid/token`, or the shell created `token` as a directory;
- the file was written under `sudo`, so `$HOME` was root's;
- a stray extension, e.g. `token.txt`.

`--check-token` prints the resolved absolute path (symlinks included) and the
reason the default was skipped. Other flags such as `--max-records` have no
bearing on token resolution; it happens before anything else.

## Use

```bash
# 1. See what fields the schema actually has (one cheap call)
python3 build/fetch_aiid.py --list-fields

# 2. Smoke test on 20 records
python3 build/fetch_aiid.py --max-records 20

# 3. The full incidents table
python3 build/fetch_aiid.py

# The reports table, same way
python3 build/fetch_aiid.py --collection reports
```

Run step 1 before any bulk fetch. AIID renames fields from time to time, and
`--list-fields` is how you find out before a long download.

## Output

| File | Contents |
|---|---|
| `resources/aiid/<collection>.jsonl` | one raw JSON record per line, lossless |
| `resources/aiid/<collection>.csv` | flattened: scalar lists joined with `; `, nested objects as JSON strings |

Expanded objects stay structured in the JSONL and become JSON text in the CSV
column of the same name, so `jq` is the better tool for anything nested:

```bash
jq -r '[.incident_id, .title, ([.AllegedDeployerOfAISystem[].name] | join("; "))] | @tsv' \
  resources/aiid/incidents.jsonl
```

Treat the JSONL as the archive and the CSV as the thing you read. Both are
overwritten on each run, so note the fetch date when you cite a row.

## What the two AIID files contain

`run.py fetch aiid` writes two files to `0.2/raw/aiid/`. Counts are from the snapshot
fetched on 2026-11-15.

**`incidents.jsonl`** has one row per incident: 1,817 rows. Each row has the incident's
`incident_id`, the number AIID shows, and `_id`, AIID's internal id. It is fetched at
depth 0, so it carries no classifications.

**`classifications.jsonl`** has one row per taxonomy annotation, not one per incident:
2,623 rows. By namespace:

| namespace | rows |
|---|---|
| `MIT` | 1,498 |
| `GMF` | 326 |
| `CSETv1` | 214 |
| `CSETv1_Annotator-1` | 298 |
| `CSETv1_Annotator-2` | 106 |
| `CSETv1_Annotator-3` | 81 |
| `CSETv0` | 100 |

An incident can have several classifications, one per namespace or annotator.

A classification row carries no `incident_id`. It links to its incident through its
`incidents` list, which holds the incident's `_id`. So the join is on `_id`, and that is
what `run.py normalise` does.

The multi-agent field is the attribute whose `short_name` is `Multiple AI Interaction`,
in the classification's `attributes` list. Its `value_json` is `yes`, `no` or `maybe`.
It exists only in the CSETv1 namespaces: `CSETv1` and the three `CSETv1_Annotator-*`.

313 incidents carry a value for it. None of them is dated 2025 or later. 319 incidents
have no classification at all, in any namespace.

A record built from these files keeps a pointer back to them: `raw_ref` names
`0.2/raw/aiid/incidents.jsonl`, the id field `_id`, its value and the fetch date.

## How the field selection works

There is no literal `SELECT *` in GraphQL, so the script builds one. It
introspects the schema, finds the root query field named by `--collection`,
resolves its return type, and selects every scalar and enum field on it.
Nothing is hardcoded, so a renamed field shows up in the output rather than
breaking the query.

Linked objects — `reports`, `classifications`, `AllegedDeployerOfAISystem` and
the rest — need a subselection of their own, so the builder **recurses into
them** and expands their scalars too. `--depth` controls how far:

| `--depth` | What you get |
|---|---|
| `0` | scalars only (`incident_id`, `title`, `description`, …) |
| `1` | **default** — scalars, plus every linked object expanded to its own scalars |
| `2` | also expands the objects hanging off those objects (e.g. `reports.embedding`) |

Three kinds of field are dropped, and each run names them on stderr so nothing
disappears quietly:

- **needs arguments** — e.g. `translations(language: String!)`. There is no
  sensible default, so it is skipped. Fetch it with a hand-written query if
  you need it.
- **beyond `--depth`** — raise `--depth` to pull it in.
- **cyclic** — `incidents → reports → incidents` would recurse forever, so the
  second visit to a type on the current path is cut.

Check what you are about to request before a long download:

```bash
python3 build/fetch_aiid.py --list-fields --depth 2   # the tree, with markers
python3 build/fetch_aiid.py --print-query --depth 2   # the exact GraphQL, no fetch
```

### The 6 MB response cap

The API is served by a Lambda that refuses any response over 6 MB:

```
HTTP 502: {"errorType":"Function.ResponseSizeTooLarge", ...}
```

With `--depth 1` on `incidents`, 100 records per page blows straight through
that, because each incident drags its full `reports` array along. The script
handles it: on that error it **halves the page size and retries the same
offset**, repeatedly if needed, then creeps back up after ten clean pages so one
oversized incident does not pin the whole run at a tiny page size. You will see

```
  response too large at offset 0; page size -> 50
  response too large at offset 0; page size -> 25
  fetched 100 incidents
```

and the run completes. No records are skipped or duplicated — the offset is
derived from the rows already held, not from a fixed counter.

Two things to know:

- `--limit` is the **ceiling**, not a fixed size. The run never pages larger
  than it; it only shrinks below it and recovers back towards it.
- If a *single* record is over the cap, the script stops and says so rather
  than looping. Narrow the selection as below.

Letting it shrink costs extra round trips, so for a full fetch it is faster to
cut the payload up front.

### Keeping it to a sane size

At `--depth 1` every incident carries its full `reports` array and its
`embedding` vector, which dominates the output. Drop them by field name or by
dotted path:

```bash
# everything except the embedding vectors and the t-SNE coordinates
python3 build/fetch_aiid.py --depth 1 --exclude embedding,tsne

# incidents with their entities and classifications, but not full report bodies
python3 build/fetch_aiid.py --depth 1 --exclude reports,embedding,tsne

# depth 2, but without the embedding nested under each report
python3 build/fetch_aiid.py --depth 2 --exclude reports.embedding,embedding,tsne
```

`--fields` still works as a top-level whitelist, and composes with `--depth`.

Reports can also be pulled as their own collection and joined on
`incident_id`, which avoids duplicating a report shared by several incidents:

```bash
python3 build/fetch_aiid.py --collection reports --depth 1
```

## Options

| Flag | Default | Purpose |
|---|---|---|
| `--collection` | `incidents` | root query field to fetch |
| `--token-file` | `~/.config/aiid/token` | where the token lives |
| `--out-dir` | `resources/aiid` | output directory |
| `--limit` | `100` | page size |
| `--max-records` | all | stop after N records, for a trial run |
| `--depth` | `1` | how many levels of linked objects to expand |
| `--exclude` | – | comma-separated fields to drop, by name or dotted path |
| `--fields` | all | comma-separated whitelist of top-level fields |
| `--print-query` | – | print the generated GraphQL and exit; no API call |
| `--sort-field` | `incident_id` | sort key; pass `''` to disable |
| `--list-fields` | – | print the schema and exit |
| `--check-token` | – | report where the token resolves from and exit; no API call |
| `--endpoint` | AIID production | override the API URL |

## Behaviour and failure modes

- **Pagination** uses `pagination: {limit, skip}` and stops on a short page.
  Results are sorted by `incident_id` so paging is stable; if the server rejects
  the `sort` argument the script says so and retries unsorted.
- **Responses over the server's 6 MB cap** halve the page size and retry the
  same offset; see above.
- **401 / 403** exits at once with the response body. Rotate or re-copy the token.
- **A token file that is a directory, empty, or unreadable** fails loudly rather
  than falling through to the prompt.
- **Network errors and 5xx** retry three times with exponential backoff.
- **GraphQL `errors`** abort the run rather than write a half-complete table.
- Progress goes to stderr, so `2>/dev/null` leaves you with just the summary.

## Exploring before you fetch

`notebooks/explore_aiid.ipynb` imports this script as a library (`fa.Client`,
`fa.Schema`, `fa.SelectionBuilder`, `fa.fetch_all`), so what you try in the
notebook is exactly what the CLI will do. It walks the schema, measures bytes
per record to pick a page size, samples a few hundred incidents into a
DataFrame, checks which fields are actually populated, runs a keyword prefilter
for multi-agent candidates, and prints the equivalent CLI command at the end.

Run the long download from the shell, not from a kernel.

```bash
pip install jupyterlab   # only IPython + ipykernel are installed; VS Code works as-is
jupyter lab notebooks/explore_aiid.ipynb
```

## Licence

AIID content is CC-BY-SA 4.0. Attribute it if a fetched row ends up in
`data/incidents.csv` or in the dashboard, and record the source in
`data/sources.csv`.

## Status

Written 2026-11-07. **Run against the live API on 2026-11-09**, which returned
1,803 incidents and 2,623 classifications; see `../raw/aiid/FETCHED.md` for the
snapshot and the exact commands. The schema assumptions held.

Moved from `build/` to `0.2/pipeline/` on 2026-11-12 when this tree was started. The
script is unchanged: `0.2/pipeline/run.py` imports it as a library (`Client`,
`Schema`, `SelectionBuilder`, `fetch_all`, `resolve_token`) rather than wrapping
or editing it. It has no incremental fetch — both outputs are overwritten every
run — so the per-record fetch date and change detection live in the record store
around it, not here. The change detection ignores fetch dates: a re-fetch that changes
nothing of substance adds no record version (`0.2/docs/input_layer.md` § Idempotency).
