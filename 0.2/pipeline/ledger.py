"""The ledger: one row per record the pipeline has loaded, one column per value a step
produced for it. 0.2/ledger/ledger.csv. See 0.2/docs/plan.md, section 3.

The ledger is the source of truth for every column it holds. Each column has exactly one
owner, the step that writes it; a step can write only its own columns, and writing them
replaces them on every row (a row the step did not produce gets its columns blanked).
Only the `load` step adds rows. Writes are atomic and one at a time.

Values are short strings: no newlines, lists `;`-separated, booleans `true` / `false`,
missing as empty. Long text (quotes, reasons, readings) stays in the evidence files the
`*_ref` columns name.
"""
from __future__ import annotations

import csv
import fcntl
import os
import re
from contextlib import contextmanager
from pathlib import Path

# The seven facts a reading looks for (run.CONTEXT_FACTS) and the extract_gate answers
# the ledger holds (run.MODEL_FIELDS without uncertainty_reason, which is prose).
# run.py check verifies these match.
CONTEXT_FACTS = ["agents", "interaction", "multiplicity", "setting",
                 "cooperation", "objectives", "mechanism"]
GATE_FIELDS = ["n_ai_agents", "agent_names", "interaction_present", "interaction_kind",
               "setting", "stakes", "environment_controlled_by",
               "single_agent_counterfactual", "multiplicity_role", "cooperation_occurred",
               "cooperation_expected", "objective_relation", "confidence"]

# owner -> its columns, in pipeline order. The file's columns are these, in this order.
OWNERS = {
    "load": ["record_key", "source_id", "source_key", "title", "date", "url",
             "loaded_on", "fetched_at", "content_hash", "external_ma_label"],
    "prefilter": ["queued", "queue_basis", "flags", "keyword_terms", "label_values"],
    "readiness": ["read_depth", "agent_count"]
                 + [f"{f}_status" for f in CONTEXT_FACTS] + ["context_ref"],
    "derive": ["gate_prompt", "gate_run_date"] + GATE_FIELDS + ["gate_ref",
               "rules_version", "is_attack", "presumption_fires", "counterfactual",
               "by_presumption", "gate1", "rules_status", "why_a_person",
               "labels_settled", "rules_multi_agent", "rules_evidence_type",
               "rules_failure_mode", "rules_instances_presumed",
               "scope_proposed", "scope_why"],
}
COLUMNS = [c for cols in OWNERS.values() for c in cols]
OWNER_OF = {c: o for o, cols in OWNERS.items() for c in cols}
KEY = "record_key"


class LedgerError(Exception):
    pass


def cell(value) -> str:
    """A value as ledger text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "; ".join(cell(v) for v in value)
    return str(value).replace("\r\n", " ").replace("\r", " ").replace("\n", " ")


def as_bool(text: str):
    return {"true": True, "false": False}.get(text)


def as_list(text: str) -> list[str]:
    return [p.strip() for p in text.split(";") if p.strip()]


def natural(key: str):
    """Sort key: aiid:99 before aiid:1015 (as run.natural)."""
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", str(key))]


def read(path: Path) -> dict[str, dict[str, str]]:
    """record_key -> row. Every column present, as text."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise LedgerError(f"{path}: missing columns {', '.join(missing)}")
        return {r[KEY]: {c: r.get(c) or "" for c in COLUMNS} for r in reader}


@contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def write(path: Path, owner: str, updates: dict[str, dict], *, keep_absent=False) -> int:
    """Write `owner`'s columns. `updates` is record_key -> {column: value}.

    Every row's owner columns are replaced: from `updates` where the row is named, blank
    where it is not (unless keep_absent, which leaves those rows as they are). Only the
    `load` owner may add rows; any other owner naming an unknown record fails, and so
    does any column the owner does not own. Returns the number of rows written."""
    if owner not in OWNERS:
        raise LedgerError(f"unknown ledger owner {owner!r}")
    own = OWNERS[owner]
    for key, values in updates.items():
        alien = [c for c in values if c not in own]
        if alien:
            raise LedgerError(f"{owner} may not write {', '.join(alien)} ({key})")
    with _locked(path):
        rows = read(path)
        unknown = [k for k in updates if k not in rows]
        if unknown and owner != "load":
            raise LedgerError(f"{owner}: {len(unknown)} record(s) not in the ledger, "
                              f"e.g. {unknown[0]}; run normalise first")
        for key in unknown:
            rows[key] = {c: "" for c in COLUMNS}
        for key, row in rows.items():
            if key in updates:
                values = updates[key]
                for c in own:
                    row[c] = cell(values.get(c, row[c] if keep_absent else ""))
                row[KEY] = key
            elif not keep_absent:
                for c in own:
                    if c != KEY:
                        row[c] = ""
        tmp = path.with_suffix(".csv.tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
            w.writeheader()
            for key in sorted(rows, key=natural):
                w.writerow(rows[key])
        os.replace(tmp, path)
    return len(updates)
