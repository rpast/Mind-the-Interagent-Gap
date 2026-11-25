"""The two review sheets and their logs (0.2/docs/plan.md, 3.5-3.7).

Sheet 1, 1_records.xlsx: one row per record awaiting a person. Labels `scope` (in, out,
unclear) and, for a record decided in, `duplicate_of` (new, or an existing MIG key).
Sheet 2, 2_incidents.xlsx: one row per incident. Labels `incident_scope`, `failure_mode`,
`instances`, `evidence_type`; then the incident's facts and its verification.

Every label has a proposal, a reason and a decision. In a decision cell a person writes
`ok` (agree with the proposal) or their own value; blank is never agreement. A log row
stores the concrete value agreed to. An `ok` given to a proposal that changed after the
sheet was written is refused.

Two logs, append-only, one row per label decision:
  review/record_decisions_log.csv    mig_key is the record's key
  review/incident_decisions_log.csv  mig_key is the incident's key

The incident columns of the ledger are the source of the incident's labels and facts;
the dossier's frontmatter is written from them (render) after every review run.

Every function takes `rm`, the run.py module instance it works for (the test run has its
own), so this module holds no paths of its own.
"""
from __future__ import annotations

import csv
import os
import re
from pathlib import Path

import ledger

LOG_COLS = ["mig_key", "label", "proposed", "decision", "final", "reason",
            "decided_on", "sheet_generated_on"]
LOGS = {"record": "record_decisions_log.csv", "incident": "incident_decisions_log.csv"}
RECORDS = {"file": "1_records.xlsx", "title": "Decide records"}
INCIDENTS = {"file": "2_incidents.xlsx", "title": "Decide incidents"}
SNAPSHOT = "_snapshot"
SCOPES = ("in", "out", "unclear")
LABELS = ["incident_scope", "failure_mode", "instances", "evidence_type"]
# Facts a person may change on sheet 2, as run.parse_edit knows them (dossier field name).
FACTS = {"incident_title": "title", "occurrence_date": "occurrence_date",
         "actor_count": "actor_count", "interaction_kind": "interaction_kind",
         "systems": "systems", "instances_presumed": "instances_presumed",
         "verification": "verification", "last_verified": "last_verified"}
NOTES = ["reason", "verification_note"]


# --------------------------------------------------------------------- logs

def log_path(rm, kind):
    return rm.REVIEW / LOGS[kind]


def ensure_logs(rm):
    rm.REVIEW.mkdir(parents=True, exist_ok=True)
    for kind in LOGS:
        p = log_path(rm, kind)
        if not p.exists():
            with open(p, "w", newline="", encoding="utf-8") as f:
                csv.writer(f, lineterminator="\n").writerow(LOG_COLS)


def read_log(rm, kind):
    p = log_path(rm, kind)
    return rm.read_csv(p) if p.exists() else []


RECORD_LABELS = {"scope": SCOPES, "duplicate_of": None, "dossier": ("no",)}


def check_logs(rm, problems):
    """Both logs: header, labels, keys, values, dates."""
    _, by_key = rm.mig_index()
    incidents = {p.stem for p in rm.all_dossiers()}
    for kind in LOGS:
        p = log_path(rm, kind)
        if not p.exists():
            continue
        rel = p.relative_to(rm.ROOT)
        with open(p, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), [])
        if header != LOG_COLS:
            problems.append(f"{rel}: the header is {header}, it must be {LOG_COLS}")
            continue
        for n, r in enumerate(rm.read_csv(p), 2):
            where = f"{rel}:{n}"
            if kind == "record":
                if r["mig_key"] not in by_key:
                    problems.append(f"{where}: {r['mig_key']!r} is no record's MIG key")
                if r["label"] not in RECORD_LABELS:
                    problems.append(f"{where}: label {r['label']!r} is not one of "
                                    f"{', '.join(RECORD_LABELS)}")
                elif RECORD_LABELS[r["label"]] and r["final"] not in RECORD_LABELS[r["label"]]:
                    problems.append(f"{where}: {r['label']} {r['final']!r} is not allowed")
                elif r["label"] == "duplicate_of" and r["final"] != "new" \
                        and not re.fullmatch(rm.MIG_PATTERN, r["final"]):
                    problems.append(f"{where}: duplicate_of {r['final']!r} is neither new nor "
                                    f"a MIG key")
            else:
                if r["mig_key"] not in incidents:
                    problems.append(f"{where}: {r['mig_key']!r} is no incident")
                if r["label"] not in LABELS + list(FACTS) + NOTES:
                    problems.append(f"{where}: label {r['label']!r} is not one sheet 2 sets")
            for col in ("decided_on", "sheet_generated_on"):
                if r[col] and not rm.parse_iso(r[col])[0]:
                    problems.append(f"{where}: {col} {r[col]!r} is not an ISO date")


def append_log(rm, kind, rows):
    ensure_logs(rm)
    if not rows:
        return
    with open(log_path(rm, kind), "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_COLS, lineterminator="\n")
        for r in rows:
            w.writerow({c: r.get(c, "") for c in LOG_COLS})


def newest(rows):
    """{(mig_key, label): the newest row}: a later row wins."""
    return {(r["mig_key"], r["label"]): r for r in rows}


def record_decisions(rm):
    """{record_key: {label: newest row}} from the record log, with a hand-added record's
    scope `in` on the curator's word unless the log says otherwise."""
    _, by_key = rm.mig_index()
    out = {}
    for (mig, label), r in newest(read_log(rm, "record")).items():
        pair = by_key.get(mig)
        if pair:
            out.setdefault(rm.record_key(*pair), {})[label] = r
    for sid, rid in rm.latest_records():
        if sid == rm.MANUAL:
            out.setdefault(rm.record_key(sid, rid), {}).setdefault("scope", {
                "mig_key": "", "label": "scope", "proposed": "", "decision": "in",
                "final": "in", "reason": rm.HAND_ADDED_REASON, "decided_on": "",
                "sheet_generated_on": ""})
    return out


def write_decision_columns(rm):
    """The ledger's record decision columns, from the newest row of each label."""
    dec = record_decisions(rm)
    rows = ledger.read(rm.LEDGER)
    updates = {}
    for key, labels in dec.items():
        if key not in rows:
            continue
        u = {}
        for label in ("scope", "duplicate_of", "dossier"):
            r = labels.get(label)
            if r:
                u[f"{label}_decision"] = r["decision"]
                u[f"{label}_final"] = r["final"]
                u[f"{label}_decided_on"] = r["decided_on"]
        updates[key] = u
    ledger.write(rm.LEDGER, "decisions", updates)


# ----------------------------------------------------------------- the turn
#
# Incident values live on the canonical row. Placement (which records make an incident,
# which one is canonical) follows the dossiers' sources, which only promote and merge
# change. Values follow the ledger; only a dossier the ledger has never held is read in.

def effective(row, label):
    return row.get(f"{label}_final") if row.get(f"{label}_decision") else \
        row.get(f"{label}_proposed", "")


def pipeline_proposals(rm, row, inst_prop):
    """The proposals the pipeline makes for an incident from its canonical record."""
    out = {}
    if row.get("rules_status"):
        src = f"rules {row.get('rules_version')} from {row.get('gate_prompt')}"
        out["incident_scope"] = (row.get("scope_proposed", ""), row.get("scope_why", ""))
        out["failure_mode"] = (row.get("rules_failure_mode") or "none", src)
        out["evidence_type"] = (row.get("rules_evidence_type", ""), src)
    if inst_prop:
        ids, why = rm.adoptable_instances(inst_prop)
        out["instances"] = ("; ".join(ids) or "none", f"assign_instances: {why or 'none adoptable'}")
    return out


def pipeline_made(why):
    return not why or why.startswith(("rules ", "assign_instances", "not settled",
                                      "settled by the rules"))


def new_incident(rm, pair, row, inst_prop, rec):
    """The incident columns of a dossier made from one record now."""
    ok, precision = rm.parse_iso(rec.get("date") or "")
    out = {"incident_title": rec.get("title", ""), "occurrence_date": rec.get("date", ""),
           "occurrence_date_precision": precision or "year",
           "actor_count": row.get("n_ai_agents") or "unclear",
           "interaction_kind": row.get("interaction_kind")
           if row.get("interaction_kind") in rm.INTERACTION_KINDS else "unclear",
           "systems": row.get("agent_names", ""),
           "instances_presumed": row.get("rules_instances_presumed", ""),
           "verification": "unverified", "last_verified": ""}
    for label, (p, why) in pipeline_proposals(rm, row, inst_prop).items():
        out[f"{label}_proposed"], out[f"{label}_why"] = p, why
    scope = record_decisions(rm).get(rm.record_key(*pair), {}).get("scope")
    if scope:
        out["incident_scope_decision"] = out["incident_scope_final"] = scope["final"]
    return out


def place_incidents(rm, fresh=None):
    """Write the incident columns: placement from the dossiers, values from the ledger
    (moved with the canonical record), pipeline proposals refreshed. `fresh` gives the
    values of incidents made in this run. Returns the number of incidents."""
    fresh = fresh or {}
    rows = ledger.read(rm.LEDGER)
    index = rm.mig_index()
    inst = rm.proposal_rows("assign_instances")
    held = {r["incident_key"]: {c: r[c] for c in ledger.INCIDENT_COLUMNS}
            for r in rows.values() if r["canonical"] == "true" and r["incident_key"]}
    updates = {}
    for key in rows:
        mig = rm.mig_key_of(rm.split_key(key), index)
        if mig:
            updates[key] = {"mig_key": mig}
    n = 0
    for path in rm.all_dossiers():
        meta, body = rm.read_dossier(path)
        inc = meta.get("mig_key")
        canon = rm.canonical_pair(meta)
        if not canon:
            continue
        for s in meta.get("sources") or []:
            pair = (s.get("source_id"), str(s.get("record_id")))
            key = rm.record_key(*pair)
            updates.setdefault(key, {}).update(
                {"mig_key": rm.mig_key_of(pair, index) or inc, "incident_key": inc,
                 "canonical": pair == canon})
        ck = rm.record_key(*canon)
        if inc in fresh:
            values = fresh[inc]
        elif inc in held:
            values = dict(held[inc])
        else:   # a dossier the ledger never held: read it in, labels as the dossier marks them
            rm.info(f"  note  {inc}: not in the ledger yet; its labels are read from the "
                    f"dossier")
            values = rm.incident_columns(meta, body, rows.get(ck, {}), inst.get(canon))
        for label, (p, why) in pipeline_proposals(rm, rows.get(ck, {}), inst.get(canon)).items():
            if pipeline_made(values.get(f"{label}_why", "")) or not values.get(f"{label}_proposed"):
                values[f"{label}_proposed"], values[f"{label}_why"] = p, why
        updates[ck].update(values)
        n += 1
    ledger.write(rm.LEDGER, "incidents", updates)
    return n


def frontmatter_from(rm, meta, row):
    """A dossier's frontmatter with its labels and facts as the ledger row says."""
    new = dict(meta)
    scope = effective(row, "incident_scope")
    new["multi_agent"] = {"in": True, "out": False}.get(scope, scope or False)
    new["multi_agent_label_source"] = "ours" if row.get("incident_scope_decision") else ""
    fm = effective(row, "failure_mode")
    new["failure_mode"] = None if fm in ("", "none") else fm
    why = row.get("failure_mode_why", "")
    new["failure_mode_source"] = "ours" if row.get("failure_mode_decision") else (
        why if why.startswith("classifier:") else
        f"classifier:{why.split(' from ', 1)[1]}" if why.startswith("rules ") and " from " in why
        and new["failure_mode"] else "")
    inst = effective(row, "instances")
    new["instances"] = [] if inst in ("", "none") else ledger.as_list(inst)
    new["evidence_type"] = effective(row, "evidence_type")
    new["title"] = row.get("incident_title") or meta.get("title", "")
    new["occurrence_date"] = row.get("occurrence_date", "")
    new["occurrence_date_precision"] = row.get("occurrence_date_precision", "")
    ac = row.get("actor_count", "")
    new["actor_count"] = int(ac) if ac.isdigit() else (ac or "unclear")
    new["interaction_kind"] = row.get("interaction_kind", "") or "unclear"
    # A system name may hold a ';' (six PoC dossiers do); while the ledger cell still
    # says what the dossier's list says, the list is kept as it is, not split on it.
    new["systems"] = list(meta.get("systems") or []) \
        if ledger.cell(meta.get("systems") or []) == row.get("systems", "") \
        else ledger.as_list(row.get("systems", ""))
    new["instances_presumed"] = ledger.as_list(row.get("instances_presumed", ""))
    new["verification"] = row.get("verification", "") or "unverified"
    new["last_verified"] = row.get("last_verified", "")
    new.pop(rm.SET_BY_PERSON, None)
    return new


RENDERED = ["title", "occurrence_date", "occurrence_date_precision", "actor_count",
            "interaction_kind", "systems", "evidence_type", "multi_agent",
            "multi_agent_label_source", "failure_mode", "failure_mode_source", "instances",
            "instances_presumed", "verification", "last_verified"]


def norm(v):
    if isinstance(v, list):
        return [str(x) for x in v]
    return "" if v is None else str(v)


def drift(rm, meta, row):
    """The rendered fields where a dossier's frontmatter differs from its ledger row."""
    want = frontmatter_from(rm, meta, row)
    return [f for f in RENDERED if norm(meta.get(f)) != norm(want.get(f))]


def canonical_rows(rm):
    return {r["incident_key"]: r for r in ledger.read(rm.LEDGER).values()
            if r["canonical"] == "true" and r["incident_key"]}


def render(rm):
    """Write every dossier's labels and facts from the ledger, where they differ."""
    rows = canonical_rows(rm)
    n = 0
    for path in rm.all_dossiers():
        meta, body = rm.read_dossier(path)
        row = rows.get(meta.get("mig_key"))
        if row and drift(rm, meta, row):
            rm.write_dossier_body(path, frontmatter_from(rm, meta, row), body)
            n += 1
    return n


# ------------------------------------------------------------------- sheets

def book(rm, title, columns, rows, editable, choices, help_lines, snap_cols, path):
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    wb = rm.openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    ws.append(columns)
    head, ask, ask_head = (PatternFill("solid", start_color=c)
                           for c in ("D9E1F2", "FFF2CC", "FFD966"))
    for i, name in enumerate(columns, 1):
        c = ws.cell(1, i)
        c.font = Font(bold=True)
        c.fill = ask_head if name in editable else head
        c.alignment = Alignment(vertical="top", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = (
            40 if name.endswith(("_why", "_quote", "reason", "_note")) or name == "title"
            else 30 if name.endswith("_reading") else 13)
    for row in rows:
        ws.append([rm.clean(row.get(c, "")) for c in columns])
    if not rows:
        ws.append([rm.NOTHING_LEFT] + [""] * (len(columns) - 1))
    last = max(len(rows) + 1, 2)
    for r in range(2, last + 1):
        for i, name in enumerate(columns, 1):
            c = ws.cell(r, i)
            c.alignment = Alignment(vertical="top", wrap_text=name.endswith(
                ("_why", "_quote", "reason", "_note")) or name == "title")
            if name in editable:
                c.fill = ask
                c.number_format = "@"
            if name == "url" and str(c.value).startswith(("http://", "https://")):
                c.hyperlink = str(c.value)
                c.style = "Hyperlink"
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{last}"
    for col, allowed in choices.items():
        listed = ",".join(allowed)
        dv = DataValidation(type="list", formula1=f'"{listed}"', allow_blank=True,
                            showErrorMessage=False)
        ws.add_data_validation(dv)
        letter = get_column_letter(columns.index(col) + 1)
        dv.add(f"{letter}2:{letter}{last}")
    hs = wb.create_sheet(rm.HELP_SHEET)
    hs.column_dimensions["A"].width = 110
    for i, line in enumerate(help_lines, 1):
        hs.cell(i, 1, line).alignment = Alignment(wrap_text=True, vertical="top")
    hs.cell(1, 1).font = Font(bold=True)
    snap = wb.create_sheet(SNAPSHOT)
    snap.append(["mig_key"] + snap_cols)
    for row in rows:
        snap.append([row["mig_key"]] + [rm.clean(row.get(c, "")) for c in snap_cols])
    snap.sheet_state = "hidden"
    meta = wb.create_sheet(rm.META_SHEET)
    meta.append(["generated_on", rm.TODAY])
    meta.sheet_state = "hidden"
    rm.REVIEW.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    wb.save(tmp)
    os.replace(tmp, path)
    return path


def read_book(rm, cfg, needed):
    """(generated_on, rows, snapshot) of a filled sheet, None when there is none."""
    path = rm.REVIEW / cfg["file"]
    if not path.exists():
        return None
    try:
        wb = rm.openpyxl.load_workbook(path, data_only=True)
        ws, sw = wb[cfg["title"]], wb[SNAPSHOT]
    except Exception as e:  # noqa: BLE001 - a corrupt or half-written file
        raise ValueError(f"{type(e).__name__}: {e}") from None
    head = {str(c.value).strip(): i for i, c in enumerate(ws[1]) if c.value is not None}
    for need in needed:
        if need not in head:
            raise ValueError(f"the column {need!r} is gone from the header row")
    generated = str(wb[rm.META_SHEET].cell(1, 2).value or "") \
        if rm.META_SHEET in wb.sheetnames else ""
    srows = list(sw.iter_rows(values_only=True))
    snapshot = {}
    if srows:
        shead = [str(h) for h in srows[0]]
        for r in srows[1:]:
            if r and r[0]:
                snapshot[str(r[0])] = {h: rm.cell_text(v) for h, v in zip(shead[1:], r[1:])}
    rows = []
    for n, r in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        cells = {name: rm.cell_text(r[i] if i < len(r) else None) for name, i in head.items()}
        if cells.get("mig_key") and cells["mig_key"] != rm.NOTHING_LEFT:
            rows.append({"row": n, "id": cells["mig_key"], "cells": cells})
    return generated, rows, snapshot


# ------------------------------------------------------------- sheet 1: records

RECORDS_LEAD = ["mig_key", "source_id", "source_key", "ask", "title", "date", "url",
                "scope_proposed", "scope_why", "scope_decision",
                "duplicate_of_proposed", "duplicate_of_why", "duplicate_of_decision",
                "reason"]
RECORDS_EDIT = ["scope_decision", "duplicate_of_decision", "reason"]
RECORDS_SNAP = ["scope_proposed", "duplicate_of_proposed"]
RECORDS_HELP = [
    "Decide records: is each record a multi-agent incident, and is it one the index "
    "already holds?",
    "Each label has a proposal (`*_proposed`), the reason for it (`*_why`) and your "
    "decision (`*_decision`, yellow). Write `ok` to agree with the proposal, or your own "
    "value. A blank decision is not agreement: the row comes back next time.",
    "scope_decision: in, out or unclear (or ok). in: two or more AI agents, and the harm "
    "came from them acting on each other. out: one agent, or many doing what one could. "
    "unclear: the source was read and does not say.",
    "duplicate_of_decision, needed for every record you decide in: new (a new incident, "
    "a dossier is made) or the MIG key of the incident it already is (the record joins "
    "that dossier), or ok to take the proposal.",
    "reason is optional; a line is worth writing. It goes into the log.",
    "ask: yes = decide this; check = the rules leave it out, decide only to sample-check "
    "them; duplicate = you decided it in, it still needs duplicate_of.",
    "An ok to a proposal that changed after this sheet was written is refused; the row "
    "comes back with the new proposal.",
    "Right of the yellow columns: everything the pipeline extracted for the record "
    "(the model's answers with quotes, the rules' steps, the reading of the source).",
    "Save the file, then run `python 0.2/pipeline/run.py review` or press Continue on "
    "the page.",
]


def records_state(rm, records=None):
    """The records sheet 1 lists: record_key -> ask (yes, check, duplicate)."""
    rows = ledger.read(rm.LEDGER)
    dec = record_decisions(rm)
    gates = rm.proposal_rows("extract_gate")
    out = {}
    for key, r in rows.items():
        if r["incident_key"]:
            continue
        if not (r["rules_status"] or r["source_id"] == rm.MANUAL):
            continue
        d = dec.get(key, {})
        scope = d.get("scope")
        if scope is None:
            say = r["scope_proposed"]
            conf = (gates.get(rm.split_key(key)) or {}).get("confidence")
            out[key] = "yes" if say == "in" or conf == "low" else "check"
        elif scope["final"] == "in" and "duplicate_of" not in d and "dossier" not in d:
            out[key] = "duplicate"
    return out


def records_rows(rm, state, records):
    evidence = {r["_pair"]: r for r in rm.scope_sheet_rows(
        {**rm.review_state(records), "scope_shown": sorted(state, key=rm.natural)}, records)}
    rows = ledger.read(rm.LEDGER)
    dec = record_decisions(rm)
    out = []
    order = {"yes": 0, "duplicate": 0, "check": 1}
    for key in sorted(state, key=lambda k: (order[state[k]], rm.natural(k))):
        r, pair = rows[key], rm.split_key(key)
        row = dict(evidence.get(pair, {}))
        row.update({**rm.key_fields(pair), "ask": state[key], "title": r["title"],
                    "date": r["date"], "url": r["url"],
                    "scope_proposed": r["scope_proposed"], "scope_why": r["scope_why"],
                    "duplicate_of_proposed": r["duplicate_of_proposed"],
                    "duplicate_of_why": r["duplicate_of_why"]})
        if state[key] == "duplicate":
            row["scope_decision"] = dec[key]["scope"]["final"]
        out.append(row)
    return out


def records_columns(rm):
    tail = [c for c in rm.SCOPE_COLUMNS if c not in RECORDS_LEAD
            and c not in ("rules_say", "decision", "ask")]
    return RECORDS_LEAD + tail


def write_records_sheet(rm, records):
    state = records_state(rm, records)
    rows = records_rows(rm, state, records)
    book(rm, RECORDS["title"], records_columns(rm), rows, RECORDS_EDIT,
         {"scope_decision": ["ok", *SCOPES]}, RECORDS_HELP, RECORDS_SNAP,
         rm.REVIEW / RECORDS["file"])
    return state


def resolve(cell, proposed_now, proposed_then, allowed=None):
    """A decision cell -> (final, decision as logged). Raises ValueError."""
    text = cell.strip()
    if text.lower() == "ok":
        if proposed_now != proposed_then:
            raise ValueError(f"ok given to {proposed_then!r}, but the proposal is now "
                             f"{proposed_now!r}")
        if not proposed_now:
            raise ValueError("ok, but nothing is proposed")
        return proposed_now, "ok"
    if allowed is not None and text.lower() not in allowed:
        raise ValueError(f"{text!r} is not ok or one of {', '.join(allowed)}")
    return (text.lower() if allowed is not None else text), text


def read_records_sheet(rm, records):
    """Read sheet 1: log the decisions, make the dossiers of `in` + `new`, join the
    records decided duplicates to their incident. Returns (decided, fresh incidents)."""
    got = read_book(rm, RECORDS, ["mig_key"] + RECORDS_EDIT)
    if got is None:
        return 0, {}
    generated, rows, snapshot = got
    state = records_state(rm, records)
    ledger_rows = ledger.read(rm.LEDGER)
    _, by_key = rm.mig_index()
    incidents = {p.stem for p in rm.all_dossiers()}
    logged, fresh, seen = [], {}, set()
    context = rm.load_context()
    made = []
    for r in rows:
        c, mig = r["cells"], r["id"]
        if not (c.get("scope_decision") or c.get("duplicate_of_decision")):
            continue
        where = f"{RECORDS['file']} row {r['row']} {mig}"
        pair = by_key.get(mig)
        key = rm.record_key(*pair) if pair else ""
        snap = snapshot.get(mig)
        if not pair or key not in state or snap is None or key in seen:
            rm.info(f"  warn  {where}: not a record this sheet asks about now (decided, "
                    f"in a dossier, or on the sheet twice); not read")
            continue
        seen.add(key)
        lr = ledger_rows[key]
        try:
            if state[key] == "duplicate":
                scope, scope_dec = "in", None
            else:
                scope, scope_dec = resolve(c.get("scope_decision", ""), lr["scope_proposed"],
                                           snap.get("scope_proposed", ""), SCOPES)
            dup = dup_dec = None
            if scope == "in":
                if not c.get("duplicate_of_decision"):
                    raise ValueError("decided in, but duplicate_of_decision is blank: write "
                                     "new, an existing MIG key, or ok")
                dup, dup_dec = resolve(c["duplicate_of_decision"], lr["duplicate_of_proposed"],
                                       snap.get("duplicate_of_proposed", ""))
                dup = dup.upper() if dup.upper().startswith("MIG-") else dup.lower()
                if dup != "new" and dup not in incidents:
                    raise ValueError(f"duplicate_of {dup!r} is neither new nor an incident")
        except ValueError as e:
            rm.info(f"  warn  {where}: {e}. Not logged; the record comes back.")
            continue
        base = {"mig_key": mig, "reason": c.get("reason", ""), "decided_on": rm.TODAY,
                "sheet_generated_on": generated}
        new_rows = []
        if scope_dec is not None:
            new_rows.append({**base, "label": "scope", "proposed": lr["scope_proposed"],
                             "decision": scope_dec, "final": scope})
        if dup is not None:
            new_rows.append({**base, "label": "duplicate_of",
                             "proposed": lr["duplicate_of_proposed"], "decision": dup_dec,
                             "final": dup})
        # act before logging: a refused promote leaves the record on the sheet
        if dup == "new":
            append_log(rm, "record", [x for x in new_rows if x["label"] == "scope"])
            try:
                doc_id = rm.promote_one(key, records, context, made)
            except rm.PromoteRefused as e:
                rm.info(f"  warn  {where}: no dossier made: {e} Its duplicate_of is not "
                        f"logged; it comes back.")
                logged += [x for x in new_rows if x["label"] == "scope"]
                continue
            if doc_id:
                made.append(doc_id)
                dpath = rm.dossier_path(doc_id)
                dmeta, dbody = rm.read_dossier(dpath)
                said = record_decisions(rm).get(key, {}).get("scope", {})
                why = (c.get("reason") or said.get("reason") or "").strip()
                dmeta["multi_agent_basis"] = (
                    f"Scope decided `in` by a person on sheet 1 on "
                    f"{said.get('decided_on') or rm.TODAY}"
                    + (f": {why}" if why else "; no reason given") + ".")
                rm.write_dossier_body(dpath, dmeta, dbody)
                fresh[doc_id] = new_incident(rm, pair, lr,
                                             rm.proposal_rows("assign_instances").get(pair),
                                             records.get(pair, {}))
            append_log(rm, "record", [x for x in new_rows if x["label"] == "duplicate_of"])
        else:
            if dup:
                join_incident(rm, dup, pair, records.get(pair, {}))
            append_log(rm, "record", new_rows)
        logged += new_rows
        rm.info(f"  ok    {mig}: " + ", ".join(f"{x['label']} {x['final']}" for x in new_rows))
    return len(logged), fresh


def join_incident(rm, inc, pair, rec):
    """Add a record to an incident's dossier as a further source."""
    path = rm.dossier_path(inc)
    meta, body = rm.read_dossier(path)
    meta["sources"] = list(meta.get("sources") or []) + [
        {"source_id": pair[0], "record_id": pair[1], "url": rec.get("url", ""),
         "first_seen": rm.TODAY}]
    body = rm.add_to_section(body, "Sources", f"- {pair[0]}: {rec.get('url', '')}") or body
    rm.write_dossier_body(path, meta, body)
    rm.info(f"  ok    {rm.record_key(*pair)} joins {inc} as a further source")


# ----------------------------------------------------------- sheet 2: incidents

INCIDENT_HELP = [
    "Decide incidents: confirm or correct each incident's labels and facts.",
    "For each label - incident_scope, failure_mode, instances, evidence_type - the "
    "proposal, its reason, and your decision (yellow). Write `ok` to agree with the "
    "proposal, or your own value. A decision you made before shows as its value; change "
    "it to change the label. A blank decision is not agreement.",
    "incident_scope: in, out or unclear. failure_mode: FM1, FM2, FM3, or none. "
    "instances: ids separated by ';' (0.2/taxonomy/instances.csv), or none. "
    "evidence_type: real_world, synthetic, lab, theoretical.",
    "The facts (title, date, actor_count, interaction_kind, systems, instances_presumed, "
    "verification, last_verified) show their current value: change a cell to change it.",
    "reason goes into the incident's scope basis; verification_note is added to "
    "## Verification notes with the date. Raising verification sets last_verified to "
    "today unless you set it.",
    "ask lists the labels with no decision yet.",
    "A row that would break a dossier rule (run.py check) is not written. An ok to a "
    "proposal that changed after the sheet was written is refused. An edit to a value "
    "that changed after the sheet was written is refused.",
    "Save the file, then run `python 0.2/pipeline/run.py review` or press Continue on "
    "the page.",
]


def sheet2_columns():
    cols = ["mig_key", "title", "url", "ask"]
    for label in LABELS:
        cols += [f"{label}_proposed", f"{label}_why", f"{label}_decision"]
    return cols + list(FACTS) + NOTES


def incident_rows(rm):
    out = []
    srcs = {}
    for p in rm.all_dossiers():
        m, _ = rm.read_dossier(p)
        srcs[m.get("mig_key")] = (m.get("sources") or [{}])[0].get("url", "")
    for inc, r in sorted(canonical_rows(rm).items()):
        row = {"mig_key": inc, "title": r["incident_title"], "url": srcs.get(inc, ""),
               "ask": "; ".join(l for l in LABELS if not r[f"{l}_decision"])}
        for label in LABELS:
            row[f"{label}_proposed"] = r[f"{label}_proposed"]
            row[f"{label}_why"] = r[f"{label}_why"]
            row[f"{label}_decision"] = r[f"{label}_final"] if r[f"{label}_decision"] else ""
        for col in FACTS:
            row[col] = r[col]
        out.append(row)
    return out


def write_incidents_sheet(rm):
    rows = incident_rows(rm)
    fms = [r["risk_id"] for r in rm.read_csv(rm.TAXONOMY / "risks.csv")
           if r["risk_id"].startswith("FM")]
    snap_cols = [f"{l}_proposed" for l in LABELS] + [f"{l}_decision" for l in LABELS] \
        + list(FACTS)
    book(rm, INCIDENTS["title"], sheet2_columns(), rows,
         [f"{l}_decision" for l in LABELS] + list(FACTS) + NOTES,
         {"incident_scope_decision": ["ok", *SCOPES],
          "failure_mode_decision": ["ok", *fms, "none"],
          "evidence_type_decision": ["ok", *rm.EVIDENCE_TYPES],
          "interaction_kind": rm.INTERACTION_KINDS, "verification": rm.VERIFICATION},
         INCIDENT_HELP, snap_cols, rm.REVIEW / INCIDENTS["file"])
    return rows


def label_value(rm, label, text, insts, fms):
    t = text.strip()
    if label == "incident_scope":
        if t.lower() not in SCOPES:
            raise ValueError(f"incident_scope {t!r} is not ok, in, out or unclear")
        return t.lower()
    if label == "failure_mode":
        if t.lower() == "none":
            return "none"
        if t.upper() not in fms:
            raise ValueError(f"failure_mode {t!r} is not ok, none or one of {', '.join(fms)}")
        return t.upper()
    if label == "instances":
        if t.lower() == "none":
            return "none"
        ids = [p.strip().upper() for p in t.split(";") if p.strip()]
        bad = [i for i in ids if i not in insts]
        if bad or not ids:
            raise ValueError(f"instances {t!r}: not instance ids ({', '.join(bad) or 'empty'})")
        return "; ".join(ids)
    if t not in rm.EVIDENCE_TYPES:
        raise ValueError(f"evidence_type {t!r} is not ok or one of {', '.join(rm.EVIDENCE_TYPES)}")
    return t


def read_incidents_sheet(rm):
    """Read sheet 2: write the decided labels and changed facts into the ledger, log
    them, add the notes to the dossiers. Returns the number of log rows."""
    got = read_book(rm, INCIDENTS, ["mig_key"] + [f"{l}_decision" for l in LABELS]
                    + list(FACTS) + NOTES)
    if got is None:
        return 0
    generated, rows, snapshot = got
    insts = {r["instance_id"] for r in rm.read_csv(rm.TAXONOMY / "instances.csv")}
    fms = [r["risk_id"] for r in rm.read_csv(rm.TAXONOMY / "risks.csv")
           if r["risk_id"].startswith("FM")]
    current = canonical_rows(rm)
    ledger_all = ledger.read(rm.LEDGER)
    choices = rm.edit_choices()
    env = None
    logged, updates, seen = [], {}, set()
    for r in rows:
        inc, c = r["id"], r["cells"]
        where = f"{INCIDENTS['file']} row {r['row']} {inc}"
        snap, now = snapshot.get(inc), current.get(inc)
        if snap is None or now is None or inc in seen:
            continue
        seen.add(inc)
        new, entries, bad = dict(now), [], []
        for label in LABELS:
            text = c.get(f"{label}_decision", "")
            if text == snap.get(f"{label}_decision", ""):
                continue
            if not text:
                bad.append(f"{label}: a decision is not taken back by blanking it; write "
                           f"the value you want")
                continue
            try:
                if text.strip().lower() == "ok":
                    final, _ = resolve(text, now[f"{label}_proposed"],
                                       snap.get(f"{label}_proposed", ""))
                    dec = "ok"
                else:
                    final, dec = label_value(rm, label, text, insts, fms), text
            except ValueError as e:
                bad.append(str(e))
                continue
            entries.append({"label": label, "proposed": now[f"{label}_proposed"],
                            "decision": dec, "final": final})
            new[f"{label}_decision"], new[f"{label}_final"] = dec, final
        for col, field in FACTS.items():
            text = c.get(col, "")
            if text == snap.get(col, ""):
                continue
            if now[col] != snap.get(col, ""):
                bad.append(f"{col} changed after the sheet was written")
                continue
            try:
                value, canon = rm.parse_edit(field, text, choices)
            except ValueError as e:
                bad.append(str(e))
                continue
            entries.append({"label": col, "proposed": now[col], "decision": canon,
                            "final": canon})
            new[col] = canon
            if col == "occurrence_date":
                new["occurrence_date_precision"] = rm.parse_iso(canon)[1]
        if any(e["label"] == "verification" for e in entries) and not any(
                e["label"] == "last_verified" for e in entries) and new["verification"] != "unverified":
            new["last_verified"] = rm.TODAY
        if bad:
            rm.info(f"  warn  {where}: {'; '.join(bad)}. Nothing in this row is written.")
            continue
        notes = {k: c.get(k, "") for k in NOTES if c.get(k, "")}
        if not entries and not notes:
            continue
        path = rm.dossier_path(inc)
        meta, body = rm.read_dossier(path)
        new_meta = frontmatter_from(rm, meta, new)
        if notes.get("reason"):
            new_meta["multi_agent_basis"] = (
                f"{(meta.get('multi_agent_basis') or '').strip()} Scope reason given by a "
                f"person on sheet 2 on {rm.TODAY}: {notes['reason']}").strip()
        new_body = body
        if notes.get("verification_note"):
            new_body = rm.add_to_section(body, "Verification notes",
                                         f"Curator, {rm.TODAY}: {notes['verification_note']}")
            if new_body is None:
                rm.info(f"  warn  {where}: no ## Verification notes section; not written")
                continue
        env = env or rm.check_env()
        before, _ = rm.check_dossier(path, meta, body, env)
        after, _ = rm.check_dossier(path, new_meta, new_body, env)
        fresh = [p for p in after if p not in before]
        if fresh:
            rm.info(f"  warn  {where}: not written, it would break a dossier rule: "
                    + " | ".join(p.split(": ", 1)[-1] for p in fresh))
            continue
        rm.write_dossier_body(path, new_meta, new_body)
        updates[inc] = new
        for k, v in notes.items():
            entries.append({"label": k, "proposed": "", "decision": v, "final": v})
        for e in entries:
            logged.append({"mig_key": inc, "reason": notes.get("reason", ""),
                           "decided_on": rm.TODAY, "sheet_generated_on": generated, **e})
        rm.info(f"  ok    {inc}: " + ", ".join(f"{e['label']} {e['final']}" for e in entries))
    if updates:
        out = {}
        for key, row in ledger_all.items():
            if row["canonical"] == "true" and row["incident_key"] in updates:
                out[key] = {col: updates[row["incident_key"]][col]
                            for col in ledger.INCIDENT_COLUMNS}
        ledger.write(rm.LEDGER, "incidents", out, keep_absent=True)
    append_log(rm, "incident", logged)
    return len(logged)
