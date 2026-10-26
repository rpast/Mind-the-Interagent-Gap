#!/usr/bin/env python3
"""Build the Mind the Interagent Gap outputs from data/*.csv.

Outputs (in out/):
  multi_agent_risk_taxonomy.xlsx  risk index, FM-RF links, taxonomy, instances, evidence, sources
  risk_index.csv                  flat FM/RF index with grounding scores (for pipelines)
  associations.csv                FM-RF links with case_study_link and grounding

The Evidence sheet is the single table of evidence: Hammond case studies and inventory incidents
together, told apart by evidence_class. Grounding formulas count evidence_class = "Case study"
only; see OPEN.md item 3.

Usage:  python build/build_xlsx.py
The taxonomy workbook uses live formulas; Excel/LibreOffice compute them on open.
The CSV outputs hold the same scores computed in Python.
"""
import csv
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

R = {r["risk_id"]: r for r in risks}
FM = [r["risk_id"] for r in risks if r["risk_type"] == "Failure mode"]
RF = [r["risk_id"] for r in risks if r["risk_type"] == "Risk factor"]
CS = {c["case_study_id"]: c for c in cases}
name = lambda rid: R[rid]["risk"]


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
        if has_cs != (row["evidence_basis"] == "Case study"):
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
    for c in cases:  # every FM x RF co-tag must be a recorded association
        for f in ids(c["failure_modes"]):
            for r in ids(c["risk_factors"]):
                if (f, r) not in pairs:
                    err.append(f"{c['case_study_id']} tags {f}+{r} but associations.csv lacks that pair")
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


# ---------------------------------------------------------------- derived values
def tagged(rid):
    col = "failure_modes" if rid in FM else "risk_factors"
    return [c for c in cases if rid in ids(c[col])]


def both(fm, rf):
    return [c for c in cases if fm in ids(c["failure_modes"]) and rf in ids(c["risk_factors"])]


def max_score(cs_list):
    s = [score(c) for c in cs_list]
    return max(s) if s else 0


def linked(rid):
    if rid in FM:
        return [(a["rf_id"], a) for a in assocs if a["fm_id"] == rid]
    return [(a["fm_id"], a) for a in assocs if a["rf_id"] == rid]


def link_flag(a):
    return bool(both(a["fm_id"], a["rf_id"]))


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


OUT.mkdir(exist_ok=True)
write_csv(OUT / "risk_index.csv",
          ["risk_id", "risk", "risk_type", "section", "grounding_score", "case_studies", "associations", "case_study_link"],
          [[r["risk_id"], r["risk"], r["risk_type"], r["section"], max_score(tagged(r["risk_id"])) / 10,
            ";".join(c["case_study_id"] for c in tagged(r["risk_id"])),
            ";".join(o for o, _ in linked(r["risk_id"])),
            ";".join(str(link_flag(a)).upper() for _, a in linked(r["risk_id"]))] for r in risks])
write_csv(OUT / "associations.csv",
          ["fm_id", "failure_mode", "rf_id", "risk_factor", "case_study_link", "case_studies", "fm_grounding", "rf_grounding"],
          [[a["fm_id"], name(a["fm_id"]), a["rf_id"], name(a["rf_id"]), str(link_flag(a)).upper(),
            ";".join(c["case_study_id"] for c in both(a["fm_id"], a["rf_id"])),
            max_score(tagged(a["fm_id"])) / 10, max_score(tagged(a["rf_id"])) / 10] for a in assocs])


# ---------------------------------------------------------------- evidence rows
CASE_CLASS, INCIDENT_CLASS = "Case study", "Incident"


def evidence_rows():
    """Hammond case studies and inventory incidents as one list of dicts, cases first."""
    out = []
    for c in cases:
        out.append(dict(
            id=c["case_study_id"], evidence_class=CASE_CLASS, title=c["title"], date=c["date"],
            type=c["type"], source_class=c["hammond_type"], system=None, system_basis=c["system_basis"],
            harm=c["harm"], failure_modes=c["failure_modes"], risk_factors=c["risk_factors"],
            e=[c[e] for e in E_COLS],
            notes=" ".join(x for x in [c["scoring_note"], c["type_note"]] if x) or None,
            page=int(c["page"]), source=c["source"], source_url=REPORT_URL,
            retrieved_on=date(2026, 10, 25), summary=c["summary"]))
    for i in sorted(incidents, key=lambda i: parse_date(i["date"])[0], reverse=True):
        out.append(dict(
            id=i["event_id"], evidence_class=INCIDENT_CLASS, title=i["incident"], date=i["date"],
            type=i["type"], source_class=i["source_class"], system=i["system"] or None,
            system_basis=i["system_basis"] or None, harm=i["harm"], failure_modes=i["failure_modes"],
            risk_factors=i["risk_factors"], e=[i[e] for e in E_COLS], notes=i["notes"] or None,
            page=None, source=i["source"], source_url=i["source_url"],
            retrieved_on=date.fromisoformat(i["retrieved_on"]), summary=None))
    return out


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

    def maxifs(fm=None, rf=None, evidence_class=CASE_CLASS):
        """Grounding counts case studies only by default; pass evidence_class=None to count every row."""
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
        rows.append([rid, r["risk"], r["risk_type"], r["section"], f"={g}/10",
                     ", ".join(c["case_study_id"] for c in tagged(rid)) or "—",
                     NL.join(name(o) for o, _ in lk) or "—",
                     NL.join(str(link_flag(a)).upper() for _, a in lk) or "—"])
    L = table(ws, ["risk_id", "risk", "risk_type", "section", "grounding_score", "case_studies", "associations",
                   "case_study_link"], rows, [8, 26, 14, 8, 15, 26, 26, 15])
    center(ws, L["grounding_score"], "0.00")
    center(ws, L["case_study_link"])
    for r in range(2, ws.max_row + 1):
        if ws[f"C{r}"].value == "Failure mode":
            for c in ws[r]:
                c.fill = fill("DEEAF6")
    ws.append([])
    for line in ["grounding_score = highest evidence_score / 10 among case studies tagged with this risk (Hammond et al. 2025, Table 3).",
                 "associations = linked risk factors (for a failure mode) or failure modes (for a risk factor). case_study_link is "
                 "line-aligned: TRUE if a case study is tagged with both ends, FALSE if the paper links them only in the text."]:
        ws.append([line])
        ws.merge_cells(start_row=ws.max_row, start_column=1, end_row=ws.max_row, end_column=8)
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
        cs = both(f, r)
        basis = ("Case study + text" if cs and a["text_reference"] else "Case study" if cs else "Text cross-reference only")
        rows.append([k, name(f), name(r), str(bool(cs)).upper(), basis, inst(f), dirs(f), inst(r), dirs(r),
                     NL.join(f"{c['case_study_id']}: {c['title']}" for c in cs) or "—",
                     NL.join(c["hammond_type"] for c in cs) or "—", NL.join(c["type"] for c in cs) or "—",
                     None, f"={maxifs(f, r)}", NL.join(c["source"] for c in cs) or "—", a["text_reference"] or "—"])
    H = ["#", "failure_mode", "risk_factor", "case_study_link", "link_basis", "fm_instances", "fm_directions",
         "rf_instances", "rf_directions", "case_studies_tagged_both", "hammond_type", "type",
         "evidence_strength_max", "evidence_score_max", "case_study_source", "text_reference"]
    L = table(ws, H, rows, [4, 15, 22, 11, 18, 26, 34, 30, 34, 36, 22, 20, 13, 11, 28, 44])
    for r in range(2, ws.max_row + 1):
        ws[f"{L['evidence_strength_max']}{r}"] = strength(f"{L['evidence_score_max']}{r}")
        for c in ws[r]:
            c.fill = fill(FM_FILL.get(ws[f"B{r}"].value, "FFFFFF"))
    center(ws, L["evidence_score_max"])
    center(ws, L["case_study_link"])

    # Taxonomy
    ws = wb.create_sheet("Taxonomy", 2)
    rows = []
    for r in risks:
        rid = r["risk_id"]
        cs = tagged(rid)
        rows.append([r["risk_type"], r["risk"], r["section"], r["definition"], inst(rid), dirs(rid),
                     NL.join(name(o) for o, _ in linked(rid)) or "—",
                     NL.join(f"{c['case_study_id']}: {c['title']}" for c in cs) or "—",
                     NL.join(c["hammond_type"] for c in cs) or "—", NL.join(c["type"] for c in cs) or "—",
                     None, f"={maxifs(fm=rid) if rid in FM else maxifs(rf=rid)}"])
    H = ["risk_type", "risk", "section", "definition", "instances", "directions", "linked_risks", "case_studies",
         "hammond_type", "type", "evidence_strength_max", "evidence_score_max"]
    L = table(ws, H, rows, [13, 22, 8, 44, 32, 40, 22, 44, 30, 22, 13, 11])
    for r in range(2, ws.max_row + 1):
        ws[f"{L['evidence_strength_max']}{r}"] = strength(f"{L['evidence_score_max']}{r}")
        if ws[f"A{r}"].value == "Failure mode":
            for c in ws[r]:
                c.fill = fill(FM_FILL.get(ws[f"B{r}"].value, "FFFFFF"))
    center(ws, L["evidence_score_max"])

    # Instances
    ws = wb.create_sheet("Instances", 3)
    rows = []
    for i in instances:
        linked_cs = ids(i["case_studies_explicit"]) + ids(i["case_studies_placement"])
        f = ("=MAX(" + ",".join(f'INDEX({SC},MATCH("{c}",{IDR},0))' for c in linked_cs) + ")") if linked_cs else None
        rr = R[i["risk_id"]]
        rows.append([i["instance_id"], i["instance"], rr["risk"], rr["risk_type"], rr["section"],
                     ", ".join(ids(i["case_studies_explicit"])) or "—", ", ".join(ids(i["case_studies_placement"])) or "—",
                     i["evidence_basis"], f, i["key_references"] or "—", i["support_summary"] or "—"])
    H = ["instance_id", "instance", "parent_risk", "parent_risk_type", "section", "case_studies_explicit",
         "case_studies_placement", "evidence_basis", "evidence_score_max", "key_references", "support_summary"]
    L = table(ws, H, rows, [9, 30, 24, 14, 8, 16, 16, 20, 12, 36, 60])
    basis_fill = {"Case study": "E2EFDA", "Cited empirical work": "FFF2CC", "Theoretical": "F2F2F2"}
    for r in range(2, ws.max_row + 1):
        ws[f"{L['evidence_basis']}{r}"].fill = fill(basis_fill[ws[f"{L['evidence_basis']}{r}"].value])
    center(ws, L["evidence_score_max"])

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
        "grounding_score and evidence_score_max = highest evidence_score among the relevant rows with "
        "evidence_class = 'Case study' (0 = none). Scored incidents sit in the same sheet but are deliberately left out "
        "of grounding; that is the open decision in OPEN.md item 3. To fold them in, drop the evidence_class criterion "
        "from maxifs() in build/build_xlsx.py.",
        "Case studies tagged with a risk factor but no failure mode (CS7, CS8, CS10, CS12, CS13) count only towards that risk factor.",
        "case_studies_explicit = the paper cross-references the case study in that instance's paragraph; case_studies_placement = "
        "the case-study box sits in that instance's discussion without an explicit reference.",
        "evidence_basis: Case study / Cited empirical work (no case study, but empirical studies cited) / Theoretical.",
        "Formulas need a spreadsheet app to compute (Excel 2019+ or LibreOffice). out/risk_index.csv has the same values precomputed.",
    ])
    wb.active = 0
    wb.save(OUT / "multi_agent_risk_taxonomy.xlsx")


build_taxonomy()
stale = OUT / "multi_agent_incident_inventory.xlsx"
if stale.exists():
    stale.unlink()
    print(f"removed {stale.relative_to(ROOT)}: merged into the Evidence sheet")
print(f"Built {len(risks)} risks, {len(instances)} instances, "
      f"{len(cases)} case studies + {len(incidents)} incidents = {len(cases) + len(incidents)} evidence rows "
      f"-> {OUT.relative_to(ROOT)}/")
