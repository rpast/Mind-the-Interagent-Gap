"""The front end of the update routine: `python mvp/pipeline/run.py serve`.

Serves the dataflow map (pipeline_patch.html) on http://127.0.0.1:<port>/ with live
data, and runs `update` step by step on a background thread, waiting for the person
wherever a step needs one. The steps are run.py's UpdateRun, the same code the
command line runs; only the waiting differs.

It also runs test runs: `POST /api/run` with `"test": true` walks the same steps on
the made-up incidents of mvp/testenv/, in a scratch workspace, through a second
instance of run.py pointed at that workspace (testenv.py). The real instance is never
re-pointed. A test run is persisted only inside its workspace, never to the real
state/run.json, so after a restart only real runs are remembered. Each new test run
removes the previous one's workspace; stopping the server removes the last one.

Endpoints:
    GET  /                 the map, with the real tree's numbers
    GET  /api/status       server, current run, AIID snapshot, token, test_available
    GET  /api/run          the current run, test or real
    POST /api/run          start: {"discover","refetch","manual_dir"} or
                           {"test": true, "discover", "refetch", "manual"}
    POST /api/run/signal   {"step", "action"}: answer a waiting step
    POST /api/run/cancel
    POST /api/open         {"path"} under mvp/, or {"path", "test": true} under the
                           test workspace's mvp/, where "." is that folder itself

Safety: binds 127.0.0.1 only; refuses any request whose Host is not this server;
refuses a POST whose Origin is foreign or whose body is not JSON. Nothing a request
says is ever run as a command; the one thing a request can launch is the desktop's
opener (xdg-open) on a data file or folder under mvp/, or under the current test
workspace's mvp/. Only one run, test or real, is active at a time. Standard library
only.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

MAX_BODY = 64 * 1024
# What "where it is kept" may open, besides folders: the kinds of file the map points at.
OPEN_SUFFIXES = {".csv", ".json", ".jsonl", ".md", ".txt", ".html", ".pdf", ".py"}


def _testenv(rm):
    sys.path.insert(0, str(Path(rm.__file__).resolve().parent))
    import testenv
    return testenv


class Runner:
    """Holds the one run that may be active, and persists it: a real run to
    state/run.json, a test run inside its own workspace."""

    def __init__(self, rm, token_file=None):
        self.rm = rm
        self.token_file = token_file
        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)
        self.run = None            # the UpdateRun or TestRun of this server's lifetime
        self.thread = None
        self.signal = None         # (step id, action id) sent by the page
        self.workspace = None      # the current test run's scratch folder
        self.last = self._load()   # a real run left by an earlier server, or None

    # -- persistence -------------------------------------------------------
    def _load(self):
        path = self.rm.RUN_FILE
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if data.get("test"):       # never written there; ignore it if it ever is
            return None
        data.setdefault("test", False)
        # No thread survives a restart: a run that was still going is over.
        if data.get("state") in ("running", "waiting") or any(
                s.get("prompt") for s in data.get("steps") or []):
            if data.get("state") in ("running", "waiting"):
                data["state"] = "cancelled"
            for s in data.get("steps") or []:
                if s.get("state") in ("running", "waiting"):
                    s["state"] = "skipped"
                    s.setdefault("log", []).append(
                        "  note  the server stopped during this step; run abandoned")
                s["prompt"] = None
            self._write(data, path)
        return data

    def _write(self, data, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        os.replace(tmp, path)

    def persist(self, run):
        """A run is kept where its own module instance keeps runs. A test run's
        must land in its workspace; anything else is not written at all."""
        path = Path(run.run_file()).resolve()
        snap = run.snapshot()
        if snap.get("test"):
            ws = Path(snap.get("workspace") or "/nonexistent").resolve()
            if not path.is_relative_to(ws) or path == Path(self.rm.RUN_FILE).resolve():
                return
        with self.lock:
            self._write(snap, path)

    # -- the run -----------------------------------------------------------
    def active(self):
        return self.thread is not None and self.thread.is_alive()

    def current(self):
        with self.lock:
            if self.run is not None:
                return self.run.snapshot()
            return self.last

    def start(self, discover, refetch, manual_dir="", test=False, manual=False):
        with self.lock:
            if self.active():
                return None
            self.signal = None
            if test:
                te = _testenv(self.rm)
                old, self.workspace = self.workspace, None
                te.remove_workspace(old)
                self.run, self.workspace = te.start(
                    self.rm, discover=discover, refetch=refetch, manual=manual,
                    wait=self.wait, on_change=self.persist)
            else:
                self.run = self.rm.UpdateRun(discover=discover, refetch=refetch,
                                             manual_dir=manual_dir,
                                             token_file=self.token_file,
                                             wait=self.wait, on_change=self.persist)
            self.persist(self.run)
            self.thread = threading.Thread(target=self._go, args=(self.run,),
                                           name="update-run", daemon=True)
            self.thread.start()
            return self.run.snapshot()

    def _go(self, run):
        try:
            run.run()
        except BaseException as e:   # noqa: BLE001 - nothing may take the server down
            with run.lock:
                run.data["state"] = "failed"
                step = run.step(run.data["current"]) if run.data["current"] else None
                if step is not None:
                    step["state"] = "failed"
                    step["log"].append(f"  FAIL  the runner stopped: {e!r}")
            self.persist(run)

    def wait(self, run, step):
        """Called on the run's thread: block until the page answers this step."""
        allowed = {a["id"] for a in (step.get("prompt") or {}).get("actions") or []}
        with self.cond:
            while True:
                if run.cancelled:
                    return "cancel"
                if self.signal and self.signal[0] == step["id"] \
                        and self.signal[1] in allowed:
                    action = self.signal[1]
                    self.signal = None
                    return action
                self.cond.wait(timeout=1.0)

    def send(self, step_id, action):
        """Returns (http status, body)."""
        with self.cond:
            if not self.active() or self.run is None:
                return 409, {"error": "no run is active"}
            snap = self.run.snapshot()
            step = next((s for s in snap["steps"] if s["id"] == step_id), None)
            if step is None:
                return 400, {"error": f"no step {step_id!r}"}
            if step["state"] not in ("waiting", "failed") or not step.get("prompt"):
                return 409, {"error": f"step {step_id!r} is not waiting for a person"}
            allowed = [a["id"] for a in step["prompt"]["actions"]]
            if action not in allowed:
                return 400, {"error": f"action {action!r} is not one of {allowed}"}
            if action == "cancel":
                self.run.cancelled = True
            self.signal = (step_id, action)
            self.cond.notify_all()
        # give the runner a moment, so the answer already shows the step moving on
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            s = next(x for x in self.run.snapshot()["steps"] if x["id"] == step_id)
            if s["state"] not in ("waiting", "failed") or not s.get("prompt"):
                break
            time.sleep(0.05)
        return 200, self.run.snapshot()

    def cancel(self):
        with self.cond:
            if not self.active() or self.run is None:
                return 409, {"error": "no run is active"}
            self.run.cancelled = True
            self.cond.notify_all()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
        return 200, self.run.snapshot()

    def test_mvp(self):
        """The current test workspace's mvp/, or None."""
        with self.lock:
            if self.workspace is None:
                return None
            mvp = (Path(self.workspace) / "mvp").resolve()
            return mvp if mvp.is_dir() else None

    def close(self):
        """On shutdown: stop the run, remove the last test workspace."""
        if self.run is not None and self.active():
            self.run.cancelled = True
            with self.cond:
                self.cond.notify_all()
            self.thread.join(timeout=2.0)
        if self.workspace is not None:
            _testenv(self.rm).remove_workspace(self.workspace)
            self.workspace = None


def make_handler(rm, runner, port):
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{h}" for h in hosts}

    class Handler(BaseHTTPRequestHandler):
        server_version = "mig-pipeline"

        def log_message(self, fmt, *args):
            sys.stderr.write(f"  http  {self.command} {self.path} {args[1] if len(args) > 1 else ''}\n")

        # -- plumbing --------------------------------------------------------
        def _send(self, status, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else (
                json.dumps(body, ensure_ascii=False).encode("utf-8")
                if ctype.startswith("application/json") else body.encode("utf-8"))
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _host_ok(self):
            if self.headers.get("Host", "") in hosts:
                return True
            self._send(403, {"error": "this server answers to 127.0.0.1 and localhost "
                                      "only"})
            return False

        def _body(self):
            """The JSON body of a POST, or None after answering with an error."""
            origin = self.headers.get("Origin")
            if origin is not None and origin not in origins:
                self._send(403, {"error": f"origin {origin!r} is not this server"})
                return None
            ctype = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if ctype != "application/json":
                self._send(415, {"error": "the body must be application/json"})
                return None
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if n < 0 or n > MAX_BODY:
                self._send(413 if n > MAX_BODY else 400, {"error": "bad body length"})
                return None
            raw = self.rfile.read(n) if n else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send(400, {"error": "the body is not valid JSON"})
                return None
            if not isinstance(body, dict):
                self._send(400, {"error": "the body must be a JSON object"})
                return None
            return body

        # -- routes ----------------------------------------------------------
        def do_GET(self):
            if not self._host_ok():
                return
            path = urlsplit(self.path).path
            try:
                if path in ("/", "/index.html"):
                    return self._page()
                if path == "/api/status":
                    ok, why = _testenv(rm).available()
                    status = {"server": True, "run": runner.current(),
                              "aiid_snapshot": rm.aiid_snapshot(),
                              "token_present": token_present(rm, runner.token_file),
                              "test_available": ok}
                    if not ok:
                        status["test_unavailable"] = why
                    return self._send(200, status)
                if path == "/api/run":
                    run = runner.current()
                    return self._send(200, run) if run else \
                        self._send(404, {"error": "no run yet"})
                return self._send(404, {"error": "not found"})
            except BaseException as e:   # noqa: BLE001 - incl. die() from a stage
                return self._send(500, {"error": f"{type(e).__name__}: {e}"})

        def do_POST(self):
            if not self._host_ok():
                return
            path = urlsplit(self.path).path
            if path not in ("/api/run", "/api/run/signal", "/api/run/cancel", "/api/open"):
                return self._send(404, {"error": "not found"})
            body = self._body()
            if body is None:
                return
            try:
                if path == "/api/open":
                    return self._open(body)
                if path == "/api/run":
                    return self._start(body)
                if path == "/api/run/signal":
                    step, action = body.get("step"), body.get("action")
                    if not isinstance(step, str) or not isinstance(action, str):
                        return self._send(400, {"error": "need step and action strings"})
                    return self._send(*runner.send(step, action))
                return self._send(*runner.cancel())
            except BaseException as e:   # noqa: BLE001
                return self._send(500, {"error": f"{type(e).__name__}: {e}"})

        def _start(self, body):
            test = body.get("test", False)
            if not isinstance(test, bool):
                return self._send(400, {"error": "test is true or false"})
            if test:
                return self._start_test(body)
            discover, refetch = body.get("discover", False), body.get("refetch", False)
            manual_dir = body.get("manual_dir", "") or ""
            if not isinstance(discover, bool) or not isinstance(refetch, bool):
                return self._send(400, {"error": "discover and refetch are true or false"})
            if not isinstance(manual_dir, str):
                return self._send(400, {"error": "manual_dir is a string"})
            if manual_dir:
                d = Path(manual_dir).expanduser()
                if not d.is_dir():
                    return self._send(400, {"error": f"{manual_dir!r} is not a directory"})
                manual_dir = str(d.resolve())
            run = runner.start(discover, refetch, manual_dir)
            if run is None:
                return self._send(409, {"error": "a run is already active; wait for it, "
                                                 "or cancel it"})
            return self._send(200, run)

        def _start_test(self, body):
            """A test run: made-up incidents in a scratch workspace. manual_dir is
            ignored; `manual` includes the sample write-up."""
            opts = {k: body.get(k, False) for k in ("discover", "refetch", "manual")}
            if not all(isinstance(v, bool) for v in opts.values()):
                return self._send(400, {"error": "discover, refetch and manual are true "
                                                 "or false"})
            ok, why = _testenv(rm).available()
            if not ok:
                return self._send(503, {"error": why})
            run = runner.start(opts["discover"], opts["refetch"], test=True,
                               manual=opts["manual"])
            if run is None:
                return self._send(409, {"error": "a run is already active; wait for it, "
                                                 "or cancel it"})
            return self._send(200, run)

        def _open(self, body):
            """Open a file or folder under mvp/ in the desktop's own application: what
            the page's "where it is kept" links do. With "test": true the path is under
            the current test workspace's mvp/ instead, and "." is that folder itself.
            The path is checked, then handed to the opener as one argument; no shell
            sees it."""
            rel, test = body.get("path"), body.get("test", False)
            if not isinstance(rel, str):
                return self._send(400, {"error": "need a path string"})
            if not isinstance(test, bool):
                return self._send(400, {"error": "test is true or false"})
            if test:
                mvp = runner.test_mvp()
                if mvp is None:
                    return self._send(409, {"error": "there is no test run workspace; "
                                                     "start a test run first"})
                where = "in the test workspace"
            else:
                mvp, where = rm.MVP.resolve(), ""
            parts = [p for p in rel.split("/") if p]
            if test and parts == ["."]:
                parts, target = [], mvp
            else:
                target = mvp.joinpath(*parts).resolve()
                if not parts:
                    target = None
            if (target is None or any(p.startswith(".") for p in parts)
                    or not target.is_relative_to(mvp) or not target.exists()):
                return self._send(404, {"error": f"nothing at mvp/{rel} {where}".rstrip()
                                        + (" yet" if test else "")})
            if not target.is_dir() and target.suffix.lower() not in OPEN_SUFFIXES:
                return self._send(400, {"error": f"{target.suffix or 'that'} files are "
                                                 "not opened from the page"})
            opener = shutil.which("xdg-open") or shutil.which("open")
            if opener is None:
                return self._send(501, {"error": "no xdg-open on this machine"})
            subprocess.Popen([opener, str(target)], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            body = {"opened": str(target.relative_to(mvp))}
            if test:
                body["workspace"] = str(mvp.parent)
            return self._send(200, body)

        def _page(self):
            state = rm.pipeline_state(rm.index_rows())
            payload = json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False)
            html = rm.render_page("pipeline_patch.html", payload)
            if html is None:
                return self._send(404, "no template", "text/plain; charset=utf-8")
            return self._send(200, html, "text/html; charset=utf-8")

    return Handler


def token_present(rm, token_file):
    """Is an AIID token to be had without asking? Never reads it out."""
    if token_file:
        return Path(token_file).expanduser().is_file()
    if os.environ.get("AIID_API_TOKEN", "").strip():
        return True
    try:
        sys.path.insert(0, str(Path(rm.__file__).resolve().parent))
        import fetch_aiid
        path = Path(fetch_aiid.DEFAULT_TOKEN_FILE).expanduser()
        return path.is_file() and bool(path.read_text(encoding="utf-8").strip())
    except Exception:            # noqa: BLE001
        return False


def serve(rm, port=8765, token_file=None):
    runner = Runner(rm, token_file)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), None)
    real_port = httpd.server_address[1]
    httpd.RequestHandlerClass = make_handler(rm, runner, real_port)
    httpd.daemon_threads = True
    print(f"serving the pipeline on http://127.0.0.1:{real_port}/  (ctrl-c to stop)",
          file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.", file=sys.stderr)
    finally:
        runner.close()
        httpd.server_close()
