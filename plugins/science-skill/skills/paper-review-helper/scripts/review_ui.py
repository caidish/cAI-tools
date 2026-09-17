#!/usr/bin/env python
"""Paper Review Helper - local web UI bridge between Claude Code and the reviewer.

Claude Code drives the review through this CLI; the reviewer reads, chats and
decides in the browser. Every command prints exactly one JSON object on stdout.

  start    python review_ui.py start --workspace <paper-folder> [--port 8765] [--no-open]
  meta     python review_ui.py meta --title "Paper title" [--outline outline.json]
  section  python review_ui.py section --id 01 --title "Introduction" --file artifact/sections/01.md
                                       [--figures figs.json] [--source "main.tex L120-210"]
  say      python review_ui.py say [--section 01] (--text "..." | --file reply.md)
  ask      python review_ui.py ask [--section 01] --prompt "..." [--options "A|B|C"] [--multi]
                                   [--text-label "..."] [--fields fields.json] [--timeout 100] [--no-wait]
  wait     python review_ui.py wait [--id N] [--timeout 100]
  issue    python review_ui.py issue --severity major|minor [--section 01] [--location "..."] --text "..."
  issues   python review_ui.py issues [--new]
  done     python review_ui.py done [--section 01]
  export   python review_ui.py export
  status   python review_ui.py status
  stop     python review_ui.py stop

All commands except `start` find the running server through --workspace
(<workspace>/artifact/ui-server.json) or the pointer file written by `start`
(~/.cache/paper-review-helper/current.json).

`ask` / `wait` block until the reviewer answers the question card, sends a chat
message, or the timeout elapses. Their result has "status" of:
  answered  - the question card was submitted; see "answer"
  message   - the reviewer sent chat messages; reply with `say`, then `wait` again
  pending   - timeout; call `wait` again (the question card stays open)
  cancelled - the question was replaced by a newer `ask`
Every result also carries "issues": issues the reviewer logged since the last delivery.

The server is stdlib-only and binds 127.0.0.1. State persists in
<workspace>/artifact/ui-state.json, so `start` on an existing workspace resumes.
"""

import argparse
import json
import mimetypes
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
UI_HTML = HERE / "ui" / "index.html"
POINTER = Path.home() / ".cache" / "paper-review-helper" / "current.json"
DEFAULT_PORT = 8765
DEFAULT_WAIT = 100  # seconds; stays under Claude Code's default 120 s Bash timeout
BROWSER_POLL = 25  # seconds the browser long-poll may hang


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- state


def empty_state(workspace):
    return {
        "version": 1,
        "workspace": str(workspace),
        "title": "",
        "outline": [],
        "sections": {},
        "current": None,
        "messages": [],
        "questions": [],
        "issues": [],
        "waiting": False,
        "started": now_iso(),
        "updated": now_iso(),
    }


class ReviewState:
    """In-memory state with a condition variable and JSON persistence."""

    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve()
        self.path = self.workspace / "artifact" / "ui-state.json"
        self.cond = threading.Condition()
        self.waiters = 0
        self.data = self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                data["workspace"] = str(self.workspace)
                data["waiting"] = False
                return data
            except (OSError, ValueError):
                pass
        return empty_state(self.workspace)

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False))
        os.replace(tmp, self.path)

    def _bump(self):
        self.data["version"] += 1
        self.data["updated"] = now_iso()
        self._save()
        self.cond.notify_all()

    def mutate(self, fn):
        """Run fn(data) under the lock, persist, and wake every long-poll."""
        with self.cond:
            result = fn(self.data)
            self._bump()
            return result

    def snapshot(self):
        with self.cond:
            return json.loads(json.dumps(self.data))

    def wait_version(self, version, timeout):
        with self.cond:
            self.cond.wait_for(lambda: self.data["version"] > version, timeout)
            return json.loads(json.dumps(self.data))

    # ---- helpers used by both CLI and browser ops
    @staticmethod
    def next_id(items):
        return (max((i["id"] for i in items), default=0) + 1)

    def find_question(self, qid):
        for q in self.data["questions"]:
            if q["id"] == qid:
                return q
        return None

    def latest_pending(self):
        """Latest question Claude still needs to hear about: pending, or resolved but undelivered."""
        for q in reversed(self.data["questions"]):
            if q["status"] == "pending" or not q.get("delivered"):
                return q
        return None


# --------------------------------------------------------------------------- ops


def op_meta(data, req):
    if req.get("title") is not None:
        data["title"] = req["title"]
    if req.get("outline") is not None:
        outline = []
        for i, entry in enumerate(req["outline"]):
            if isinstance(entry, str):
                entry = {"id": f"{i + 1:02d}", "title": entry}
            outline.append(
                {
                    "id": str(entry.get("id", f"{i + 1:02d}")),
                    "title": entry.get("title", ""),
                    "level": int(entry.get("level", 1)),
                    "paragraphs": entry.get("paragraphs"),
                    "skip": bool(entry.get("skip", False)),
                }
            )
        data["outline"] = outline
    return {"ok": True}


def op_section(data, req):
    sid = str(req["id"])
    prev = data.get("current")
    if prev and prev != sid and prev in data["sections"]:
        if data["sections"][prev].get("status") == "open":
            data["sections"][prev]["status"] = "done"
    data["sections"][sid] = {
        "id": sid,
        "title": req.get("title") or sid,
        "markdown": req.get("markdown", ""),
        "file": req.get("file"),
        "base": req.get("base", ""),
        "figures": req.get("figures") or [],
        "source": req.get("source"),
        "status": "open",
        "posted_at": now_iso(),
    }
    if sid not in [o["id"] for o in data["outline"]]:
        data["outline"].append({"id": sid, "title": req.get("title") or sid, "level": 1})
    data["current"] = sid
    return {"ok": True, "section": sid}


def _add_message(data, role, section, text, kind="message", answer=None, delivered=False):
    msg = {
        "id": ReviewState.next_id(data["messages"]),
        "role": role,
        "section": section,
        "text": text,
        "kind": kind,
        "ts": now_iso(),
        "delivered": delivered,
    }
    if answer is not None:
        msg["answer"] = answer
    data["messages"].append(msg)
    return msg


def op_say(data, req):
    section = req.get("section") or data.get("current")
    msg = _add_message(data, "assistant", section, req.get("text", ""), delivered=True)
    return {"ok": True, "message_id": msg["id"]}


def op_ask(data, req):
    section = req.get("section") or data.get("current")
    for q in data["questions"]:
        if q["status"] == "pending":
            q["status"] = "cancelled"
    options = req.get("options") or []
    q = {
        "id": ReviewState.next_id(data["questions"]),
        "section": section,
        "prompt": req.get("prompt", ""),
        "options": options,
        "multi": bool(req.get("multi", False)),
        "text_label": req.get("text_label"),
        "fields": req.get("fields") or [],
        "status": "pending",
        "answer": None,
        "delivered": False,
        "ts": now_iso(),
    }
    data["questions"].append(q)
    return {"ok": True, "question_id": q["id"]}


def op_issue(data, req, source):
    issue = {
        "id": ReviewState.next_id(data["issues"]),
        "severity": "major" if req.get("severity") == "major" else "minor",
        "section": req.get("section") or data.get("current"),
        "location": req.get("location") or "",
        "text": req.get("text", ""),
        "marker": req.get("marker"),
        "source": source,
        "ts": now_iso(),
        "delivered": source == "claude",
    }
    data["issues"].append(issue)
    return {"ok": True, "issue_id": issue["id"]}


def op_done(data, req):
    sid = req.get("section") or data.get("current")
    if sid in data["sections"]:
        data["sections"][sid]["status"] = "done"
    return {"ok": True, "section": sid}


def op_cancel(data, req):
    q = None
    for cand in data["questions"]:
        if cand["id"] == req.get("id"):
            q = cand
    if q and q["status"] == "pending":
        q["status"] = "cancelled"
    return {"ok": True}


def export_files(state):
    """Write issues-major.md, issues-minor.md and ui-transcript.md into artifact/."""
    data = state.snapshot()
    art = state.workspace / "artifact"
    art.mkdir(parents=True, exist_ok=True)
    titles = {o["id"]: o["title"] for o in data["outline"]}
    titles.update({k: v["title"] for k, v in data["sections"].items()})

    def sec_name(sid):
        return titles.get(sid, sid or "general")

    written = []
    for sev in ("major", "minor"):
        lines = [f"# {sev.capitalize()} Issues", ""]
        items = [i for i in data["issues"] if i["severity"] == sev]
        if not items:
            lines.append("_None logged._")
        for n, i in enumerate(items, 1):
            loc = f" ({i['location']})" if i.get("location") else ""
            who = "reviewer" if i.get("source") == "user" else "claude"
            lines.append(f"{n}. **[{sec_name(i['section'])}{loc}]** {i['text']}  ")
            lines.append(f"   _logged by {who}, {i['ts']}_")
        path = art / f"issues-{sev}.md"
        path.write_text("\n".join(lines) + "\n")
        written.append(str(path))

    lines = [f"# Review transcript - {data.get('title') or state.workspace.name}", ""]
    qmap = {q["id"]: q for q in data["questions"]}
    by_section = {}
    for m in data["messages"]:
        by_section.setdefault(m.get("section"), []).append(m)
    for sid, msgs in by_section.items():
        lines.append(f"## {sec_name(sid)}")
        lines.append("")
        for m in msgs:
            who = "Reviewer" if m["role"] == "user" else "Claude"
            if m.get("kind") == "answer" and m.get("answer"):
                lines.append(f"**{who} decided** ({m['ts']}): {json.dumps(m['answer'], ensure_ascii=False)}")
            else:
                lines.append(f"**{who}** ({m['ts']}):")
                lines.append("")
                lines.append(m["text"])
            lines.append("")
    for q in data["questions"]:
        if q["status"] == "answered":
            qmap[q["id"]] = q
    path = art / "ui-transcript.md"
    path.write_text("\n".join(lines) + "\n")
    written.append(str(path))
    return written


# --------------------------------------------------------------------------- server


class Handler(BaseHTTPRequestHandler):
    state = None  # type: ReviewState
    server_version = "PaperReviewUI/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quiet unless REVIEW_UI_DEBUG is set
        if os.environ.get("REVIEW_UI_DEBUG"):
            super().log_message(fmt, *args)

    # ---- helpers
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            return {}

    # ---- routing
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url.query)
        if url.path in ("/", "/index.html"):
            if not UI_HTML.exists():
                return self._send(500, "ui/index.html missing", "text/plain")
            return self._send(200, UI_HTML.read_bytes(), "text/html; charset=utf-8")
        if url.path == "/api/health":
            return self._send(200, {"ok": True, "workspace": str(self.state.workspace), "pid": os.getpid()})
        if url.path == "/api/state":
            version = int(qs.get("v", ["0"])[0])
            timeout = min(float(qs.get("timeout", [str(BROWSER_POLL)])[0]), 60)
            return self._send(200, self.state.wait_version(version, timeout))
        if url.path == "/api/wait":
            qid = qs.get("id", [None])[0]
            timeout = min(float(qs.get("timeout", [str(DEFAULT_WAIT)])[0]), 3000)
            return self._send(200, self._wait(int(qid) if qid else None, timeout))
        if url.path.startswith("/files/"):
            return self._serve_file(urllib.parse.unquote(url.path[len("/files/"):]))
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        req = self._json_body()
        if url.path == "/api/cli":
            return self._cli(req)
        if url.path == "/api/user":
            return self._user(req)
        return self._send(404, {"error": "not found"})

    # ---- file serving restricted to the workspace
    def _serve_file(self, rel):
        root = self.state.workspace
        target = (root / rel).resolve()
        if root not in target.parents and target != root:
            return self._send(403, {"error": "outside workspace"})
        if not target.is_file():
            return self._send(404, {"error": "no such file"})
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        return self._send(200, target.read_bytes(), ctype)

    # ---- CLI side
    def _cli(self, req):
        op = req.get("op")
        st = self.state
        try:
            if op == "meta":
                return self._send(200, st.mutate(lambda d: op_meta(d, req)))
            if op == "section":
                return self._send(200, st.mutate(lambda d: op_section(d, req)))
            if op == "say":
                return self._send(200, st.mutate(lambda d: op_say(d, req)))
            if op == "ask":
                return self._send(200, st.mutate(lambda d: op_ask(d, req)))
            if op == "issue":
                return self._send(200, st.mutate(lambda d: op_issue(d, req, "claude")))
            if op == "done":
                return self._send(200, st.mutate(lambda d: op_done(d, req)))
            if op == "cancel":
                return self._send(200, st.mutate(lambda d: op_cancel(d, req)))
            if op == "issues":
                return self._send(200, self._issues(req.get("new", False)))
            if op == "export":
                return self._send(200, {"ok": True, "written": export_files(st)})
            if op == "shutdown":
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return self._send(200, {"ok": True, "stopping": True})
        except KeyError as exc:
            return self._send(400, {"error": f"missing field {exc}"})
        return self._send(400, {"error": f"unknown op {op!r}"})

    def _issues(self, only_new):
        def fn(d):
            items = [i for i in d["issues"] if not only_new or not i.get("delivered")]
            for i in items:
                i["delivered"] = True
            return {"ok": True, "issues": json.loads(json.dumps(items))}

        return self.state.mutate(fn)

    def _wait(self, qid, timeout):
        st = self.state
        deadline = time.monotonic() + timeout
        with st.cond:
            st.waiters += 1
            st.data["waiting"] = True
            st._bump()
            try:
                if qid is None:
                    q = st.latest_pending()
                    qid = q["id"] if q else None
                while True:
                    q = st.find_question(qid) if qid is not None else None
                    new_msgs = [
                        m
                        for m in st.data["messages"]
                        if m["role"] == "user" and m.get("kind") == "message" and not m.get("delivered")
                    ]
                    new_issues = [i for i in st.data["issues"] if not i.get("delivered")]
                    result = None
                    if q and q["status"] in ("answered", "cancelled"):
                        result = {"status": q["status"], "question_id": qid, "answer": q.get("answer")}
                        q["delivered"] = True
                    elif new_msgs:
                        result = {"status": "message", "question_id": qid}
                    if result is not None:
                        result["messages"] = json.loads(json.dumps(new_msgs))
                        result["issues"] = json.loads(json.dumps(new_issues))
                        for m in new_msgs:
                            m["delivered"] = True
                        for i in new_issues:
                            i["delivered"] = True
                        result["section"] = q["section"] if q else st.data.get("current")
                        st._bump()
                        return result
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return {"status": "pending", "question_id": qid, "messages": [], "issues": []}
                    st.cond.wait(remaining)
            finally:
                st.waiters -= 1
                if st.waiters == 0:
                    st.data["waiting"] = False
                    st._bump()

    # ---- browser side
    def _user(self, req):
        op = req.get("op")
        st = self.state

        def answer(d):
            q = None
            for cand in d["questions"]:
                if cand["id"] == req.get("question_id"):
                    q = cand
            if not q or q["status"] != "pending":
                return {"ok": False, "error": "question not pending"}
            q["status"] = "answered"
            q["answer"] = req.get("answer") or {}
            _add_message(d, "user", q["section"], req.get("summary", ""), kind="answer", answer=q["answer"], delivered=True)
            return {"ok": True}

        def message(d):
            section = req.get("section") or d.get("current")
            m = _add_message(d, "user", section, req.get("text", ""))
            return {"ok": True, "message_id": m["id"]}

        def issue_update(d):
            for i in d["issues"]:
                if i["id"] == req.get("id"):
                    for key in ("severity", "location", "text", "section"):
                        if key in req:
                            i[key] = req[key]
                    i["delivered"] = False
                    return {"ok": True}
            return {"ok": False, "error": "no such issue"}

        def issue_delete(d):
            d["issues"] = [i for i in d["issues"] if i["id"] != req.get("id")]
            return {"ok": True}

        if op == "answer":
            return self._send(200, st.mutate(answer))
        if op == "message":
            return self._send(200, st.mutate(message))
        if op == "issue_add":
            return self._send(200, st.mutate(lambda d: op_issue(d, req, "user")))
        if op == "issue_update":
            return self._send(200, st.mutate(issue_update))
        if op == "issue_delete":
            return self._send(200, st.mutate(issue_delete))
        return self._send(400, {"error": f"unknown op {op!r}"})


def serve(workspace, port):
    Handler.state = ReviewState(workspace)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    info = {"workspace": str(Handler.state.workspace), "port": port, "pid": os.getpid(), "url": f"http://127.0.0.1:{port}/"}
    (Handler.state.workspace / "artifact").mkdir(parents=True, exist_ok=True)
    (Handler.state.workspace / "artifact" / "ui-server.json").write_text(json.dumps(info, indent=1))
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        try:
            (Handler.state.workspace / "artifact" / "ui-server.json").unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------- client


def out(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False, indent=1))
    sys.exit(code)


def http(url, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read() or b"{}")


def health(port):
    try:
        return http(f"http://127.0.0.1:{port}/api/health", timeout=3)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def load_server_info(workspace=None):
    """Return {url, port, workspace} for a healthy server, else None."""
    candidates = []
    if workspace:
        candidates.append(Path(workspace).resolve() / "artifact" / "ui-server.json")
    candidates.append(POINTER)
    for path in candidates:
        if not path.exists():
            continue
        try:
            info = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        h = health(info.get("port", 0))
        if h and (not workspace or Path(h["workspace"]) == Path(workspace).resolve()):
            info["workspace"] = h["workspace"]
            return info
    return None


def require_server(args):
    info = load_server_info(getattr(args, "workspace", None))
    if not info:
        out({"ok": False, "error": "no running review UI; run `review_ui.py start --workspace <paper-folder>`"}, 1)
    return info


def free_port(start):
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("no free port")


def cmd_start(args):
    ws = Path(args.workspace).resolve()
    (ws / "artifact").mkdir(parents=True, exist_ok=True)
    existing = load_server_info(ws)
    if existing:
        if not args.no_open:
            webbrowser.open(existing["url"])
        out({"ok": True, "url": existing["url"], "port": existing["port"], "workspace": str(ws), "resumed": True})
    other = load_server_info()
    if other and args.stop_others:
        try:
            http(f"{other['url']}api/cli", {"op": "shutdown"}, timeout=5)
        except (urllib.error.URLError, OSError):
            pass
    port = free_port(args.port)
    log = open(ws / "artifact" / "ui-server.log", "ab")
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "serve", "--workspace", str(ws), "--port", str(port)],
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    for _ in range(50):
        if health(port):
            break
        if proc.poll() is not None:
            out({"ok": False, "error": f"server exited early; see {ws / 'artifact' / 'ui-server.log'}"}, 1)
        time.sleep(0.2)
    else:
        out({"ok": False, "error": "server did not become healthy"}, 1)
    info = {"workspace": str(ws), "port": port, "pid": proc.pid, "url": f"http://127.0.0.1:{port}/"}
    POINTER.parent.mkdir(parents=True, exist_ok=True)
    POINTER.write_text(json.dumps(info, indent=1))
    if not args.no_open:
        webbrowser.open(info["url"])
    out({"ok": True, **info, "resumed": False})


def cmd_stop(args):
    info = load_server_info(getattr(args, "workspace", None))
    if not info:
        out({"ok": True, "stopped": False, "note": "no running server"})
    try:
        http(f"{info['url']}api/cli", {"op": "shutdown"}, timeout=5)
    except (urllib.error.URLError, OSError):
        pass
    for _ in range(25):
        if not health(info["port"]):
            break
        time.sleep(0.2)
    if POINTER.exists():
        try:
            if json.loads(POINTER.read_text()).get("port") == info["port"]:
                POINTER.unlink()
        except (OSError, ValueError):
            pass
    out({"ok": True, "stopped": True, "workspace": info["workspace"]})


def cmd_status(args):
    info = load_server_info(getattr(args, "workspace", None))
    if not info:
        out({"ok": True, "running": False})
    state = http(f"{info['url']}api/state?v=0&timeout=0", timeout=10)
    pending = [q for q in state["questions"] if q["status"] == "pending"]
    out(
        {
            "ok": True,
            "running": True,
            "url": info["url"],
            "workspace": info["workspace"],
            "title": state.get("title"),
            "current": state.get("current"),
            "sections": {k: v["status"] for k, v in state["sections"].items()},
            "pending_question": pending[-1]["id"] if pending else None,
            "issues": {
                "major": sum(1 for i in state["issues"] if i["severity"] == "major"),
                "minor": sum(1 for i in state["issues"] if i["severity"] == "minor"),
                "undelivered": sum(1 for i in state["issues"] if not i.get("delivered")),
            },
            "unread_messages": sum(
                1 for m in state["messages"] if m["role"] == "user" and m.get("kind") == "message" and not m.get("delivered")
            ),
        }
    )


def cli_call(info, payload, timeout=30):
    return http(f"{info['url']}api/cli", payload, timeout=timeout)


def cmd_meta(args):
    info = require_server(args)
    payload = {"op": "meta", "title": args.title}
    if args.outline:
        payload["outline"] = json.loads(Path(args.outline).read_text())
        if isinstance(payload["outline"], dict):  # tex_tools.py outline output
            if not args.title and payload["outline"].get("title"):
                payload["title"] = payload["outline"]["title"]
            payload["outline"] = payload["outline"].get("sections", [])
    elif args.sections:
        payload["outline"] = [s.strip() for s in args.sections.split("|") if s.strip()]
    out(cli_call(info, payload))


def cmd_section(args):
    info = require_server(args)
    ws = Path(info["workspace"])
    md_path = Path(args.file).resolve()
    if not md_path.exists():
        out({"ok": False, "error": f"{md_path} not found"}, 1)
    try:
        rel = md_path.relative_to(ws)
        base = str(rel.parent).replace(os.sep, "/")
        file_rel = str(rel).replace(os.sep, "/")
    except ValueError:
        base, file_rel = "", str(md_path)
    figures = []
    if args.figures:
        raw = json.loads(Path(args.figures).read_text())
        figures = raw.get("figures", raw) if isinstance(raw, dict) else raw
    for fig in figures:
        p = Path(fig.get("path", ""))
        if p.is_absolute():
            try:
                fig["path"] = str(p.resolve().relative_to(ws)).replace(os.sep, "/")
            except ValueError:
                pass
    markdown = md_path.read_text()

    def to_served(m):  # absolute paths inside the workspace become /files/<rel> URLs
        try:
            rel = Path(m.group(2)).resolve().relative_to(ws)
            return f"{m.group(1)}(/files/{str(rel).replace(os.sep, '/')})"
        except ValueError:
            return m.group(0)

    markdown = re.sub(r"(!\[[^\]]*\])\((/[^)\s]+)\)", to_served, markdown)
    payload = {
        "op": "section",
        "id": args.id,
        "title": args.title,
        "markdown": markdown,
        "file": file_rel,
        "base": base if base != "." else "",
        "figures": figures,
        "source": args.source,
    }
    out(cli_call(info, payload))


def cmd_say(args):
    info = require_server(args)
    text = args.text if args.text is not None else Path(args.file).read_text()
    out(cli_call(info, {"op": "say", "section": args.section, "text": text}))


def do_wait(info, qid, timeout):
    try:
        url = f"{info['url']}api/wait?timeout={timeout}" + (f"&id={qid}" if qid is not None else "")
        return http(url, timeout=timeout + 20)
    except (urllib.error.URLError, OSError) as exc:
        return {"status": "error", "error": str(exc), "question_id": qid}


def cmd_ask(args):
    info = require_server(args)
    payload = {
        "op": "ask",
        "section": args.section,
        "prompt": args.prompt,
        "options": [o.strip() for o in args.options.split("|") if o.strip()] if args.options else [],
        "multi": args.multi,
        "text_label": args.text_label,
        "fields": json.loads(Path(args.fields).read_text()) if args.fields else [],
    }
    res = cli_call(info, payload)
    qid = res.get("question_id")
    if args.no_wait:
        out({"ok": True, "question_id": qid, "status": "pending"})
    out(do_wait(info, qid, args.timeout))


def cmd_wait(args):
    info = require_server(args)
    out(do_wait(info, args.id, args.timeout))


def cmd_issue(args):
    info = require_server(args)
    out(
        cli_call(
            info,
            {
                "op": "issue",
                "severity": args.severity,
                "section": args.section,
                "location": args.location,
                "text": args.text,
                "marker": args.marker,
            },
        )
    )


def cmd_issues(args):
    info = require_server(args)
    out(cli_call(info, {"op": "issues", "new": args.new}))


def cmd_done(args):
    info = require_server(args)
    out(cli_call(info, {"op": "done", "section": args.section}))


def cmd_export(args):
    info = require_server(args)
    out(cli_call(info, {"op": "export"}))


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--workspace", help="paper folder (defaults to the last started session)")
        return sp

    sp = common(sub.add_parser("start", help="start the UI server for a workspace and open the browser"))
    sp.add_argument("--port", type=int, default=DEFAULT_PORT)
    sp.add_argument("--no-open", action="store_true", help="do not open the browser")
    sp.add_argument("--stop-others", action="store_true", help="stop a server running for another workspace")
    sp.set_defaults(fn=cmd_start)

    sp = common(sub.add_parser("serve", help="(internal) run the server in the foreground"))
    sp.add_argument("--port", type=int, default=DEFAULT_PORT)
    sp.set_defaults(fn=lambda a: serve(a.workspace, a.port))

    common(sub.add_parser("stop")).set_defaults(fn=cmd_stop)
    common(sub.add_parser("status")).set_defaults(fn=cmd_status)

    sp = common(sub.add_parser("meta", help="set paper title and section outline"))
    sp.add_argument("--title")
    sp.add_argument("--outline", help="JSON file: list of {id,title,level} or tex_tools.py outline output")
    sp.add_argument("--sections", help='pipe-separated titles, e.g. "Abstract|Introduction|Methods"')
    sp.set_defaults(fn=cmd_meta)

    sp = common(sub.add_parser("section", help="show a section (markdown file) in the browser"))
    sp.add_argument("--id", required=True)
    sp.add_argument("--title", required=True)
    sp.add_argument("--file", required=True, help="markdown file with inline markers")
    sp.add_argument("--figures", help='JSON file: [{"path": "...", "caption": "...", "label": "..."}]')
    sp.add_argument("--source", help='where the text came from, e.g. "main.tex L120-210"')
    sp.set_defaults(fn=cmd_section)

    sp = common(sub.add_parser("say", help="post a message from Claude into the section thread"))
    sp.add_argument("--section")
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--text")
    g.add_argument("--file")
    sp.set_defaults(fn=cmd_say)

    sp = common(sub.add_parser("ask", help="show a decision card and wait for the reviewer"))
    sp.add_argument("--section")
    sp.add_argument("--prompt", required=True)
    sp.add_argument("--options", help='pipe-separated choices, e.g. "Clear|Somewhat unclear|Confusing"')
    sp.add_argument("--multi", action="store_true", help="allow several choices")
    sp.add_argument("--text-label", help="label for the free-text box (omit for no text box)")
    sp.add_argument("--fields", help="JSON file describing a form (see references/ui-protocol.md)")
    sp.add_argument("--timeout", type=int, default=DEFAULT_WAIT)
    sp.add_argument("--no-wait", action="store_true")
    sp.set_defaults(fn=cmd_ask)

    sp = common(sub.add_parser("wait", help="wait for an answer or chat message"))
    sp.add_argument("--id", type=int, help="question id (default: latest pending)")
    sp.add_argument("--timeout", type=int, default=DEFAULT_WAIT)
    sp.set_defaults(fn=cmd_wait)

    sp = common(sub.add_parser("issue", help="log an issue found by Claude"))
    sp.add_argument("--severity", choices=["major", "minor"], required=True)
    sp.add_argument("--section")
    sp.add_argument("--location")
    sp.add_argument("--text", required=True)
    sp.add_argument("--marker", choices=["G", "C", "?", "REF", "EQ"])
    sp.set_defaults(fn=cmd_issue)

    sp = common(sub.add_parser("issues", help="list logged issues"))
    sp.add_argument("--new", action="store_true", help="only issues not yet delivered to Claude")
    sp.set_defaults(fn=cmd_issues)

    sp = common(sub.add_parser("done", help="mark a section as reviewed"))
    sp.add_argument("--section")
    sp.set_defaults(fn=cmd_done)

    common(sub.add_parser("export", help="write issues-major.md, issues-minor.md, ui-transcript.md")).set_defaults(fn=cmd_export)
    return p


def main():
    args = build_parser().parse_args()
    if args.cmd == "serve":
        if not args.workspace:
            out({"ok": False, "error": "--workspace required"}, 1)
        serve(args.workspace, args.port)
        return
    try:
        args.fn(args)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        out({"ok": False, "error": f"HTTP {exc.code}: {body}"}, 1)
    except (urllib.error.URLError, OSError) as exc:
        out({"ok": False, "error": str(exc)}, 1)


if __name__ == "__main__":
    main()
