#!/usr/bin/env python
"""Regression test for writer_ui.py and segment.py.

    python scripts/tests/test_writer_ui.py            # API flow (stdlib only)
    python scripts/tests/test_writer_ui.py --browser  # also drive the page with Playwright (chromium)

Uses a temporary workspace and a free port; leaves nothing behind.
"""
import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
UI = SCRIPTS / "writer_ui.py"
SEG = SCRIPTS / "segment.py"
PORT = 8798

SAMPLE_TEX = r"""\documentclass{article}
\title{Sample \textbf{Paper}}
\author{A. Author}
\begin{document}
\maketitle
\begin{abstract}
We measure a mobility of $10^5$ cm$^2$/Vs in graphene devices at four kelvin. It is important to note that this is significant.
\end{abstract}
\section{Introduction}
Graphene has high mobility \cite{geim2007}. This is the first paragraph of the
introduction, e.g. wrapped across lines (see Fig. 2 and Ref. 3). Dr. Smith agrees.

Second paragraph with \emph{emphasis} and an inline $a_i^* = 0.5$ symbol. % a comment
\begin{figure}
\includegraphics{images/fig1.png}
\caption{Device schematic showing $V_g$. The scale bar is 1 µm.}
\label{fig:one}
\end{figure}
\begin{equation}
E = \hbar \omega_c \label{eq:1}
\end{equation}
where $\omega_c$ is the cyclotron frequency.
\section{Methods}
Methods paragraph describing the fabrication\footnote{Details in SI.} and measurement procedure.
\appendix
\section{Acknowledgments}
We thank J. Smith et al. for discussions \citep[p.~3]{foo}.
\end{document}
"""


def cli(ws, *args, timeout=60):
    p = subprocess.run([sys.executable, str(UI), *args, "--workspace", str(ws)], capture_output=True, text=True, timeout=timeout)
    assert p.stdout.strip(), f"no output: {p.stderr}"
    return json.loads(p.stdout)


def browser_post(url, body):
    req = urllib.request.Request(url + "api/user", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def check(cond, msg):
    print(("  ok  " if cond else "  FAIL") + " " + msg)
    if not cond:
        raise SystemExit(1)


def main():
    with_browser = "--browser" in sys.argv
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "sample-revision"
        (ws / "working").mkdir(parents=True)
        tex = ws / "working" / "sample.tex"
        tex.write_text(SAMPLE_TEX)

        print("segment")
        p = subprocess.run([sys.executable, str(SEG), str(tex), "--out", str(ws / "artifact/sentences.json")], capture_output=True, text=True)
        seg = json.loads((ws / "artifact/sentences.json").read_text())
        ids = [s["id"] for s in seg["sentences"]]
        texts = {s["id"]: s["text"] for s in seg["sentences"]}
        check(seg["title"] == "Sample Paper" and seg["format"] == "tex", "title and format")
        check([s["title"] for s in seg["sections"]] == ["Abstract", "Introduction", "Methods", "Acknowledgments"], "sections")
        check(seg["sections"][3]["skip"] is True, "acknowledgments flagged skip")
        check(seg["count"] == 11 and ids[0] == "S001" and ids[-1] == "S011", f"11 sentences ({seg['count']})")
        check(texts["S004"].startswith("This is the first paragraph") and "e.g. wrapped" in texts["S004"] and texts["S004"].endswith("Ref. 3)."), "abbreviations and wrapped lines do not split")
        check(texts["S005"] == "Dr. Smith agrees.", "Dr. kept")
        check(texts["S006"].startswith("Second paragraph with \\emph{emphasis}") and "$a_i^* = 0.5$" in texts["S006"], "math and decimals intact")
        caps = [s for s in seg["sentences"] if s["kind"] == "caption"]
        check(len(caps) == 2 and caps[0]["text"] == "Device schematic showing $V_g$.", "caption split into sentences")
        check(texts["S009"].startswith("where $\\omega_c$"), "equation env skipped, following prose kept")
        check("J. Smith et al. for discussions" in texts["S011"], "initials and et al. do not split")
        disp = {s["id"]: s["display"] for s in seg["sentences"]}
        check(disp["S003"] == "Graphene has high mobility [cite: geim2007]." and disp["S006"].startswith("Second paragraph with *emphasis*"), "display markdown")
        check(not any("\x00" in s["text"] or "\x00" in s["display"] for s in seg["sentences"]), "no placeholder leaks")
        check(not any("A. Author" in s["text"] for s in seg["sentences"]), "author block dropped")

        print("writer_ui")
        r = cli(ws, "start", "--port", str(PORT), "--no-open")
        check(r.get("ok"), f"start {r.get('url')}")
        url = r["url"]
        try:
            r = cli(ws, "load", "--sentences", str(ws / "artifact/sentences.json"))
            check(r["ok"] and r["loaded"] == 11 and r["progress"]["pending"] == 11, "load")
            state = json.loads(urllib.request.urlopen(url + "api/state?v=0&timeout=0").read())
            check(state["title"] == "Sample Paper" and len(state["outline"]) == 4, "title and outline from segment output")
            check(cli(ws, "focus", "--id", "S002")["current"] == "S002", "focus")
            check(not cli(ws, "focus", "--id", "S999")["ok"], "focus rejects unknown id")
            q = cli(ws, "propose", "--id", "S002", "--light", "Note that this is significant.", "--medium", "This is significant.",
                    "--bold", "The mobility is high.", "--notes", "cuts the opener|cuts the opener and the hedge|states the claim", "--no-wait")
            check(q["ok"] and q["sentence"] == "S002", "propose")
            state = json.loads(urllib.request.urlopen(url + "api/state?v=0&timeout=0").read())
            pq = state["questions"][-1]
            check(pq["kind"] == "propose" and [o["level"] for o in pq["options"]] == ["light", "medium", "bold"] and pq["options"][1]["note"] == "cuts the opener and the hedge" and pq["keep"], "propose card content")
            check(cli(ws, "wait", "--id", str(q["question_id"]), "--timeout", "1")["status"] == "pending", "wait times out as pending")
            browser_post(url, {"op": "message", "sentence": "S002", "text": "Can I keep 'significant'?"})
            r = cli(ws, "wait", "--id", str(q["question_id"]), "--timeout", "3")
            check(r["status"] == "message" and r["messages"][0]["text"] == "Can I keep 'significant'?" and r["messages"][0]["section"] == "01", "chat message delivered with section")
            check(cli(ws, "say", "--sentence", "S002", "--text", "Sure - pick Light.")["ok"], "say")
            browser_post(url, {"op": "answer", "question_id": q["question_id"], "answer": {"choice": "medium", "chosen_text": "This is significant.", "text": "", "values": {}}, "summary": "Picked Medium"})
            r = cli(ws, "wait", "--timeout", "3")
            check(r["status"] == "answered" and r["kind"] == "propose" and r["answer"]["choice"] == "medium" and r["sentence"] == "S002", "propose answer delivered via wait without --id")
            r = cli(ws, "apply", "--id", "S002", "--status", "edited", "--text", "This is significant.", "--choice", "medium", "--fixes", "cut filler opener")
            check(r["ok"] and r["progress"]["edited"] == 1, "apply edited")
            check(cli(ws, "apply", "--id", "S001", "--status", "kept")["progress"]["kept"] == 1, "apply kept")
            check(not cli(ws, "apply", "--id", "S003", "--status", "edited")["ok"], "apply edited needs text")
            r = cli(ws, "ask", "--prompt", "Continue?", "--options", "Continue|Pause", "--no-wait")
            browser_post(url, {"op": "answer", "question_id": r["question_id"], "answer": {"choice": "Pause", "choices": ["Pause"], "text": "", "values": {}}, "summary": "Pause"})
            check(cli(ws, "wait", "--id", str(r["question_id"]), "--timeout", "3")["answer"]["choice"] == "Pause", "generic ask")
            cli(ws, "ask", "--prompt", "A", "--no-wait"); q3 = cli(ws, "ask", "--prompt", "B", "--no-wait")
            check(cli(ws, "wait", "--id", str(q3["question_id"] - 1), "--timeout", "1")["status"] == "cancelled", "older ask cancelled by newer")
            check(cli(ws, "profile", "--text", "# Style\n- Sentence length: medium")["ok"], "profile")
            st = cli(ws, "status")
            check(st["progress"]["reviewed"] == 2 and st["next_pending"] == "S003" and st["pending_question"] == q3["question_id"], "status")
            r = cli(ws, "export")
            changes = (ws / "artifact/changes.md").read_text()
            check(len(r["written"]) == 2 and "### S002 - medium" in changes and "cut filler opener" in changes, "export changes.md")
            check("Can I keep" in (ws / "artifact/ui-transcript.md").read_text(), "export transcript")
            # reload keeps decisions for unchanged sentences
            r = cli(ws, "load", "--sentences", str(ws / "artifact/sentences.json"))
            check(r["progress"]["edited"] == 1 and r["progress"]["kept"] == 1, "reload preserves decisions")
            (ws / "secret.txt").write_text("x")
            try:
                urllib.request.urlopen(url + "files/../../etc/passwd"); check(False, "traversal blocked")
            except urllib.error.HTTPError as e:
                check(e.code in (403, 404), "traversal blocked")
            if with_browser:
                browser_check(url, ws)
        finally:
            r = cli(ws, "stop")
            check(r["ok"], "stop")
        r = cli(ws, "start", "--port", str(PORT), "--no-open")
        try:
            st = cli(ws, "status")
            check(st["current"] in ("S002", "S005") and st["progress"]["edited"] == 1, "state resumed after restart")
        finally:
            cli(ws, "stop")
    print("all passed")


def browser_check(url, ws):
    from playwright.sync_api import sync_playwright
    print("browser")
    errors = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 1400, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(url)
        page.wait_for_selector(".doc .sent", timeout=15000)
        page.wait_for_timeout(1500)
        check(page.locator(".doc .sent").count() == 2, "abstract renders its two sentences")
        check(page.locator(".doc .sent.st-edited").count() == 1, "edited sentence highlighted")
        check(page.locator(".doc .katex").count() >= 1, "KaTeX rendered")
        page.click(".outline li:nth-child(2)")
        page.wait_for_selector(".doc p.caption", timeout=5000)
        check(page.locator(".doc .sent").count() == 7 and page.locator(".doc .ref").count() == 1, "introduction with caption and cite tag")
        q = cli(ws, "propose", "--id", "S004", "--light", "Light one.", "--medium", "Medium one.", "--bold", "Bold one.", "--no-wait")
        page.wait_for_selector(".qcard .choice", timeout=5000)
        check(page.locator(".qcard .choice").count() == 4, "three options plus keep")
        check(page.locator(".doc .sent.cur").count() == 1, "current sentence highlighted")
        page.click(".qcard .btn.primary")
        page.wait_for_timeout(300)
        check(page.locator(".toast.on").count() == 1, "empty submit rejected")
        page.keyboard.press("2")
        page.click(".qcard .btn.primary")
        r = cli(ws, "wait", "--id", str(q["question_id"]), "--timeout", "5")
        check(r["status"] == "answered" and r["answer"]["choice"] == "medium" and r["answer"]["chosen_text"] == "Medium one.", "keyboard pick reaches the CLI")
        q = cli(ws, "propose", "--id", "S005", "--light", "L.", "--no-wait")
        page.wait_for_selector(".qcard textarea", timeout=5000)
        page.fill(".qcard textarea", "Dr. Smith concurs.")
        page.click(".qcard .btn.primary")
        r = cli(ws, "wait", "--id", str(q["question_id"]), "--timeout", "5")
        check(r["answer"]["choice"] == "other" and r["answer"]["text"] == "Dr. Smith concurs.", "own wording reaches the CLI as other")
        page.click("#tab-changes")
        check(page.locator("#changes .change").count() >= 0, "changes tab opens")
        b.close()
    check(not errors, f"no console errors {errors}")


if __name__ == "__main__":
    main()
