#!/usr/bin/env python
"""Hardworking Paper Writer - local web UI bridge between Claude Code and the author.

Claude Code drives the revision through this CLI; the author reads the paper with the
current sentence highlighted, picks a rewrite (or writes their own) and chats, all in
the browser. Every command prints exactly one JSON object on stdout.

  start    python writer_ui.py start --workspace <paper-stem>-revision [--port 8766] [--no-open]
  meta     python writer_ui.py meta [--title "Paper title"] [--sections "Abstract|Introduction|..."]
  load     python writer_ui.py load --sentences artifact/sentences.json      (segment.py output)
  focus    python writer_ui.py focus --id S012
  propose  python writer_ui.py propose --id S012 (--options opts.json | --light T --medium T --bold T [--notes "a|b|c"])
                                       [--prompt "..."] [--no-keep] [--text-label "..."] [--timeout 100] [--no-wait]
  ask      python writer_ui.py ask [--section 02] [--sentence S012] --prompt "..." [--options "A|B"] [--multi]
                                   [--text-label "..."] [--fields fields.json] [--timeout 100] [--no-wait]
  wait     python writer_ui.py wait [--id N] [--timeout 100]
  say      python writer_ui.py say [--section 02] [--sentence S012] (--text "..." | --file reply.md)
  apply    python writer_ui.py apply --id S012 --status edited|kept [--text "..."] [--choice light|medium|bold|other|keep] [--fixes "..."]
  profile  python writer_ui.py profile --file style-profile.md
  export   python writer_ui.py export
  status   python writer_ui.py status
  stop     python writer_ui.py stop

All commands except `start` find the running server through --workspace
(<workspace>/artifact/ui-server.json) or the pointer file written by `start`
(~/.cache/hardworking-paper-writer/current.json).

`propose`, `ask` and `wait` block until the author answers the card, sends a chat
message, or the timeout elapses. Their result has "status" of:
  answered  - the card was submitted; see "answer"
  message   - the author sent chat messages; reply with `say`, then `wait` again
  pending   - timeout; call `wait` again (the card stays open)
  cancelled - the card was replaced by a newer propose/ask
For a propose card, "answer" is {"choice": "light|medium|bold|keep|other", "chosen_text": "...",
"text": "<free text: the author's own wording or a steering instruction>"}.

The server is stdlib-only and binds 127.0.0.1. State persists in
<workspace>/artifact/ui-state.json, so `start` on an existing workspace resumes.
"""

import argparse
import json
import mimetypes
import os
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
sys.path.insert(0, str(HERE))
from segment import to_display  # noqa: E402

UI_HTML = HERE / "ui" / "index.html"
POINTER = Path.home() / ".cache" / "hardworking-paper-writer" / "current.json"
DEFAULT_PORT = 8766  # paper-review-helper uses 8765
DEFAULT_WAIT = 100  # seconds; stays under Claude Code's default 120 s Bash timeout
BROWSER_POLL = 25  # seconds the browser long-poll may hang
LEVELS = ("light", "medium", "bold")


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- state


def empty_state(workspace):
    return {
        "version": 1,
        "workspace": str(workspace),
        "title": "",
        "format": "txt",
        "outline": [],
        "sentences": [],
        "current": None,
        "messages": [],
        "questions": [],
        "profile": "",
        "waiting": False,
        "started": now_iso(),
        "updated": now_iso(),
    }


def progress(data):
    counts = {"total": 0, "pending": 0, "kept": 0, "edited": 0}
    for s in data["sentences"]:
        counts["total"] += 1
        counts[s.get("status", "pending")] = counts.get(s.get("status", "pending"), 0) + 1
    counts["reviewed"] = counts["kept"] + counts["edited"]
    return counts


class WriterState:
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

    @staticmethod
    def next_id(items):
        return max((i["id"] for i in items), default=0) + 1

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


def find_sentence(data, sid):
    for s in data["sentences"]:
        if s["id"] == sid:
            return s
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
                    "skip": bool(entry.get("skip", False)),
                }
            )
        data["outline"] = outline
    return {"ok": True}


def op_load(data, req):
    """Replace the sentence list; keep status/edits of sentences whose id and original text match."""
    old = {s["id"]: s for s in data["sentences"]}
    fmt = req.get("format") or data.get("format") or "txt"
    data["format"] = fmt
    new = []
    for s in req.get("sentences") or []:
        sid = str(s["id"])
        text = s.get("text", "")
        entry = {
            "id": sid,
            "section": str(s.get("section") or "01"),
            "para": int(s.get("para") or 0),
            "kind": s.get("kind", "prose"),
            "line": s.get("line"),
            "original": text,
            "current": text,
            "display": s.get("display") or (to_display(text) if fmt == "tex" else text),
            "display_original": s.get("display") or (to_display(text) if fmt == "tex" else text),
            "status": "pending",
            "choice": None,
            "fixes": "",
            "ts": None,
        }
        prev = old.get(sid)
        if prev and prev.get("original") == text and prev.get("status") != "pending":
            for k in ("current", "display", "status", "choice", "fixes", "ts"):
                entry[k] = prev.get(k, entry[k])
        new.append(entry)
    data["sentences"] = new
    if req.get("sections"):
        op_meta(data, {"outline": req["sections"]})
    if req.get("title") and not data.get("title"):
        data["title"] = req["title"]
    if data.get("current") not in {s["id"] for s in new}:
        data["current"] = None
    return {"ok": True, "loaded": len(new), "progress": progress(data)}


def op_focus(data, req):
    sid = req.get("id")
    if sid and not find_sentence(data, sid):
        return {"ok": False, "error": f"no sentence {sid}"}
    data["current"] = sid
    return {"ok": True, "current": sid}


def _add_message(data, role, section, text, kind="message", answer=None, delivered=False, sentence=None):
    msg = {
        "id": WriterState.next_id(data["messages"]),
        "role": role,
        "section": section,
        "sentence": sentence,
        "text": text,
        "kind": kind,
        "ts": now_iso(),
        "delivered": delivered,
    }
    if answer is not None:
        msg["answer"] = answer
    data["messages"].append(msg)
    return msg


def _section_of(data, req):
    if req.get("section"):
        return req["section"]
    sid = req.get("sentence") or data.get("current")
    s = find_sentence(data, sid) if sid else None
    return s["section"] if s else None


def op_say(data, req):
    section = _section_of(data, req)
    msg = _add_message(data, "assistant", section, req.get("text", ""), delivered=True, sentence=req.get("sentence") or data.get("current"))
    return {"ok": True, "message_id": msg["id"]}


def _new_question(data, kind, req, **extra):
    for q in data["questions"]:
        if q["status"] == "pending":
            q["status"] = "cancelled"
    q = {
        "id": WriterState.next_id(data["questions"]),
        "kind": kind,
        "section": _section_of(data, req),
        "sentence": req.get("sentence") or (data.get("current") if kind == "propose" else None),
        "prompt": req.get("prompt", ""),
        "status": "pending",
        "answer": None,
        "delivered": False,
        "ts": now_iso(),
    }
    q.update(extra)
    data["questions"].append(q)
    return q


def op_propose(data, req):
    sid = req["id"]
    s = find_sentence(data, sid)
    if not s:
        return {"ok": False, "error": f"no sentence {sid}"}
    data["current"] = sid
    options = []
    for o in req.get("options") or []:
        options.append(
            {
                "level": str(o.get("level", "")).lower() or "option",
                "text": o.get("text", ""),
                "display": o.get("display") or (to_display(o.get("text", "")) if data.get("format") == "tex" else o.get("text", "")),
                "note": o.get("note", ""),
            }
        )
    q = _new_question(
        data,
        "propose",
        {"sentence": sid, "prompt": req.get("prompt") or "Which version?"},
        options=options,
        keep=bool(req.get("keep", True)),
        text_label=req.get("text_label") or "Your own wording, or tell Claude how to change these options",
    )
    return {"ok": True, "question_id": q["id"], "sentence": sid}


def op_ask(data, req):
    q = _new_question(
        data,
        "ask",
        req,
        options=req.get("options") or [],
        multi=bool(req.get("multi", False)),
        text_label=req.get("text_label"),
        fields=req.get("fields") or [],
    )
    return {"ok": True, "question_id": q["id"]}


def op_apply(data, req):
    s = find_sentence(data, req["id"])
    if not s:
        return {"ok": False, "error": f"no sentence {req['id']}"}
    status = req.get("status") or ("edited" if req.get("text") else "kept")
    if status not in ("edited", "kept", "pending"):
        return {"ok": False, "error": "status must be edited, kept or pending"}
    if status == "edited":
        text = req.get("text")
        if text is None:
            return {"ok": False, "error": "--text required for edited"}
        s["current"] = text
        s["display"] = to_display(text) if data.get("format") == "tex" else text
    elif status == "kept":
        s["current"] = s["original"]
        s["display"] = s.get("display_original", s["display"])
    else:
        s["current"] = s["original"]
        s["display"] = s.get("display_original", s["display"])
    s["status"] = status
    s["choice"] = req.get("choice")
    s["fixes"] = req.get("fixes") or ""
    s["ts"] = now_iso()
    return {"ok": True, "sentence": s["id"], "status": status, "progress": progress(data)}


def op_profile(data, req):
    data["profile"] = req.get("text", "")
    return {"ok": True}


def op_cancel(data, req):
    for q in data["questions"]:
        if q["id"] == req.get("id") and q["status"] == "pending":
            q["status"] = "cancelled"
    return {"ok": True}


def export_files(state):
    """Write changes.md and ui-transcript.md into artifact/."""
    data = state.snapshot()
    art = state.workspace / "artifact"
    art.mkdir(parents=True, exist_ok=True)
    titles = {o["id"]: o["title"] for o in data["outline"]}
    p = progress(data)
    lines = [f"# Changes - {data.get('title') or state.workspace.name}", "",
             f"Sentences: {p['total']} total, {p['reviewed']} reviewed ({p['edited']} edited, {p['kept']} kept), {p['pending']} pending.", ""]
    section = None
    for s in data["sentences"]:
        if s["status"] != "edited":
            continue
        if s["section"] != section:
            section = s["section"]
            lines += [f"## {titles.get(section, section)}", ""]
        lines.append(f"### {s['id']}" + (f" - {s['choice']}" if s.get("choice") else ""))
        lines.append(f"- Original: {s['original']}")
        lines.append(f"- Final:    {s['current']}")
        if s.get("fixes"):
            lines.append(f"- Fixes:    {s['fixes']}")
        lines.append("")
    if p["edited"] == 0:
        lines.append("_No sentences edited yet._")
    written = []
    path = art / "changes.md"
    path.write_text("\n".join(lines) + "\n")
    written.append(str(path))

    lines = [f"# Revision transcript - {data.get('title') or state.workspace.name}", ""]
    by_section = {}
    for m in data["messages"]:
        by_section.setdefault(m.get("section"), []).append(m)
    for sid, msgs in by_section.items():
        lines += [f"## {titles.get(sid, sid or 'general')}", ""]
        for m in msgs:
            who = "Author" if m["role"] == "user" else "Claude"
            tag = f" [{m['sentence']}]" if m.get("sentence") else ""
            if m.get("kind") == "answer" and m.get("answer"):
                lines.append(f"**{who} decided{tag}** ({m['ts']}): {json.dumps(m['answer'], ensure_ascii=False)}")
            else:
                lines += [f"**{who}{tag}** ({m['ts']}):", "", m["text"]]
            lines.append("")
    path = art / "ui-transcript.md"
    path.write_text("\n".join(lines) + "\n")
    written.append(str(path))
    return written


# --------------------------------------------------------------------------- server


class Handler(BaseHTTPRequestHandler):
    state = None  # type: WriterState
    server_version = "PaperWriterUI/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quiet unless WRITER_UI_DEBUG is set
        if os.environ.get("WRITER_UI_DEBUG"):
            super().log_message(fmt, *args)

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

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url.query)
        if url.path in ("/", "/index.html"):
            if not UI_HTML.exists():
                return self._send(500, "ui/index.html missing", "text/plain")
            return self._send(200, UI_HTML.read_bytes(), "text/html; charset=utf-8")
        if url.path == "/api/health":
            return self._send(200, {"ok": True, "workspace": str(self.state.workspace), "pid": os.getpid(), "app": "writer"})
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

    def _serve_file(self, rel):
        root = self.state.workspace
        target = (root / rel).resolve()
        if root not in target.parents and target != root:
            return self._send(403, {"error": "outside workspace"})
        if not target.is_file():
            return self._send(404, {"error": "no such file"})
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        return self._send(200, target.read_bytes(), ctype)

    def _cli(self, req):
        op = req.get("op")
        st = self.state
        ops = {
            "meta": op_meta, "load": op_load, "focus": op_focus, "propose": op_propose, "ask": op_ask,
            "say": op_say, "apply": op_apply, "profile": op_profile, "cancel": op_cancel,
        }
        try:
            if op in ops:
                return self._send(200, st.mutate(lambda d: ops[op](d, req)))
            if op == "export":
                return self._send(200, {"ok": True, "written": export_files(st)})
            if op == "shutdown":
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return self._send(200, {"ok": True, "stopping": True})
        except KeyError as exc:
            return self._send(400, {"error": f"missing field {exc}"})
        return self._send(400, {"error": f"unknown op {op!r}"})

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
                        m for m in st.data["messages"]
                        if m["role"] == "user" and m.get("kind") == "message" and not m.get("delivered")
                    ]
                    result = None
                    if q and q["status"] in ("answered", "cancelled"):
                        result = {"status": q["status"], "question_id": qid, "kind": q.get("kind"), "answer": q.get("answer")}
                        q["delivered"] = True
                    elif new_msgs:
                        result = {"status": "message", "question_id": qid, "kind": q.get("kind") if q else None}
                    if result is not None:
                        result["messages"] = json.loads(json.dumps(new_msgs))
                        for m in new_msgs:
                            m["delivered"] = True
                        result["sentence"] = q.get("sentence") if q else st.data.get("current")
                        result["section"] = q["section"] if q else None
                        result["progress"] = progress(st.data)
                        st._bump()
                        return result
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return {"status": "pending", "question_id": qid, "messages": [], "progress": progress(st.data)}
                    st.cond.wait(remaining)
            finally:
                st.waiters -= 1
                if st.waiters == 0:
                    st.data["waiting"] = False
                    st._bump()

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
            _add_message(d, "user", q["section"], req.get("summary", ""), kind="answer", answer=q["answer"], delivered=True, sentence=q.get("sentence"))
            return {"ok": True}

        def message(d):
            sentence = req.get("sentence") or d.get("current")
            section = req.get("section") or _section_of(d, {"sentence": sentence})
            m = _add_message(d, "user", section, req.get("text", ""), sentence=sentence)
            return {"ok": True, "message_id": m["id"]}

        if op == "answer":
            return self._send(200, st.mutate(answer))
        if op == "message":
            return self._send(200, st.mutate(message))
        return self._send(400, {"error": f"unknown op {op!r}"})


def serve(workspace, port):
    Handler.state = WriterState(workspace)
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
        h = http(f"http://127.0.0.1:{port}/api/health", timeout=3)
        return h if h.get("app") == "writer" else None
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
        out({"ok": False, "error": "no running writer UI; run `writer_ui.py start --workspace <paper-stem>-revision`"}, 1)
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
        stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True, close_fds=True,
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
    nxt = next((s["id"] for s in state["sentences"] if s["status"] == "pending"), None)
    out(
        {
            "ok": True,
            "running": True,
            "url": info["url"],
            "workspace": info["workspace"],
            "title": state.get("title"),
            "current": state.get("current"),
            "next_pending": nxt,
            "progress": progress(state),
            "pending_question": pending[-1]["id"] if pending else None,
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
    if args.sections:
        payload["outline"] = [s.strip() for s in args.sections.split("|") if s.strip()]
    out(cli_call(info, payload))


def cmd_load(args):
    info = require_server(args)
    raw = json.loads(Path(args.sentences).read_text())
    if isinstance(raw, list):
        raw = {"sentences": raw}
    payload = {
        "op": "load",
        "sentences": raw.get("sentences", []),
        "sections": raw.get("sections"),
        "title": raw.get("title"),
        "format": raw.get("format"),
    }
    out(cli_call(info, payload, timeout=60))


def cmd_focus(args):
    info = require_server(args)
    out(cli_call(info, {"op": "focus", "id": args.id}))


def cmd_say(args):
    info = require_server(args)
    text = args.text if args.text is not None else Path(args.file).read_text()
    out(cli_call(info, {"op": "say", "section": args.section, "sentence": args.sentence, "text": text}))


def do_wait(info, qid, timeout):
    try:
        url = f"{info['url']}api/wait?timeout={timeout}" + (f"&id={qid}" if qid is not None else "")
        return http(url, timeout=timeout + 20)
    except (urllib.error.URLError, OSError) as exc:
        return {"status": "error", "error": str(exc), "question_id": qid}


def cmd_propose(args):
    info = require_server(args)
    options = []
    if args.options:
        raw = json.loads(Path(args.options).read_text())
        options = raw.get("options", raw) if isinstance(raw, dict) else raw
    else:
        notes = [n.strip() for n in (args.notes or "").split("|")] if args.notes else []
        for i, level in enumerate(LEVELS):
            text = getattr(args, level)
            if text:
                options.append({"level": level, "text": text, "note": notes[i] if i < len(notes) else ""})
    if not options:
        out({"ok": False, "error": "give --options opts.json or at least one of --light/--medium/--bold"}, 1)
    payload = {
        "op": "propose",
        "id": args.id,
        "options": options,
        "keep": not args.no_keep,
        "prompt": args.prompt,
        "text_label": args.text_label,
    }
    res = cli_call(info, payload)
    if not res.get("ok"):
        out(res, 1)
    qid = res.get("question_id")
    if args.no_wait:
        out({"ok": True, "question_id": qid, "sentence": args.id, "status": "pending"})
    out(do_wait(info, qid, args.timeout))


def cmd_ask(args):
    info = require_server(args)
    payload = {
        "op": "ask",
        "section": args.section,
        "sentence": args.sentence,
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


def cmd_apply(args):
    info = require_server(args)
    text = args.text
    if text is None and args.file:
        text = Path(args.file).read_text().strip()
    out(cli_call(info, {"op": "apply", "id": args.id, "status": args.status, "text": text, "choice": args.choice, "fixes": args.fixes}))


def cmd_profile(args):
    info = require_server(args)
    text = args.text if args.text is not None else Path(args.file).read_text()
    out(cli_call(info, {"op": "profile", "text": text}))


def cmd_export(args):
    info = require_server(args)
    out(cli_call(info, {"op": "export"}))


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--workspace", help="<paper-stem>-revision folder (defaults to the last started session)")
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
    sp.add_argument("--sections", help='pipe-separated titles, e.g. "Abstract|Introduction|Methods"')
    sp.set_defaults(fn=cmd_meta)

    sp = common(sub.add_parser("load", help="load the sentence list (segment.py output)"))
    sp.add_argument("--sentences", required=True, help="JSON from segment.py (title, sections, sentences)")
    sp.set_defaults(fn=cmd_load)

    sp = common(sub.add_parser("focus", help="highlight a sentence in the browser"))
    sp.add_argument("--id", required=True)
    sp.set_defaults(fn=cmd_focus)

    sp = common(sub.add_parser("propose", help="show rewrite options for a sentence and wait for the author"))
    sp.add_argument("--id", required=True, help="sentence id, e.g. S012")
    sp.add_argument("--options", help='JSON file: [{"level": "light", "text": "...", "note": "..."}, ...]')
    for level in LEVELS:
        sp.add_argument(f"--{level}", help=f"{level} rewrite text")
    sp.add_argument("--notes", help='pipe-separated notes for --light|--medium|--bold, e.g. "cuts filler|active voice|merges with next"')
    sp.add_argument("--prompt", help="short question shown above the options")
    sp.add_argument("--no-keep", action="store_true", help='omit the "Keep original" option')
    sp.add_argument("--text-label", help="label for the free-text box")
    sp.add_argument("--timeout", type=int, default=DEFAULT_WAIT)
    sp.add_argument("--no-wait", action="store_true")
    sp.set_defaults(fn=cmd_propose)

    sp = common(sub.add_parser("ask", help="show a generic decision card and wait"))
    sp.add_argument("--section")
    sp.add_argument("--sentence")
    sp.add_argument("--prompt", required=True)
    sp.add_argument("--options", help='pipe-separated choices, e.g. "Continue|Pause here"')
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

    sp = common(sub.add_parser("say", help="post a message from Claude into the thread"))
    sp.add_argument("--section")
    sp.add_argument("--sentence")
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--text")
    g.add_argument("--file")
    sp.set_defaults(fn=cmd_say)

    sp = common(sub.add_parser("apply", help="record the decision for a sentence (after editing working/)"))
    sp.add_argument("--id", required=True)
    sp.add_argument("--status", choices=["edited", "kept", "pending"], required=True)
    sp.add_argument("--text", help="final sentence text (required for edited)")
    sp.add_argument("--file", help="read the final text from this file instead")
    sp.add_argument("--choice", choices=["light", "medium", "bold", "other", "keep"])
    sp.add_argument("--fixes", help="what the edit fixed, one line")
    sp.set_defaults(fn=cmd_apply)

    sp = common(sub.add_parser("profile", help="show the style profile in the browser"))
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--file")
    g.add_argument("--text")
    sp.set_defaults(fn=cmd_profile)

    common(sub.add_parser("export", help="write artifact/changes.md and ui-transcript.md")).set_defaults(fn=cmd_export)
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
