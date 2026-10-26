#!/usr/bin/env python3
"""Build the Mind the Interagent Gap outputs from data/*.csv.

Outputs (in out/):
  multi_agent_risk_taxonomy.xlsx  risk index, FM-RF links, taxonomy, instances, evidence, sources
  dashboard.html                  self-contained ontology dashboard, data inlined, opens on file://
  risk_index.csv                  flat FM/RF index with grounding scores (for pipelines)
  associations.csv                FM-RF links with evidence_link and grounding
  evidence.csv                    every piece of evidence, case studies and incidents

The Evidence sheet is the single table of evidence: Hammond case studies and inventory incidents
together, told apart by evidence_class. Grounding and every evidence_score_max run over the whole
inventory, not case studies alone.

Usage:  python build/build_xlsx.py
The taxonomy workbook uses live formulas; Excel/LibreOffice compute them on open.
The CSV outputs hold the same scores computed in Python.
"""
import csv
import json
import sys
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
DATA, OUT = ROOT / "data", ROOT / "out"

TYPES = ["Observed in real world", "Synthetic evidence", "Observed in lab", "Theoretical"]
E_COLS = ["e1_ecological_validity", "e2_causal_attribution", "e3_scale_precision",
          "e4_corroboration", "e5_source_vetting"]
REPORT_URL = "https://arxiv.org/abs/2502.14143"
NL = "\n"


# ---------------------------------------------------------------- data
def read(name):
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ids(value):
    return [x.strip() for x in (value or "").split(";") if x.strip()]


def parse_date(value):
    """ISO date, possibly partial (2025, 2025-06, 2025-06-18) -> (date, excel number format)."""
    parts = [int(p) for p in value.split("-")]
    fmt = {1: "yyyy", 2: "yyyy-mm", 3: "yyyy-mm-dd"}[len(parts)]
    return date(*(parts + [1] * (3 - len(parts)))), fmt


def score(row):
    vals = [row.get(c, "") for c in E_COLS]
    return None if any(v == "" for v in vals) else sum(int(v) for v in vals)


def band(s):
    if s is None:
        return None
    return "Strong" if s >= 9 else "Moderate" if s >= 6 else "Limited" if s >= 3 else "Weak"


risks = read("risks.csv")
directions = read("risk_directions.csv")
instances = read("risk_instances.csv")
assocs = read("associations.csv")
cases = read("case_studies.csv")
incidents = read("incidents.csv")
sources = read("sources.csv")
prefixes = read("id_prefixes.csv")
instances_by_id = {i["instance_id"]: i for i in instances}

R = {r["risk_id"]: r for r in risks}
FM = [r["risk_id"] for r in risks if r["risk_type"] == "Failure mode"]
RF = [r["risk_id"] for r in risks if r["risk_type"] == "Risk factor"]
CS = {c["case_study_id"]: c for c in cases}
INST = {i["instance_id"]: i for i in instances}
name = lambda rid: R[rid]["risk"]


def inst_risks(row):
    """Risks a piece of evidence reaches through its instances: the link layer."""
    return sorted({INST[i]["risk_id"] for i in ids(row.get("instances", "")) if i in INST},
                  key=lambda x: (x[:2], int(x[2:])))


# ---------------------------------------------------------------- validation
def validate():
    err = []
    seen = set()
    for table, key in ((risks, "risk_id"), (instances, "instance_id"), (cases, "case_study_id"), (incidents, "event_id")):
        for row in table:
            if row[key] in seen:
                err.append(f"duplicate id {row[key]}")
            seen.add(row[key])
    for row in directions + instances:
        if row["risk_id"] not in R:
            err.append(f"unknown risk_id {row['risk_id']}")
    for row in instances:
        for c in ids(row["case_studies_explicit"]) + ids(row["case_studies_placement"]):
            if c not in CS:
                err.append(f"{row['instance_id']}: unknown case study {c}")
        has_cs = bool(ids(row["case_studies_explicit"]) or ids(row["case_studies_placement"]))
        if row["provenance"] == "Hammond Table 1" and has_cs != (row["evidence_basis"] == "Case study"):
            err.append(f"{row['instance_id']}: evidence_basis inconsistent with linked case studies")
    pairs = set()
    for a in assocs:
        if a["fm_id"] not in FM or a["rf_id"] not in RF:
            err.append(f"association {a['fm_id']}-{a['rf_id']}: bad ids")
        pairs.add((a["fm_id"], a["rf_id"]))
    for row in cases + incidents:
        rid = row.get("case_study_id") or row["event_id"]
        for f in ids(row["failure_modes"]):
            if f not in FM:
                err.append(f"{rid}: unknown failure mode {f}")
        for r in ids(row["risk_factors"]):
            if r not in RF:
                err.append(f"{rid}: unknown risk factor {r}")
        if row["type"] not in TYPES:
            err.append(f"{rid}: type '{row['type']}' not in {TYPES}")
        try:
            parse_date(row["date"])
        except Exception:
            err.append(f"{rid}: bad date '{row['date']}'")
        vals = [row.get(c, "") for c in E_COLS]
        if any(vals) and not all(v in {"0", "1", "2"} for v in vals):
            err.append(f"{rid}: E1-E5 must all be 0, 1 or 2 (or all blank)")
    # NB: no co-tag invariant. One row reaching both a failure mode and a risk factor, through
    # two separate instances, is two independent claims -- never evidence that the two are linked.
    # Associations record only what the authors assert; see docs/methodology.md.
    for a in assocs:
        if a["basis"] not in ("Paper prose", "Paper Table 3 co-tag"):
            err.append(f"association {a['fm_id']}-{a['rf_id']}: unknown basis '{a['basis']}'")
        if a["basis"] == "Paper prose" and not a["text_reference"].strip():
            err.append(f"association {a['fm_id']}-{a['rf_id']}: basis is prose but text_reference is empty")
    for r in RF:  # the model requires every risk factor to reach at least one failure mode
        if not any(a["rf_id"] == r for a in assocs):
            err.append(f"{r} is linked to no failure mode")
    # instances are the link layer: every risk tag must be derivable from them
    inst_ids = {i["instance_id"] for i in instances}
    for row in cases + incidents:
        rid = row.get("case_study_id") or row["event_id"]
        linked_i = ids(row.get("instances", ""))
        for i in linked_i:
            if i not in inst_ids:
                err.append(f"{rid}: unknown instance {i}")
        reach = {instances_by_id[i]["risk_id"] for i in linked_i if i in inst_ids}
        tagged_r = set(ids(row["failure_modes"]) + ids(row["risk_factors"]))
        if tagged_r - reach:
            err.append(f"{rid}: tags {','.join(sorted(tagged_r - reach))} not reachable through "
                       f"its instances ({','.join(linked_i) or 'none'})")
        if reach - tagged_r:
            err.append(f"{rid}: instances reach {','.join(sorted(reach - tagged_r))} but the row "
                       f"is not tagged with it")
        if not linked_i and score(row) is not None:
            err.append(f"{rid}: scored but has no instance, so it links to no risk")
    for i in instances:
        if i["evidence_basis"] == "Incident evidence" and not any(
                i["instance_id"] in ids(x.get("instances", "")) for x in incidents):
            err.append(f"{i['instance_id']}: basis 'Incident evidence' but no incident links to it")
        if i["provenance"] not in ("Hammond Table 1", "Ours"):
            err.append(f"{i['instance_id']}: unknown provenance '{i['provenance']}'")
    for s in sources:
        if s["event_id"] and s["event_id"] not in {i["event_id"] for i in incidents}:
            err.append(f"sources.csv: unknown event_id {s['event_id']}")
    import re
    pats = {}
    for p in prefixes:
        pats.setdefault(p["table"], []).append(re.compile(p["id_pattern"]))
    for table, rows_, key in (("risks.csv", risks, "risk_id"), ("risk_instances.csv", instances, "instance_id"),
                              ("case_studies.csv", cases, "case_study_id"), ("incidents.csv", incidents, "event_id")):
        for row in rows_:
            if not any(p.match(row[key]) for p in pats.get(table, [])):
                err.append(f"{table}: id {row[key]} matches no prefix in id_prefixes.csv")
    if err:
        sys.exit("Validation failed:\n  " + "\n  ".join(err))


validate()


# ---------------------------------------------------------------- evidence rows
CASE_CLASS, INCIDENT_CLASS = "Case study", "Incident"


def evidence_rows():
    """Hammond case studies and inventory incidents as one list of dicts, cases first."""
    out = []
    for c in cases:
        out.append(dict(
            id=c["case_study_id"], evidence_class=CASE_CLASS, title=c["title"], date=c["date"],
            instances=c.get("instances", ""),
            type=c["type"], source_class=c["hammond_type"], system=None, system_basis=c["system_basis"],
            harm=c["harm"], failure_modes=c["failure_modes"], risk_factors=c["risk_factors"],
            e=[c[e] for e in E_COLS],
            notes=" ".join(x for x in [c["scoring_note"], c["type_note"]] if x) or None,
            page=int(c["page"]), source=c["source"], source_url=REPORT_URL,
            retrieved_on=date(2026, 10, 25), summary=c["summary"]))
    for i in sorted(incidents, key=lambda i: parse_date(i["date"])[0], reverse=True):
        out.append(dict(
            id=i["event_id"], evidence_class=INCIDENT_CLASS, title=i["incident"], date=i["date"],
            instances=i.get("instances", ""),
            type=i["type"], source_class=i["source_class"], system=i["system"] or None,
            system_basis=i["system_basis"] or None, harm=i["harm"], failure_modes=i["failure_modes"],
            risk_factors=i["risk_factors"], e=[i[e] for e in E_COLS], notes=i["notes"] or None,
            page=None, source=i["source"], source_url=i["source_url"],
            retrieved_on=date.fromisoformat(i["retrieved_on"]), summary=None))
    return out


# ---------------------------------------------------------------- derived values
EVID = evidence_rows()
EV = {x["id"]: x for x in EVID}
short = lambda t, n=80: t if len(t) <= n else t[:n - 1].rstrip() + "…"


def escore(x):
    """Evidence score of an EVID row, or None where E1-E5 are blank."""
    return None if any(v == "" for v in x["e"]) else sum(int(v) for v in x["e"])


def tagged(rid):
    """Every piece of evidence tagged with this risk: case studies and incidents alike."""
    col = "failure_modes" if rid in FM else "risk_factors"
    return [x for x in EVID if rid in ids(x[col])]


def amplifies(fm, rf):
    """Grounding the risk factor contributes to a failure mode it is linked to.

    This is a *routed* signal, not evidence that this event showed this mechanism: evidence
    attaches to a single-risk instance, never to a pair.
    """
    return max_score(tagged(rf)) / 10


def max_score(ev_list):
    s = [escore(x) for x in ev_list if escore(x) is not None]
    return max(s) if s else 0


def linked(rid):
    if rid in FM:
        return [(a["rf_id"], a) for a in assocs if a["fm_id"] == rid]
    return [(a["fm_id"], a) for a in assocs if a["rf_id"] == rid]


def link_flag(a):
    """TRUE where the authors argue the link in prose, FALSE where it rests on a Table 3 co-tag."""
    return a["basis"] == "Paper prose"


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


OUT.mkdir(exist_ok=True)
write_csv(OUT / "risk_index.csv",
          ["risk_id", "risk", "risk_type", "section", "grounding_score", "evidence", "evidence_n", "associations",
           "link_basis"],
          [[r["risk_id"], r["risk"], r["risk_type"], r["section"], max_score(tagged(r["risk_id"])) / 10,
            ";".join(x["id"] for x in tagged(r["risk_id"])), len(tagged(r["risk_id"])),
            ";".join(o for o, _ in linked(r["risk_id"])),
            ";".join(a["basis"] for _, a in linked(r["risk_id"]))] for r in risks])
write_csv(OUT / "associations.csv",
          ["fm_id", "failure_mode", "rf_id", "risk_factor", "basis", "fm_grounding", "rf_grounding",
           "amplification"],
          [[a["fm_id"], name(a["fm_id"]), a["rf_id"], name(a["rf_id"]), a["basis"],
            max_score(tagged(a["fm_id"])) / 10, max_score(tagged(a["rf_id"])) / 10,
            amplifies(a["fm_id"], a["rf_id"])] for a in assocs])


# ---------------------------------------------------------------- styling helpers
HDR_FILL = PatternFill("solid", fgColor="1F3864")
HDR_FONT = Font(name="Arial", bold=True, color="FFFFFF", size=10)
BODY = Font(name="Arial", size=10)
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
FM_FILL = {"Miscoordination": "DEEAF6", "Conflict": "FCE4D6", "Collusion": "E2EFDA"}
fill = lambda hex_: PatternFill("solid", fgColor=hex_)


def table(ws, header, rows, widths, freeze="C2"):
    ws.append(header)
    for c in ws[1]:
        c.fill, c.font = HDR_FILL, HDR_FONT
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for row in rows:
        ws.append(row)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.font, c.border = BODY, BORDER
            c.alignment = Alignment(wrap_text=True, vertical="top")
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = freeze
    ws.auto_filter.ref = ws.dimensions
    ws.row_dimensions[1].height = 30
    return {h: get_column_letter(i) for i, h in enumerate(header, 1)}


def center(ws, col, fmt=None):
    for r in range(2, ws.max_row + 1):
        c = ws[f"{col}{r}"]
        c.alignment = Alignment(horizontal="center", vertical="top")
        if fmt:
            c.number_format = fmt


def notes(ws, lines):
    for line in lines:
        ws.append([line])
        c = ws.cell(ws.max_row, 1)
        c.font = Font(name="Arial", size=10, bold=line.isupper())
        c.alignment = Alignment(wrap_text=True)
    ws.column_dimensions["A"].width = 130


NOTES_COMMON = [
    "Source of truth is data/*.csv in the repo; this file is generated by build/build_xlsx.py. Do not edit by hand.",
    "Methodology, definitions and the evidence rubric: docs/methodology.md.",
    "TYPE: Observed in real world = deployed systems acting on real stakes outside experimenter control. "
    "Synthetic evidence = agents interacting in a simulated or researcher-built environment (e.g. GovSim, wargames, AI Village). "
    "Observed in lab = controlled experiment on real models in a narrow task probe. Theoretical = argument, formal model or non-AI analogue only.",
    "EVIDENCE SCORE: E1 ecological validity, E2 causal attribution, E3 scale and precision, E4 independent corroboration, "
    "E5 source vetting; each 0-2, summed 0-10. Bands: Strong 9-10, Moderate 6-8, Limited 3-5, Weak 0-2.",
]


# ---------------------------------------------------------------- taxonomy workbook
def build_taxonomy():
    wb = Workbook()

    # Evidence (built first: other sheets reference it)
    ws_ev = wb.active
    ws_ev.title = "Evidence"
    ev = evidence_rows()
    H = ["id", "evidence_class", "title", "date", "type", "source_class", "system", "system_basis", "harm",
         "failure_modes", "risk_factors", "evidence_strength", "evidence_score", *E_COLS, "notes", "page",
         "source", "source_url", "retrieved_on", "summary"]
    fmts, rows = [], []
    for x in ev:
        d, f = parse_date(x["date"])
        fmts.append(f)
        rows.append([x["id"], x["evidence_class"], x["title"], d, x["type"], x["source_class"], x["system"],
                     x["system_basis"], x["harm"],
                     NL.join(name(y) for y in ids(x["failure_modes"])) or None,
                     NL.join(name(y) for y in ids(x["risk_factors"])) or None,
                     None, None, *[int(v) if v != "" else None for v in x["e"]],
                     x["notes"], x["page"], x["source"], x["source_url"], x["retrieved_on"], x["summary"]])
    L = table(ws_ev, H, rows, [15, 13, 58, 10, 20, 20, 30, 16, 16, 16, 22, 12, 10, 9, 9, 9, 9, 9,
                               48, 6, 26, 32, 12, 55], freeze="C2")
    for r, (x, f) in enumerate(zip(ev, fmts), 2):
        ws_ev[f"{L['date']}{r}"].number_format = f
        ws_ev[f"{L['retrieved_on']}{r}"].number_format = "yyyy-mm-dd"
        u = ws_ev[f"{L['source_url']}{r}"]
        u.hyperlink, u.font = u.value, Font(name="Arial", size=10, color="0563C1", underline="single")
        cell = f"{L['evidence_score']}{r}"
        if all(v != "" for v in x["e"]):
            ws_ev[cell] = f"=SUM({L[E_COLS[0]]}{r}:{L[E_COLS[-1]]}{r})"
            ws_ev[f"{L['evidence_strength']}{r}"] = (
                f'=IF({cell}>=9,"Strong",IF({cell}>=6,"Moderate",IF({cell}>=3,"Limited","Weak")))')
        else:
            ws_ev[f"{L['evidence_strength']}{r}"] = "unscored"
        if x["evidence_class"] == CASE_CLASS:
            for c in ws_ev[r]:
                c.fill = fill("F2F2F2")
    for col in [L["evidence_score"]] + [L[e] for e in E_COLS]:
        center(ws_ev, col)
    n = len(ev) + 50  # head-room for added rows
    CSR = "Evidence!"
    SC = f"{CSR}${L['evidence_score']}$2:${L['evidence_score']}${n}"
    FMR = f"{CSR}${L['failure_modes']}$2:${L['failure_modes']}${n}"
    RFR = f"{CSR}${L['risk_factors']}$2:${L['risk_factors']}${n}"
    ECR = f"{CSR}${L['evidence_class']}$2:${L['evidence_class']}${n}"
    IDR = f"{CSR}$A$2:$A${n}"

    def maxifs(fm=None, rf=None, evidence_class=None):
        """Grounding counts the whole evidence inventory; pass evidence_class to restrict it."""
        crit = ([f'{FMR},"*{name(fm)}*"'] if fm else []) + ([f'{RFR},"*{name(rf)}*"'] if rf else [])
        if evidence_class:
            crit.append(f'{ECR},"{evidence_class}"')
        return f"_xlfn.MAXIFS({SC},{','.join(crit)})"

    def strength(cell):
        return f'=IF({cell}=0,"—",IF({cell}>=9,"Strong",IF({cell}>=6,"Moderate",IF({cell}>=3,"Limited","Weak"))))'

    # Risk Index
    ws = wb.create_sheet("Risk Index", 0)
    rows = []
    for r in risks:
        rid = r["risk_id"]
        lk = linked(rid)
        g = maxifs(fm=rid) if rid in FM else maxifs(rf=rid)
        ev = tagged(rid)
        rows.append([rid, r["risk"], r["risk_type"], r["section"], f"={g}/10",
                     ", ".join(x["id"] for x in ev) or "—", len(ev),
                     NL.join(name(o) for o, _ in lk) or "—",
                     NL.join(a["basis"] for _, a in lk) or "—"])
    L = table(ws, ["risk_id", "risk", "risk_type", "section", "grounding_score", "evidence", "evidence_n",
                   "associations", "link_basis"], rows, [8, 26, 14, 8, 15, 40, 11, 26, 20])
    center(ws, L["grounding_score"], "0.00")
    center(ws, L["evidence_n"])
    for r in range(2, ws.max_row + 1):
        if ws[f"C{r}"].value == "Failure mode":
            for c in ws[r]:
                c.fill = fill("DEEAF6")
    ws.append([])
    for line in ["grounding_score = highest evidence_score / 10 across every piece of evidence tagged with this risk: "
                 "Hammond et al. 2025 case studies and inventory incidents alike. evidence lists their ids, evidence_n counts them.",
                 "associations = linked risk factors (for a failure mode) or failure modes (for a risk factor). evidence_link is "
                 "line-aligned: TRUE if a piece of evidence is tagged with both ends, FALSE if the paper links them only in the text."]:
        ws.append([line])
        ws.merge_cells(start_row=ws.max_row, start_column=1, end_row=ws.max_row, end_column=9)
        c = ws.cell(ws.max_row, 1)
        c.font, c.alignment = BODY, Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[ws.max_row].height = 30

    # FM-RF Links
    ws = wb.create_sheet("FM-RF Links", 1)
    inst = lambda rid: NL.join(i["instance"] for i in instances if i["risk_id"] == rid)
    dirs = lambda rid: NL.join(d["direction"] for d in directions if d["risk_id"] == rid)
    rows = []
    for k, a in enumerate(assocs, 1):
        f, r = a["fm_id"], a["rf_id"]
        fm_ev, rf_ev = tagged(f), tagged(r)
        rows.append([k, name(f), name(r), a["basis"],
                     None, max_score(fm_ev) / 10, len(fm_ev),
                     None, amplifies(f, r), len(rf_ev),
                     inst(f), dirs(f), inst(r), dirs(r),
                     ", ".join(x["id"] for x in rf_ev) or "—", a["text_reference"] or "—"])
    H = ["#", "failure_mode", "risk_factor", "link_basis",
         "fm_strength", "fm_grounding", "fm_evidence_n",
         "rf_strength", "rf_grounding_amplifying", "rf_evidence_n",
         "fm_instances", "fm_directions", "rf_instances", "rf_directions",
         "rf_evidence", "text_reference"]
    L = table(ws, H, rows, [4, 15, 22, 20, 12, 12, 11, 12, 15, 11, 26, 34, 30, 34, 40, 44])
    for r in range(2, ws.max_row + 1):
        ws[f"{L['fm_strength']}{r}"] = strength(f"{L['fm_grounding']}{r}*10")
        ws[f"{L['rf_strength']}{r}"] = strength(f"{L['rf_grounding_amplifying']}{r}*10")
        for c in ws[r]:
            c.fill = fill(FM_FILL.get(ws[f"B{r}"].value, "FFFFFF"))
    for col in ("fm_grounding", "rf_grounding_amplifying"):
        center(ws, L[col], "0.00")
    center(ws, L["fm_evidence_n"])
    center(ws, L["rf_evidence_n"])
    ws.append([])
    ws.append(["Evidence attaches to a single-risk instance, never to a pair. A failure mode is grounded "
               "by its own evidence; rf_grounding_amplifying is the linked risk factor's grounding routed "
               "along an author-asserted link, not evidence that this factor produced this failure."])
    ws.cell(ws.max_row, 1).font = BODY
    ws.cell(ws.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=ws.max_row, start_column=1, end_row=ws.max_row, end_column=10)
    ws.row_dimensions[ws.max_row].height = 30

    # Taxonomy
    ws = wb.create_sheet("Taxonomy", 2)
    rows = []
    for r in risks:
        rid = r["risk_id"]
        ev = tagged(rid)
        rows.append([r["risk_type"], r["risk"], r["section"], r["definition"], inst(rid), dirs(rid),
                     NL.join(name(o) for o, _ in linked(rid)) or "—",
                     NL.join(f"{x['id']}: {short(x['title'])}" for x in ev) or "—", len(ev),
                     NL.join(x["source_class"] for x in ev) or "—", NL.join(x["type"] for x in ev) or "—",
                     None, f"={maxifs(fm=rid) if rid in FM else maxifs(rf=rid)}"])
    H = ["risk_type", "risk", "section", "definition", "instances", "directions", "linked_risks", "evidence",
         "evidence_n", "source_class", "type", "evidence_strength_max", "evidence_score_max"]
    L = table(ws, H, rows, [13, 22, 8, 44, 32, 40, 22, 52, 11, 24, 22, 13, 11])
    for r in range(2, ws.max_row + 1):
        ws[f"{L['evidence_strength_max']}{r}"] = strength(f"{L['evidence_score_max']}{r}")
        if ws[f"A{r}"].value == "Failure mode":
            for c in ws[r]:
                c.fill = fill(FM_FILL.get(ws[f"B{r}"].value, "FFFFFF"))
    center(ws, L["evidence_score_max"])
    center(ws, L["evidence_n"])

    # Instances
    ws = wb.create_sheet("Instances", 3)
    rows = []
    for i in instances:
        rr = R[i["risk_id"]]
        ev = [x for x in EVID if i["instance_id"] in ids(x.get("instances", ""))]
        best = max([escore(x) for x in ev if escore(x) is not None] or [0])
        rows.append([i["instance_id"], i["instance"], rr["risk"], rr["risk_type"], rr["section"],
                     i["provenance"], i["evidence_basis"],
                     ", ".join(x["id"] for x in ev) or "—", len(ev),
                     None, best / 10 if best else 0,
                     ", ".join(ids(i["case_studies_explicit"])) or "—",
                     ", ".join(ids(i["case_studies_placement"])) or "—",
                     i["key_references"] or "—", i["support_summary"] or "—"])
    H = ["instance_id", "instance", "parent_risk", "parent_risk_type", "section", "provenance",
         "evidence_basis", "evidence", "evidence_n", "evidence_strength_max", "instance_grounding",
         "paper_cross_ref_explicit", "paper_cross_ref_placement", "key_references", "support_summary"]
    L = table(ws, H, rows, [9, 30, 24, 14, 8, 15, 18, 26, 11, 13, 13, 16, 16, 36, 60])
    basis_fill = {"Case study": "E2EFDA", "Cited empirical work": "FFF2CC", "Theoretical": "F2F2F2",
                  "Incident evidence": "DEEAF6"}
    for r in range(2, ws.max_row + 1):
        ws[f"{L['evidence_basis']}{r}"].fill = fill(basis_fill[ws[f"{L['evidence_basis']}{r}"].value])
        ws[f"{L['evidence_strength_max']}{r}"] = strength(f"{L['instance_grounding']}{r}*10")
        if ws[f"{L['provenance']}{r}"].value == "Ours":
            ws[f"{L['provenance']}{r}"].fill = fill("FCE4D6")
    center(ws, L["evidence_n"])
    center(ws, L["instance_grounding"], "0.00")

    # Sources
    ws = wb.create_sheet("Sources", 5)
    table(ws, ["event_id", "title", "source_type", "url"],
          [[x["event_id"] or None, x["title"], x["source_type"], x["url"]] for x in sources],
          [15, 52, 26, 70], freeze="B2")
    for r in range(2, ws.max_row + 1):
        u = ws[f"D{r}"]
        u.hyperlink, u.font = u.value, Font(name="Arial", size=10, color="0563C1", underline="single")

    # Notes
    notes(wb.create_sheet("Notes"), [
        "SOURCE",
        "Hammond et al. (2025). Multi-Agent Risks from Advanced AI. Cooperative AI Foundation Technical Report #1. arXiv:2502.14143.",
        "Instances and directions: paper Table 1. Case-study tags and hammond_type: paper Table 3.",
        "",
        "METHOD",
        *NOTES_COMMON,
        "",
        "EVIDENCE SHEET",
        "One table for all evidence. evidence_class = Case study (Hammond et al. 2025 Table 3, shaded grey, CS ids) or "
        "Incident (the inventory, AIR/LW/AIV ids). Inclusion test for incidents: the behaviour arises from interaction "
        "between two or more AI agents, including one agent acting on another.",
        "id prefixes are listed in data/id_prefixes.csv. date: event date, or publication date for studies; partial dates "
        "show as yyyy or yyyy-mm. source_class: the source collection's own label, i.e. Hammond type for case studies, "
        "AIR class or main-source type for incidents.",
        "AIR class to type: In the wild and Safety failure -> Observed in real world; Research demo and Disclosed "
        "vulnerability -> Observed in lab.",
        "evidence_strength reads 'unscored' where E1-E5 are blank, i.e. rows held back pending a scope decision.",
        "The Sources sheet lists further sources per event; rows without event_id are leads not yet in the inventory. "
        "AIR asks users to contact Enkrypt AI before reusing its dataset.",
        "",
        "GROUNDING",
        "grounding_score and evidence_score_max = highest evidence_score across the whole evidence inventory tagged with "
        "that risk, case studies and incidents alike (0 = none). Max, not sum or mean: corroboration is already scored "
        "inside each row as E4, and summing would let many weak rows outrank one strong one.",
        "evidence_n counts the rows behind the score. A high grounding on evidence_n = 1 rests on a single piece of "
        "evidence; read the two together.",
        "Evidence tagged with a risk factor but no failure mode counts only towards that risk factor. Rows with blank "
        "E1-E5 are ignored by the score.",
        "Instances: evidence_explicit and evidence_placement hold Hammond case-study ids only. Incidents attach directly to "
        "failure modes and risk factors, not to instances, because Table 1's sub-topics are finer-grained than this "
        "project's scope. Instance-level evidence stays as the paper records it.",
        "case_studies_explicit = the paper cross-references the case study in that instance's paragraph; case_studies_placement = "
        "the case-study box sits in that instance's discussion without an explicit reference.",
        "evidence_basis: Case study / Cited empirical work (no case study, but empirical studies cited) / Theoretical.",
        "Formulas need a spreadsheet app to compute (Excel 2019+ or LibreOffice). out/risk_index.csv has the same values precomputed.",
    ])
    wb.active = 0
    wb.save(OUT / "multi_agent_risk_taxonomy.xlsx")


# ---------------------------------------------------------------- dashboard
WINDOW_START = "2025-04-01"   # first incident; every case study predates it
TIERS = TYPES[:3]             # real world, synthetic, lab


def risk_series(rid):
    """Pre-window baseline from the case studies, then a step per in-window event."""
    rows = sorted(tagged(rid), key=lambda x: parse_date(x["date"])[0])
    cut = parse_date(WINDOW_START)[0]
    pre = [x for x in rows if parse_date(x["date"])[0] < cut]
    win = [x for x in rows if parse_date(x["date"])[0] >= cut]
    base = max([escore(x) for x in pre if escore(x) is not None] or [0])
    n, best = len(pre), base
    pts = [dict(date=WINDOW_START, n=n, g=best / 10, id=None, tier=None, precision=3)]
    for x in win:
        n += 1
        sc = escore(x)
        if sc is not None:
            best = max(best, sc)
        pts.append(dict(date=x["date"], n=n, g=best / 10, id=x["id"], tier=x["type"],
                        precision=len(x["date"].split("-"))))
    return dict(baseline_n=len(pre), baseline_g=base / 10, points=pts)


def build_dashboard():
    # ---- evidence rows, with their instance links and the E1-E5 breakdown
    ev_rows = []
    for x in EVID:
        sc = escore(x)
        linked_i = [i for i in ids(x.get("instances", "")) if i in INST]
        ev_rows.append(dict(
            id=x["id"], cls=x["evidence_class"], date=x["date"],
            precision=len(x["date"].split("-")), type=x["type"], source_class=x["source_class"],
            instances=[dict(id=i, name=INST[i]["instance"], risk=INST[i]["risk_id"],
                            risk_name=name(INST[i]["risk_id"]),
                            kind=R[INST[i]["risk_id"]]["risk_type"],
                            provenance=INST[i]["provenance"]) for i in linked_i],
            fms=[name(y) for y in ids(x["failure_modes"])], fm_ids=ids(x["failure_modes"]),
            rfs=[name(y) for y in ids(x["risk_factors"])], rf_ids=ids(x["risk_factors"]),
            e=[None if x["e"][k] == "" else int(x["e"][k]) for k in range(5)],
            score=sc, band=band(sc) or "unscored", title=x["title"],
            notes=x.get("notes") or "", source=x["source"], url=x["source_url"]))

    # ---- risks
    risk_rows = []
    for r in risks:
        rid = r["risk_id"]
        ev = tagged(rid)
        by_tier = {t: len([x for x in ev if x["type"] == t]) for t in TIERS}
        top = max(ev, key=lambda x: escore(x) or -1) if ev else None
        used = sorted({i for x in ev for i in ids(x.get("instances", ""))
                       if i in INST and INST[i]["risk_id"] == rid}, key=lambda z: int(z[1:]))
        allinst = [i["instance_id"] for i in instances if i["risk_id"] == rid]
        # the same three magnitudes, recomputed per evidence tier, so a view can be filtered
        metrics = {}
        for t in ["all"] + TYPES:
            sub = ev if t == "all" else [x for x in ev if x["type"] == t]
            metrics[t] = dict(
                n=len(sub), grounding=max_score(sub) / 10,
                instances=len({i for x in sub for i in ids(x.get("instances", ""))
                               if i in INST and INST[i]["risk_id"] == rid}))
        risk_rows.append(dict(
            id=rid, risk=r["risk"], kind=r["risk_type"], section=r["section"],
            definition=r["definition"], grounding=max_score(ev) / 10, n=len(ev),
            band=band(max_score(ev)) if ev else "none", tiers=by_tier, metrics=metrics,
            tier_top=next((t for t in TIERS if by_tier[t]), None),
            top_id=top["id"] if top else None, top_score=escore(top) if top else None,
            instances_used=used, instances_total=len(allinst), series=risk_series(rid)))

    # ---- the RF -> FM relationship: failure modes stand on their own evidence,
    #      risk factors route their grounding into the ones the authors link them to
    flow = []
    for f in FM:
        inc = []
        for a in assocs:
            if a["fm_id"] != f:
                continue
            rf = a["rf_id"]
            inc.append(dict(rf=rf, rf_name=name(rf), basis=a["basis"],
                            grounding=max_score(tagged(rf)) / 10, n=len(tagged(rf)),
                            text_reference=a["text_reference"]))
        inc.sort(key=lambda z: -z["grounding"])
        flow.append(dict(fm=f, fm_name=name(f), own=max_score(tagged(f)) / 10,
                         own_n=len(tagged(f)), incoming=inc,
                         strongest=max([z["grounding"] for z in inc] or [0])))
    unlinked = [r for r in RF if not any(a["rf_id"] == r for a in assocs)]

    # ---- instance layer
    inst_rows = []
    for i in instances:
        ev = [x for x in EVID if i["instance_id"] in ids(x.get("instances", ""))]
        best = max([escore(x) for x in ev if escore(x) is not None] or [0])
        inst_rows.append(dict(
            id=i["instance_id"], name=i["instance"], risk=i["risk_id"],
            risk_name=name(i["risk_id"]), kind=R[i["risk_id"]]["risk_type"],
            provenance=i["provenance"], basis=i["evidence_basis"],
            evidence=[x["id"] for x in ev], n=len(ev),
            tiers={t: len([x for x in ev if x["type"] == t]) for t in TIERS},
            grounding=best / 10, summary=i["support_summary"]))

    routed = len([x for x in ev_rows if x["instances"]])
    payload = dict(
        latest=max(x["date"] for x in EVID), window_start=WINDOW_START,
        window_end=max(x["date"] for x in EVID), tiers=TIERS, all_types=TYPES,
        counts=dict(risks=len(risks), evidence=len(EVID), cases=len(cases),
                    incidents=len(incidents), links=len(assocs), instances=len(instances),
                    ours=len([i for i in instances if i["provenance"] == "Ours"])),
        risks=risk_rows, flow=flow, unlinked_rf=[dict(id=r, name=name(r)) for r in unlinked],
        instances=inst_rows, evidence=ev_rows,
        routing=dict(total=len(EVID), routed=routed, unrouted=len(EVID) - routed,
                     unrouted_ids=[x["id"] for x in ev_rows if not x["instances"]],
                     instances_used=len({i for x in ev_rows for i in [y["id"] for y in x["instances"]]}),
                     instances_total=len(instances)),
        e_labels=["E1 ecological validity", "E2 causal attribution", "E3 scale and precision",
                  "E4 independent corroboration", "E5 source vetting"],
        rubric=[["E1 ecological validity", "Real world", "Synthetic evidence", "Lab"],
                ["E2 causal attribution", "Controlled comparison isolating the multi-agent mechanism",
                 "Quasi-experimental, correlational or contributing factor", "Anecdotal or inferred"],
                ["E3 scale and precision", "Large n or multiple models/seeds, quantified effect",
                 "Small n, single model or few seeds", "Qualitative only"],
                ["E4 independent corroboration", "Two or more independent sources agree",
                 "One corroborating source", "None"],
                ["E5 source vetting", "Peer-reviewed or official investigation",
                 "Preprint, book, journalism, operator blog", "Unreviewed, incl. the report's own experiments"]],
        type_defs=[
            ["Observed in real world", "Deployed systems acting on real stakes, outside experimenter control"],
            ["Synthetic evidence", "Agents interacting in a simulated or researcher-built environment"],
            ["Observed in lab", "Controlled experiment on real models in a narrow task probe, no environment"],
            ["Theoretical", "Argument, formal model or non-AI analogue only (not scored)"]],
        sources=[[p["prefix"], p["source_collection"], p["description"]] for p in prefixes
                 if p["table"] == "incidents.csv"])

    tpl = (Path(__file__).parent / "dashboard_template.html").read_text(encoding="utf-8")
    assert "__DATA__" in tpl, "template lost its __DATA__ placeholder"
    (OUT / "dashboard.html").write_text(
        tpl.replace("__DATA__", json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":"))), encoding="utf-8")
    write_csv(OUT / "evidence.csv",
              ["id", "evidence_class", "date", "type", "source_class", "instances",
               "failure_modes", "risk_factors", *E_COLS, "evidence_score", "band",
               "source", "source_url", "title"],
              [[x["id"], x["cls"], x["date"], x["type"], x["source_class"],
                ";".join(y["id"] for y in x["instances"]),
                ";".join(x["fm_ids"]), ";".join(x["rf_ids"]), *x["e"],
                x["score"], x["band"], x["source"], x["url"], x["title"]] for x in ev_rows])
    write_csv(OUT / "instances.csv",
              ["instance_id", "instance", "risk_id", "risk", "risk_type", "provenance",
               "evidence_basis", "evidence", "evidence_n", "instance_grounding"],
              [[i["id"], i["name"], i["risk"], i["risk_name"], i["kind"], i["provenance"],
                i["basis"], ";".join(i["evidence"]), i["n"], i["grounding"]] for i in inst_rows])


build_taxonomy()
build_dashboard()
stale = OUT / "multi_agent_incident_inventory.xlsx"
if stale.exists():
    stale.unlink()
    print(f"removed {stale.relative_to(ROOT)}: merged into the Evidence sheet")
print(f"Built {len(risks)} risks, {len(instances)} instances, "
      f"{len(cases)} case studies + {len(incidents)} incidents = {len(cases) + len(incidents)} evidence rows "
      f"-> {OUT.relative_to(ROOT)}/")
