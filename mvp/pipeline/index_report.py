#!/usr/bin/env python3
"""The index report: one Excel workbook with every incident in the index and every record
that is not, each with the reason it stopped where it did.

Reads only what the pipeline already holds (records, queue, context, proposals, verdicts,
the two decision logs, the dossiers and the taxonomy) and writes mvp/out/index_report.xlsx.
It decides nothing: every reason it gives is a decision or reading recorded elsewhere.

    python mvp/pipeline/index_report.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run  # noqa: E402

try:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:  # pragma: no cover
    sys.exit("install openpyxl: pip install -r requirements.txt")

OUT_FILE = run.OUT / "index_report.xlsx"


def taxonomy(name, key, label):
    with open(run.MVP / "taxonomy" / name, encoding="utf-8") as fh:
        return {r[key]: r for r in csv.DictReader(fh)}, label


def split_body(body):
    """'## Name' sections of a dossier body, as {name: text}."""
    out, name, buf = {}, None, []
    for line in body.splitlines():
        if line.startswith("## ") and line[3:].strip() in run.SECTIONS:
            if name:
                out[name] = "\n".join(buf).strip()
            name, buf = line[3:].strip(), []
        elif name:
            buf.append(line)
    if name:
        out[name] = "\n".join(buf).strip()
    return out


def cut(text, n=700):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def joined(values):
    return "; ".join(str(v) for v in values or [])


# ------------------------------------------------------------------ in the index

def origin_of(meta, sections):
    notes = sections.get("Verification notes", "")
    if "Written by Claude" in notes:
        return f"promoted {meta.get('first_seen')}; dossier written by Claude from the readings"
    if meta.get("canonical_source") != "aiid":
        return "carried over from the PoC"
    return "carried over from the PoC; AIID record linked 2026-11-23"


# Report column -> the dossier fields it shows. A cell is marked as a person's when one
# of its fields is in the dossier's set_by_person.
FROM_FIELDS = {
    "title": ["title"], "date": ["occurrence_date"], "evidence_type": ["evidence_type"],
    "failure_mode": ["failure_mode"], "failure_mode_name": ["failure_mode"],
    "failure_mode_source": ["failure_mode"],
    "instances": ["instances", "instances_presumed"],
    "instance_names": ["instances", "instances_presumed"],
    "instances_discussed_under": ["instances", "instances_presumed"],
    "instances_presumed": ["instances_presumed"], "verification": ["verification"],
    "last_verified": ["last_verified"], "scope_basis": ["multi_agent", "multi_agent_basis"],
    "actor_count": ["actor_count"], "interaction_kind": ["interaction_kind"],
    "systems": ["systems"],
}
MINE = PatternFill("solid", start_color="C6EFCE")


def index_rows(risks, insts):
    """One row per dossier in scope (multi_agent true). The others go to
    out_of_scope_dossiers."""
    rows = []
    for path in run.all_dossiers():
        meta, body = run.read_dossier(path)
        if meta.get("multi_agent") is not True:
            continue
        sec = split_body(body)
        mine = set(meta.get(run.SET_BY_PERSON) or [])
        fm = meta.get("failure_mode") or ""
        ids = meta.get("instances") or []
        presumed = meta.get("instances_presumed") or []
        ids = ids + [i for i in presumed if i not in ids]
        srcs = meta.get("sources") or []
        rows.append({
            "mig_key": meta.get("mig_key"),
            "source_id": meta.get("canonical_source"),
            "source_key": meta.get("source_key") or "",
            "title": meta.get("title"),
            "date": meta.get("occurrence_date"),
            "evidence_type": meta.get("evidence_type"),
            "failure_mode": fm,
            "failure_mode_name": risks.get(fm, {}).get("risk", "") if fm else "",
            "failure_mode_source": meta.get("failure_mode_source") or "",
            "instances": joined(ids),
            "instance_names": joined(insts.get(i, {}).get("instance", i) for i in ids),
            "instances_discussed_under": joined(sorted({insts.get(i, {}).get("risk_id", "")
                                                       for i in ids} - {""})),
            "instances_presumed": joined(presumed),
            "verification": meta.get("verification"),
            "last_verified": meta.get("last_verified") or "",
            "set_by_person": joined(meta.get(run.SET_BY_PERSON)),
            "_mine": {c for c, fs in FROM_FIELDS.items() if mine & set(fs)},
            "origin": origin_of(meta, sec),
            "scope_basis": meta.get("multi_agent_basis"),
            "actor_count": meta.get("actor_count"),
            "interaction_kind": meta.get("interaction_kind"),
            "systems": joined(meta.get("systems")),
            "sources": joined(f"{s.get('source_id')}:{s.get('record_id')}" for s in srcs),
            "url": (srcs[0].get("url") if srcs else ""),
            "what_happened": cut(sec.get("What happened")),
            "dossier": str(path.relative_to(run.ROOT)),
        })
    return rows


INDEX_COLS = [
    ("mig_key", 11, "Our key, MIG-nnnn: unique, given when the record first reached the decide-scope sheet, never changed. The dossier is mvp/incidents/<mig_key>.md."),
    ("source_id", 11, "The canonical source: the one whose key is source_key."),
    ("source_key", 14, "The key the source itself uses (AIID's incident number, AI Village's AIV-nn); blank when the source has none."),
    ("title", 45, "Title of the incident."),
    ("date", 11, "Event date, or publication date for studies; partial dates allowed."),
    ("evidence_type", 13, "real_world / synthetic / lab / theoretical (mvp/taxonomy/evidence_types.csv)."),
    ("failure_mode", 9, "FM1 Miscoordination, FM2 Conflict, FM3 Collusion, from the Gate 2 tree; empty when none applies (normal for attacks)."),
    ("failure_mode_name", 16, "Name of the failure mode."),
    ("failure_mode_source", 20, "ours = a person judged it; classifier:<prompt>@<version> = derived by rule from the model's facts, not yet confirmed by a person."),
    ("instances", 14, "All instance ids, quoted and presumed (mvp/taxonomy/instances.csv). Descriptive; assigned independently of the failure mode. The presumed ones are repeated in instances_presumed."),
    ("instance_names", 30, "Names of all the instances, quoted and presumed."),
    ("instances_discussed_under", 14, "The failure mode or risk factor under which Hammond et al. discuss those instances. A reading aid only: never a label of this incident."),
    ("instances_presumed", 12, "I28; I29 presumed for an attack whose source does not say what the number or mix of agents contributed. Not quoted. Also listed in instances."),
    ("verification", 15, "verified / partially_verified / unverified against the primary source by a person."),
    ("last_verified", 12, "When a person last checked the dossier against the primary source."),
    ("set_by_person", 20, "The dossier fields a person set on sheet 3 (mvp/review/3_edit_dossiers.xlsx), each logged in mvp/review/dossier_edits_log.csv. The cells showing those fields are green."),
    ("origin", 30, "How the dossier came to be."),
    ("scope_basis", 50, "Why the incident is in scope: always a person's verdict."),
    ("actor_count", 10, "Number of AI agents when the source states it; unclear otherwise."),
    ("interaction_kind", 18, "communication / one-acting-on-another / shared-environment / none / unclear."),
    ("systems", 30, "The AI agents or systems involved, as named."),
    ("sources", 22, "Source records attesting the incident (source_id:record_id)."),
    ("url", 30, "Canonical source page."),
    ("what_happened", 60, "Short account from the dossier."),
    ("dossier", 26, "The dossier file."),
]

# ---------------------------------------------------------------- not in the index

STAGES = [
    "1 Prefilter: not screened",
    "1 Prefilter: outside rater said no",
    "2 Reading: one agent or none",
    "3 Rules: out, not decided by a person",
    "3 Rules: unsettled, not decided by a person",
    "4 Person: decided out",
    "4 Person: decided unclear",
    "5 Person: decided in, not promoted",
    "5 Person: decided in, awaiting promotion",
    "6 Dossier: out of scope",
    "6 Dossier: scope unclear",
    "Other",
]


def out_of_scope_dossiers():
    """Dossiers whose multi_agent is not true: a dossier exists, but the incident is not
    in the index."""
    rows = []
    for path in run.all_dossiers():
        meta, _ = run.read_dossier(path)
        if meta.get("multi_agent") is True:
            continue
        out = meta.get("multi_agent") is False
        srcs = meta.get("sources") or []
        by_person = "multi_agent" in (meta.get(run.SET_BY_PERSON) or [])
        rows.append({
            "mig_key": meta.get("mig_key") or path.stem,
            "source_id": meta.get("canonical_source") or "",
            "source_key": meta.get("source_key") or "",
            "title": meta.get("title", ""), "date": meta.get("occurrence_date", ""),
            "url": srcs[0].get("url", "") if srcs else "",
            "stage": "6 Dossier: out of scope" if out else "6 Dossier: scope unclear",
            "decided_by": ("person (sheet 3)" if by_person
                           else "person (dossier)"
                           if meta.get("multi_agent_label_source") == "ours"
                           else "dossier"),
            "reason": ("The dossier says multi_agent false: not a multi-agent incident."
                       if out else "The dossier says multi_agent unclear: the sources do "
                       "not settle whether AI agents acted on each other."),
            "detail": meta.get("multi_agent_basis") or "",
            "flags": "",
        })
    return rows


def rules_reason(v, g):
    """Why the rules leave a record out or unsettled, from the verdict and the facts."""
    labels = run.rules.labels_of(v)
    say = run.rules_say(v)
    n = run.rules.agent_count(g) if g else None
    cf = labels.get("counterfactual_resolved")
    security = bool(g) and run.rules.is_security(g)
    if say == "out":
        if n is not None and n < 2:
            return (f"The facts show fewer than two AI agents (n_ai_agents {n}), so no "
                    f"agents interacted.")
        if cf == "could":
            why = ("one capable agent could have produced this outcome (single-agent "
                   "counterfactual: could)")
            if security and g.get("multiplicity_role") == "incidental":
                why = "the harm turned on one agent's capability (multiplicity incidental)"
            return f"The rules say out: {why}."
        if not security and g.get("interaction_present") is not True:
            return "The rules say out: no interaction between AI agents is shown."
        return "The rules say out."
    why = ", ".join(v.get("review_why") or []) or "not settled"
    return f"The rules could not settle scope ({why})."


def not_in_index_rows():
    records = run.latest_records()
    attested = run.dossier_source_refs()
    queue = {run.row_pair(r): r for r in run.read_jsonl(run.STATE / "queue.jsonl")}
    ctx = run.load_context()
    verdicts = run.read_verdicts()
    gates = run.proposal_rows("extract_gate")
    scope = run.scope_newest(records)
    promo = run.newest_by_key(run.read_log("promote"))
    frozen = run.read_frozen()
    index = run.mig_index()
    rows = []
    for (sid, rid), rec in sorted(records.items(), key=lambda kv: run.natural(
            run.record_key(*kv[0]))):
        if (sid, rid) in attested:
            continue
        key = run.record_key(sid, rid)
        row = {**run.key_fields((sid, rid), index),
               "title": rec.get("title", ""), "date": rec.get("date", ""),
               "url": rec.get("url", ""), "stage": "Other", "decided_by": "", "reason": "",
               "detail": "", "flags": ""}
        q = queue.get((sid, rid))
        if q is None:
            if sid == run.MA_SOURCE and rec.get("date", "") >= run.RECENT_FROM \
                    and run.outside_says_no(rec):
                labs = [f"{l.get('namespace') or l.get('source')}: {l.get('field')} = "
                        f"{l.get('value')}" for l in rec.get("external_labels") or []
                        if l.get("field") == run.MA_FIELD]
                row.update(stage="1 Prefilter: outside rater said no",
                           decided_by="outside rater (acted on by curator rule 2026-11-18)",
                           reason="An outside rater answered the multi-agent question no, "
                                  "and none said yes or maybe; for 2024+ records the "
                                  "project acts on that answer.",
                           detail=joined(labs))
            elif sid == run.MA_SOURCE and rec.get("date", "") < run.RECENT_FROM \
                    and key not in frozen:
                row.update(stage="1 Prefilter: not screened", decided_by="scope rule",
                           reason="Dated before 2024 and not on the frozen pre-2024 list, so "
                                  "the pipeline never screened it.",
                           detail=f"date {rec.get('date', '') or 'none'}")
            else:
                row.update(stage="Other", decided_by="scope rule",
                           reason="No prefilter rule queues it (not a recent AIID record, "
                                  "not on the frozen list, not added by hand).")
            rows.append(row)
            continue
        row["flags"] = q.get("flags", "")
        c = ctx.get((sid, rid))
        if c and c.get("agent_count") in ("one", "none"):
            facts = (c.get("facts") or {}).get("agents") or {}
            depth = run.best_depth(c)
            row.update(stage="2 Reading: one agent or none",
                       decided_by=f"model reading ({depth})",
                       reason=("No AI agent acts in the event." if c["agent_count"] == "none"
                               else "Only one AI agent acts in the event.")
                       + " A multi-agent incident needs two or more.",
                       detail=cut(" ".join(x for x in (facts.get("text"),
                                  f"Quote: “{facts['quote']}”" if facts.get("quote") else "")
                                  if x)))
            rows.append(row)
            continue
        v = verdicts.get((sid, rid))
        if v is None:
            row.update(reason="Queued but not yet judged: its reading is not complete.",
                       decided_by="pipeline")
            rows.append(row)
            continue
        g = gates.get((sid, rid), {})
        d = scope.get(key)
        if d and d.get("decision") == "out":
            row.update(stage="4 Person: decided out", decided_by="person (sheet 1)",
                       reason="A person decided it is not a multi-agent incident.",
                       detail=d.get("reason") or "")
        elif d and d.get("decision") == "unclear":
            row.update(stage="4 Person: decided unclear", decided_by="person (sheet 1)",
                       reason="A person decided the source was read and does not say "
                              "whether two or more AI agents interacted.",
                       detail=d.get("reason") or "")
        elif d and d.get("decision") == "in":
            p = promo.get(key)
            if p and p.get("decision") == "no":
                row.update(stage="5 Person: decided in, not promoted",
                           decided_by="person (sheet 2)",
                           reason="Decided in on sheet 1, then not promoted to a dossier.",
                           detail=p.get("note") or "")
            else:
                row.update(stage="5 Person: decided in, awaiting promotion",
                           decided_by="person (sheet 1)",
                           reason="Decided in; no promote decision yet.")
        else:
            say = run.rules_say(v)
            row.update(stage=("3 Rules: out, not decided by a person" if say == "out"
                              else "3 Rules: unsettled, not decided by a person"),
                       decided_by="rules (a suggestion; no person decided)",
                       reason=rules_reason(v, g),
                       detail=cut(g.get("uncertainty_reason") or ""))
        rows.append(row)
    return rows


NOT_COLS = [
    ("mig_key", 11, "Our key, MIG-nnnn. Blank for a record that never reached the decide-scope sheet (stages 1 and 2): those have only their source key."),
    ("source_id", 11, "The source the record comes from."),
    ("source_key", 14, "The key the source itself uses; blank when it has none."),
    ("title", 50, "Title of the record."),
    ("date", 11, "Record date."),
    ("stage", 34, "Where the record stopped. 1 prefilter, 2 reading, 3 rules, 4 scope decision, 5 promotion, 6 a dossier that does not put the incident in scope."),
    ("decided_by", 26, "Who or what stopped it. Only `person` rows are human decisions; `rules` rows are suggestions nobody has confirmed."),
    ("reason", 60, "Why it is not in the index."),
    ("detail", 60, "The evidence behind the reason: the person's note, the reading's quote, or the model's uncertainty."),
    ("flags", 10, "Prefilter flags: label (an outside rater said yes or maybe), keyword (a multi-agent term in the text)."),
    ("url", 30, "Source page."),
]


# ---------------------------------------------------------------------- write

HEAD = PatternFill("solid", start_color="D9E1F2")


def add_table(ws, cols, rows):
    ws.append([c for c, _, _ in cols])
    for i, (name, width, _) in enumerate(cols, 1):
        cell = ws.cell(1, i)
        cell.font = Font(bold=True)
        cell.fill = HEAD
        cell.alignment = Alignment(vertical="top", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = width
    for r in rows:
        ws.append([run.clean(r.get(c, "")) for c, _, _ in cols])
    wrap = {c for c, w, _ in cols if w >= 30}
    for row, r in zip(ws.iter_rows(min_row=2), rows):
        for cell, (name, _, _) in zip(row, cols):
            cell.alignment = Alignment(vertical="top", wrap_text=name in wrap)
            if name in r.get("_mine", ()):
                cell.fill = MINE
            if name == "url" and str(cell.value).startswith(("http://", "https://")):
                cell.hyperlink = str(cell.value)
                cell.style = "Hyperlink"
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{max(len(rows) + 1, 2)}"


def main():
    risks, _ = taxonomy("risks.csv", "risk_id", "risk")
    insts, _ = taxonomy("instances.csv", "instance_id", "instance")
    inn = index_rows(risks, insts)
    out = out_of_scope_dossiers() + not_in_index_rows()

    wb = openpyxl.Workbook()
    summ = wb.active
    summ.title = "Summary"
    summ.column_dimensions["A"].width = 52
    summ.column_dimensions["B"].width = 12
    summ.column_dimensions["C"].width = 70
    lines = [
        ("Index report", "", f"generated {run.TODAY} from the pipeline's files"),
        ("", "", ""),
        ("In the index (dossiers)", len(inn), "sheet `In the index`"),
        ("  records they cover", sum(len(r["sources"].split("; ")) for r in inn), ""),
        ("Not in the index (records)", len(out), "sheet `Not in the index`; filter on `stage`"),
    ]
    for stage in STAGES:
        n = sum(1 for r in out if r["stage"] == stage)
        if n:
            lines.append((f"  {stage}", n, ""))
    lines += [("", "", ""),
              ("Evidence type of indexed incidents", "", "")]
    for et in run.EVIDENCE_TYPES:
        lines.append((f"  {et}", sum(1 for r in inn if r["evidence_type"] == et), ""))
    lines.append(("Failure mode of indexed incidents", "", ""))
    for fm in ("FM1", "FM2", "FM3", ""):
        n = sum(1 for r in inn if r["failure_mode"] == fm)
        lines.append((f"  {fm + ' ' + risks[fm]['risk'] if fm else 'none'}", n, ""))
    lines.append(("Verification of indexed incidents", "", ""))
    for vv in run.VERIFICATION:
        lines.append((f"  {vv}", sum(1 for r in inn if r["verification"] == vv), ""))
    for a, b, c in lines:
        summ.append([a, b, c])
    summ.cell(1, 1).font = Font(bold=True, size=13)

    add_table(wb.create_sheet("In the index"), INDEX_COLS, inn)
    add_table(wb.create_sheet("Not in the index"), NOT_COLS, out)

    ref = wb.create_sheet("Failure modes and instances")
    ref.append(["id", "name", "kind", "definition"])
    for r in risks.values():
        ref.append([r["risk_id"], r["risk"], r["risk_type"], r["definition"]])
    for r in insts.values():
        ref.append([r["instance_id"], r["instance"], f"instance (discussed under {r['risk_id']})",
                    r["definition"]])
    for i, w in enumerate((8, 34, 26, 100), 1):
        ref.column_dimensions[get_column_letter(i)].width = w
        ref.cell(1, i).font = Font(bold=True)
        ref.cell(1, i).fill = HEAD
    for row in ref.iter_rows(min_row=2):
        row[3].alignment = Alignment(wrap_text=True, vertical="top")

    cols = wb.create_sheet("Columns")
    cols.append(["sheet", "column", "meaning"])
    for sheet, spec in (("In the index", INDEX_COLS), ("Not in the index", NOT_COLS)):
        for name, _, meaning in spec:
            cols.append([sheet, name, meaning])
    for i, w in enumerate((18, 26, 110), 1):
        cols.column_dimensions[get_column_letter(i)].width = w
        cols.cell(1, i).font = Font(bold=True)
        cols.cell(1, i).fill = HEAD
    for row in cols.iter_rows(min_row=2):
        row[2].alignment = Alignment(wrap_text=True, vertical="top")

    run.OUT.mkdir(parents=True, exist_ok=True)
    wb.save(OUT_FILE)
    print(f"  ok    report: {len(inn)} in the index, {len(out)} not -> "
          f"{OUT_FILE.relative_to(run.ROOT)}")


if __name__ == "__main__":
    main()
