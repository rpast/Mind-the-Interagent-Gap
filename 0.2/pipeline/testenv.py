"""The test run: the real update routine, on made-up incidents, in a scratch folder.

`python 0.2/pipeline/run.py testrun` and the page's "Test run" both come here. A test
run walks the same UpdateRun steps, states, prompts and decisions as a real run. What
differs, and nothing else:

- It runs on a second instance of run.py, loaded under another module name and pointed
  at a fresh workspace from tempfile.mkdtemp. The real instance is never re-pointed, so
  nothing a test run does can reach the real tree, and a real run cannot be redirected.
  A test run keeps no log: its trace is shown while it runs and goes with it.
- `fetch` never touches the network: the "AIID" it sees is a sample of made-up records
  from 0.2/testenv/aiid/. With --refetch the first attempt fails on purpose.
- `manual` ingests the sample write-up in 0.2/testenv/manual/, through ingest_manual.
- Where a real run waits for /classify-incidents or for a person, answering Continue
  (Try again, on a failed check) puts the matching files from 0.2/testenv/standins/ in
  place, as that work would have. Skip puts nothing in place.

Everything else - normalise, prefilter, readiness, derive, instances-due, check, index,
viz - is the real code, running on the workspace. See 0.2/testenv/README.md.
"""
from __future__ import annotations

import importlib.util
import itertools
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REAL_TREE = HERE.parent
FIXTURES = REAL_TREE / "testenv"
STANDINS = FIXTURES / "standins"
PREFIX = "mig-testrun-"
# What the stages read besides the fixtures: the live taxonomy, so every id the
# fixtures use is checked against the one real list, and the docs and prompts the map
# links to. Copied, never linked: the workspace may be written to.
LIVE_COPIES = ("taxonomy", "docs", "prompts")
NEEDED = ("cases.json", "0.2/registry/sources.csv", "aiid/incidents.jsonl",
          "aiid/classifications.jsonl", "manual", "standins")

_names = itertools.count(1)


# ------------------------------------------------------------------ fixtures

def available():
    """(True, "") if the fixture tree is complete, else (False, why)."""
    missing = [p for p in NEEDED if not (FIXTURES / p).exists()]
    if missing:
        return False, ("the test fixtures are incomplete: missing "
                       + ", ".join(f"0.2/testenv/{p}" for p in missing))
    return True, ""


def cases():
    return json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))


def sample_size():
    with open(FIXTURES / "aiid" / "incidents.jsonl", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


# ----------------------------------------------------------------- workspace

def make_workspace():
    """A fresh scratch folder holding <ws>/0.2, the curator's write-ups beside it."""
    ok, why = available()
    if not ok:
        raise RuntimeError(why)
    ws = Path(tempfile.mkdtemp(prefix=PREFIX)).resolve()
    skip = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(FIXTURES / "0.2", ws / "0.2", ignore=skip)
    for name in LIVE_COPIES:
        shutil.copytree(REAL_TREE / name, ws / "0.2" / name, ignore=skip,
                        dirs_exist_ok=True)
    # the saved snapshot a real tree keeps in raw/aiid/, here the made-up sample
    shutil.copytree(FIXTURES / "aiid", ws / "0.2" / "raw" / "aiid", ignore=skip)
    shutil.copytree(FIXTURES / "manual", ws / "writeups", ignore=skip)
    return ws


def is_workspace(path):
    """A folder this module made: named mig-testrun-*, in the temp dir, not the repo."""
    p = Path(path).resolve()
    return (p.name.startswith(PREFIX) and p.parent == Path(tempfile.gettempdir()).resolve()
            and not p.is_relative_to(REAL_TREE.parent))


def remove_workspace(path):
    if path and is_workspace(path):
        shutil.rmtree(path, ignore_errors=True)


def load_instance(real_rm, ws):
    """A second, private instance of run.py, pointed at <ws>/0.2. Not put in
    sys.modules: nothing else can import it, and it is dropped with its run."""
    spec = importlib.util.spec_from_file_location(f"mig_testrun_{next(_names)}",
                                                  real_rm.__file__)
    rm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rm)
    rm.set_paths(Path(ws) / "0.2")
    guard(rm, ws)
    return rm


def guard(rm, ws):
    """Refuse unless every path of the instance is inside the scratch workspace."""
    ws = Path(ws).resolve()
    if not is_workspace(ws):
        raise RuntimeError(f"refusing to run a test in {ws}: not a scratch workspace")
    if Path(rm.TREE).resolve() == REAL_TREE:
        raise RuntimeError("refusing to run a test on the real 0.2/ tree")
    for name in rm.PATH_NAMES:
        p = Path(getattr(rm, name)).resolve()
        if not p.is_relative_to(ws):
            raise RuntimeError(f"refusing to run a test: {name} is {p}, outside {ws}")


# ----------------------------------------------------------------- stand-ins
#
# What /classify-incidents or a person would have written between steps. Each stand-in
# puts in place only what that work could have produced from the workspace as it now
# is: no reading for a record that is not queued, no proposal for a record that cannot
# be judged, no dossier for a record nobody proposed. So a skipped step has its real
# consequence downstream.

def _key(row):
    """(source_id, source_record_id): from record_key when the row has one."""
    if row.get("record_key"):
        sid, rid = str(row["record_key"]).split(":", 1)
        return sid, rid
    return row["source_id"], str(row["source_record_id"])


def _append_rows(rm, src, dest, keep):
    rows = rm.read_jsonl(src)
    take = [r for r in rows if keep(_key(r))]
    if take:
        rm.write_jsonl(dest, rm.read_jsonl(dest) + take)
    return take, len(rows) - len(take)


def standin_read(rm, run):
    queued = {_key(r) for r in rm.read_queue()}
    have = set(rm.load_context())
    for src in sorted((STANDINS / "read" / "context").glob("*.jsonl")):
        dest = rm.CONTEXT / src.name
        take, left = _append_rows(rm, src, dest,
                                  lambda k: k in queued and k not in have)
        rm.info(f"  test  put {len(take)} sample reading(s) in place in "
                f"{dest.relative_to(rm.ROOT)}, as /classify-incidents would have")
        for r in take:
            rm.info("          {}:{}".format(*_key(r)))
        if left:
            rm.info(f"  test  left out {left}: not queued, or already read")


def standin_judge(rm, run):
    judgeable = set(run.judgeable())
    for src in sorted((STANDINS / "judge" / "proposals").glob("*.jsonl")):
        # the skill names its files by run date: extract_gate.<YYYY-MM-DD>.jsonl
        dest = rm.PROPOSALS / f"{src.stem}.{rm.TODAY}.jsonl"
        done = {_key(r) for r in rm.read_jsonl(dest)}
        take, left = _append_rows(rm, src, dest,
                                  lambda k: k in judgeable and k not in done)
        rm.info(f"  test  put {len(take)} sample proposal(s) in place in "
                f"{dest.relative_to(rm.ROOT)}, as /classify-incidents would have")
        for r in take:
            rm.info("          {}:{}".format(*_key(r)))
        if left:
            rm.info(f"  test  left out {left}: their records cannot be judged yet")


def fill_sheet(rm, kind, answers):
    """Fill in a generated review sheet the way a person would: open the workbook the
    run wrote, type into the decision and note columns of the rows the answers name,
    save it. Returns the keys filled in."""
    cfg = rm.SHEETS[kind]
    path = rm.REVIEW / cfg["file"]
    if not path.exists():
        return []
    wb = rm.openpyxl.load_workbook(path)
    ws = wb[cfg["title"]]
    head = {c.value: i for i, c in enumerate(ws[1], 1)}
    # The answers name records by record_key; the sheet shows each by its MIG key.
    by_pair, _ = rm.mig_index()
    by_key = {by_pair.get(rm.split_key(a["record_key"])): a for a in answers}
    done = []
    for r in range(2, ws.max_row + 1):
        a = by_key.get(str(ws.cell(r, head["mig_key"]).value))
        if a is None:
            continue
        ws.cell(r, head[cfg["field"]]).value = a["decision"]
        ws.cell(r, head[cfg["text"]]).value = a.get("reason") or a.get("note") or ""
        done.append(f"{a['record_key']} ({ws.cell(r, head['mig_key']).value})")
    wb.save(path)
    return done


def standin_review(rm, run):
    """A person at the review step, with the real sheets: fill sheet 1, let the run read
    it (which writes sheet 2), fill sheet 2, let the run read that (which makes the
    dossiers), then fill in each blank dossier from the sample."""
    if rm.openpyxl is None:
        rm.info(f"  test  {rm.OPENPYXL_HINT}: the sheets cannot be filled in, so no "
                f"decision is made")
        return
    answers = json.loads((STANDINS / "review" / "decisions.json").read_text(encoding="utf-8"))
    for kind, after in (("scope", "decide scope: read sheet 1, write sheet 2"),
                        ("promote", "promote: read sheet 2, make the dossiers")):
        done = fill_sheet(rm, kind, answers[kind])
        rm.info(f"  test  filled in {rm.SHEETS[kind]['file']} for {len(done)} record(s), "
                f"as a person would have: {', '.join(done) or 'none listed'}")
        rm.info(f"  test  now the run reads it ({after})")
        rm.stage_review()
    put = left = 0
    for src in sorted((STANDINS / "review" / "incidents").glob("*.md")):
        dest = rm.INCIDENTS / src.name
        meta, _ = rm.read_dossier(src)
        # only over the blank dossier of the same record: the MIG key a record gets
        # depends on which records the run reached, so a name alone is not enough
        if not dest.exists() or rm.canonical_pair(meta) is None \
                or rm.canonical_pair(rm.read_dossier(dest)[0]) != rm.canonical_pair(meta):
            left += 1
            continue
        shutil.copyfile(src, dest)
        put += 1
        rm.info(f"  test  put the filled-in {dest.relative_to(rm.ROOT)} over the blank "
                f"dossier the promote step made, as a person filling it in would have")
    if not put:
        rm.info("  test  no blank dossier was made, so none was filled in")
    if left:
        rm.info(f"  test  left out {left} sample dossier(s): no promote decision made them")
    if put and answers.get("edit"):
        rm.info("  test  now the run writes sheet 3 again, from the filled-in dossiers")
        rm.stage_review()
        # one round per run of the review step: a person edits, the run reads it
        for n, round_ in enumerate(answers["edit"], 1):
            done = fill_edit_sheet(rm, round_)
            rm.info(f"  test  edit round {n}: changed {rm.EDIT['file']} for "
                    f"{len(done)} dossier(s), as a person would have: "
                    f"{', '.join(done) or 'none listed'}")
            rm.info("  test  now the run reads it (edit dossiers: write the changed "
                    "fields)")
            rm.stage_review()


def fill_edit_sheet(rm, answers):
    """Change cells of sheet 3 the way a person would. `answers` is a list of
    {"id", "set": {column: text}}. Returns the dossier ids changed."""
    path = rm.REVIEW / rm.EDIT["file"]
    if not path.exists():
        return []
    wb = rm.openpyxl.load_workbook(path)
    ws = wb[rm.EDIT["title"]]
    head = {c.value: i for i, c in enumerate(ws[1], 1)}
    by_id = {a["mig_key"]: a["set"] for a in answers}
    done = []
    for r in range(2, ws.max_row + 1):
        cells = by_id.get(str(ws.cell(r, head["mig_key"]).value))
        if cells is None:
            continue
        for col, text in cells.items():
            ws.cell(r, head[col]).value = text
        done.append(str(ws.cell(r, head["mig_key"]).value))
    wb.save(path)
    return done


def standin_check(rm, run):
    fixed = 0
    for src in sorted((STANDINS / "check" / "incidents").glob("*.md")):
        dest = rm.INCIDENTS / src.name
        if not dest.exists():
            continue
        if dest.read_bytes() == src.read_bytes():
            continue
        shutil.copyfile(src, dest)
        fixed += 1
        rm.info(f"  test  put the corrected {dest.relative_to(rm.ROOT)} in place, as a "
                f"person fixing it would have")
    if not fixed:
        rm.info("  test  no corrected dossier applies; the check runs again as it is")


STANDIN = {("read", "continue"): standin_read, ("judge", "continue"): standin_judge,
           ("review", "continue"): standin_review, ("check", "retry"): standin_check}

TEST_NOTES = {
    ("fetch", "failed"): "In this test run the first fetch fails on purpose: Try again "
                         "fetches the made-up sample, and Use the snapshot carries on with "
                         "the sample snapshot already in the workspace.",
    ("read", "waiting"): "In this test run, Continue puts the sample readings in place, as "
                         "/classify-incidents would have, and counts again; Skip leaves "
                         "the records unread.",
    ("judge", "waiting"): "In this test run, Continue puts the sample proposals in place "
                          "for the records that can be judged, as /classify-incidents "
                          "would have.",
    ("review", "waiting"): "In this test run, Continue fills in the two generated sheets "
                           "as a person would (scope: one in, one out, one wrong value; "
                           "promote: yes), lets the run read them, and puts the filled-in "
                           "sample dossiers over the blank ones; one of them has a "
                           "deliberate fault for the check to catch.",
    ("check", "failed"): "In this test run, Try again puts the corrected dossier in "
                         "place, as a person fixing it would, and runs the check again.",
}
# What Continue (or Try again) would put in place, under 0.2/testenv/standins/: the
# waiting card links it, so the sample work can be read before choosing.
TEST_PEEK = {("read", "waiting"): "read/context",
             ("judge", "waiting"): "judge/proposals",
             ("review", "waiting"): "review/incidents",
             ("check", "failed"): "check/incidents"}
DEFAULT_NOTE = ("In this test run, Try again runs the step again on the scratch "
                "workspace; nothing outside it is touched.")


# ------------------------------------------------------------------- the run

def testrun_class(rm):
    """TestRun, built on the given instance's UpdateRun, so the inherited steps read
    and write that instance's paths: the workspace's."""

    class TestRun(rm.UpdateRun):
        def __init__(self, workspace, discover=False, refetch=False, manual=False,
                     wait=None, on_change=None):
            guard(rm, workspace)
            super().__init__(discover=discover, refetch=refetch, wait=wait,
                             on_change=on_change)
            self.workspace = Path(workspace).resolve()
            self.options = {"discover": bool(discover), "refetch": bool(refetch),
                            "manual": bool(manual)}
            self.fetch_attempts = 0
            self.data.update(test=True, options=dict(self.options),
                             workspace=str(self.workspace), cases=cases())

        def prompt_for(self, step, outcome):
            prompt = super().prompt_for(step, outcome)
            prompt["test_note"] = TEST_NOTES.get((step["id"], outcome.state), DEFAULT_NOTE)
            peek = TEST_PEEK.get((step["id"], outcome.state))
            if peek and (STANDINS / peek).exists():
                prompt["test_peek"] = {"label": "See the sample work",
                                       "path": str((STANDINS / peek).relative_to(REAL_TREE))}
            return prompt

        def answered(self, step, action):
            fn = STANDIN.get((step["id"], action))
            if fn is not None:
                fn(rm, self)

        def save_log(self):
            """A test run keeps no log: only real runs go into the run history."""

        def step_fetch(self, step, override):
            target = rm.RAW / "aiid"
            rm.info(f"  note  test run: AIID is never contacted. The 'AIID' here is a "
                    f"sample of {sample_size()} made-up records from 0.2/testenv/aiid/, "
                    f"not AIID.")
            refetch = self.options["refetch"] and override != "use_snapshot"
            if override == "use_snapshot":
                rm.info("  note  using the snapshot already on disk")
            done = []
            if refetch or not (target / "incidents.jsonl").exists():
                self.fetch_attempts += 1
                if refetch and self.fetch_attempts == 1:
                    rm.info("  FAIL  fetch: test run: the first fetch fails on purpose")
                    raise rm.StepOutcome("failed", rm.FETCH_FAILED,
                                         actions=("retry", "use_snapshot"))
                put_sample(rm, target)
                done.append("aiid")
                rm.info("  ok    aiid: fetched")
            else:
                n = rm.aiid_snapshot()["records"]
                rm.info(f"  skip  aiid: snapshot present ({n} records); "
                        f"--refetch to fetch again")
            self.count(step, "Fetched now", len(done))
            self.count(step, "AIID records in the snapshot",
                       rm.aiid_snapshot()["records"])

        def step_manual(self, step, _o):
            if not self.options["manual"]:
                rm.info("  skip  manual: not asked for; the sample write-up is left out")
                raise rm.StepOutcome("skipped")
            rm.info("  note  test run: the write-up is a made-up sample from "
                    "0.2/testenv/manual/")
            files, incidents = rm.ingest_manual(self.workspace / "writeups")
            self.count(step, "Files", files)
            self.count(step, "Incidents", incidents)

    return TestRun


def put_sample(rm, target):
    """Write the sample where the real fetch writes AIID, in the same format."""
    target.mkdir(parents=True, exist_ok=True)
    for name in ("incidents", "classifications"):
        shutil.copyfile(FIXTURES / "aiid" / f"{name}.jsonl", target / f"{name}.jsonl")
        n = len(rm.read_jsonl(target / f"{name}.jsonl"))
        rm.info(f"  ok    aiid/{name}: {n} records")
    (target / "FETCHED.md").write_text(
        f"# AIID snapshot\n\nFetched {rm.TODAY} by the test run: a sample of made-up "
        f"records from 0.2/testenv/aiid/, not AIID.\n", encoding="utf-8")


def start(real_rm, discover=False, refetch=False, manual=False, wait=None,
          on_change=None):
    """A new workspace, a new instance pointed at it, and a TestRun on that instance.
    Returns (run, workspace). The caller runs it and removes the workspace later."""
    ws = make_workspace()
    try:
        rm = load_instance(real_rm, ws)
        run = testrun_class(rm)(ws, discover=discover, refetch=refetch, manual=manual,
                                wait=wait, on_change=on_change)
    except BaseException:
        remove_workspace(ws)
        raise
    return run, ws


# ----------------------------------------------------------------------- cli

def cli(real_rm, discover=False, refetch=False, manual=False, skip=()):
    """Run a whole test run without a person: every prompt gets its first action
    (continue, retry), or `skip` at the steps named. 0 only if the run ends done."""
    ok, why = available()
    if not ok:
        print(f"error: {why}", file=sys.stderr)
        return 2
    ids = [sid for sid, _t, _n in real_rm.STEPS]
    bad = [s for s in skip if s not in ids]
    if bad:
        print(f"error: --skip {' '.join(bad)}: no such step; the steps are "
              f"{', '.join(ids)}", file=sys.stderr)
        return 2
    answers = {}

    def wait(run, step):
        prompt = step["prompt"] or {}
        actions = [a["id"] for a in prompt.get("actions") or []]
        answers[step["id"]] = answers.get(step["id"], 0) + 1
        if answers[step["id"]] > 3:          # a stand-in that does not settle it
            action = "cancel"
        elif step["id"] in skip and "skip" in actions:
            action = "skip"
        else:
            action = actions[0] if actions else "cancel"
        print(f"  wait  {prompt.get('text', '')}", file=sys.stderr)
        print(f"  test  {prompt.get('test_note', '')}", file=sys.stderr)
        print(f"  ->    {action}", file=sys.stderr)
        return action

    run, ws = start(real_rm, discover=discover, refetch=refetch, manual=manual,
                    wait=wait)
    opts = [o for o, on in (("--discover", discover), ("--refetch", refetch),
                            ("--manual", manual)) if on]
    opts += [f"--skip {s}" for s in skip]
    print(f"testrun {' '.join(opts)}".rstrip() + f": made-up incidents in {ws}",
          file=sys.stderr)
    state = run.run()
    snap = run.snapshot()
    print("", file=sys.stderr)
    print("steps:", file=sys.stderr)
    for s in snap["steps"]:
        counts = ", ".join(f"{label} {n}" for label, n in s["counts"])
        print(f"  {s['id']:10s} {s['state']:11s} {counts}", file=sys.stderr)
    print(f"{state}.", file=sys.stderr)
    print(f"workspace: {ws}", file=sys.stderr)
    return 0 if state == "done" else 1
