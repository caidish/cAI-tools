#!/usr/bin/env python
"""Regression test for review_ui.py and tex_tools.py.

    python scripts/tests/test_review_ui.py            # API flow (stdlib only)
    python scripts/tests/test_review_ui.py --browser  # also drive the page with Playwright (chromium)

Uses a temporary workspace and a free port; leaves nothing behind.
"""
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
UI = SCRIPTS / "review_ui.py"
TEX = SCRIPTS / "tex_tools.py"
PORT = 8799

SAMPLE_TEX = r"""\documentclass{article}
\title{Sample \textbf{Paper}}
\begin{document}
\begin{abstract}
We measure a mobility of $10^5$ cm$^2$/Vs in graphene devices at four kelvin.
\end{abstract}
\section{Introduction}
Graphene has high mobility \cite{geim2007}. This is the first paragraph of the introduction.

Second paragraph with \emph{emphasis} and an inline $a_i^*$ symbol, long enough to count.
\begin{figure}
\includegraphics{images/fig1.png}
\caption{Device schematic showing $V_g$.}
\label{fig:one}
\end{figure}
\begin{equation}
E = \hbar \omega_c \label{eq:1}
\end{equation}
\section{Methods}
Methods paragraph describing the fabrication and measurement procedure in detail.
\appendix
\section{Derivations}
Appendix text.
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
        ws = Path(tmp) / "paper"
        (ws / "images").mkdir(parents=True)
        (ws / "images" / "fig1.png").write_bytes(bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8cfc0f01f0005000201d0"
            "2c92b90000000049454e44ae426082"))  # 1x1 PNG
        tex = ws / "main.tex"
        tex.write_text(SAMPLE_TEX)

        print("tex_tools")
        p = subprocess.run([sys.executable, str(TEX), "outline", str(tex), "--out", str(ws / "artifact/outline.json")], capture_output=True, text=True)
        outline = json.loads(p.stdout)
        titles = [s["title"] for s in outline["sections"]]
        check(outline["title"] == "Sample Paper", "title without formatting")
        check(titles == ["Abstract", "Introduction", "Methods", "Derivations"], f"sections {titles}")
        check([s["skip"] for s in outline["sections"]] == [False, False, False, True], "appendix flagged skip")
        check(outline["sections"][1]["paragraphs"] == 2 and outline["sections"][1]["figures"] == 1, "paragraph and figure counts")
        p = subprocess.run([sys.executable, str(TEX), "extract", str(tex), "--id", "02", "--out", str(ws / "artifact/sections/02-intro.md")], capture_output=True, text=True)
        md = (ws / "artifact/sections/02-intro.md").read_text()
        check("[cite: geim2007]" in md and "*emphasis*" in md and "$a_i^*$" in md, "inline conversion")
        check("\\begin{equation}" not in md and "E = \\hbar \\omega_c" in md, "equation body kept, env stripped")
        check(f"]({ws / 'images/fig1.png'})" in md or "](/private" + str(ws / "images/fig1.png") in md, "absolute figure path")
        md = md.replace("Graphene has", "Graphene [G: have] has").replace("symbol,", "symbol [?],")
        (ws / "artifact/sections/02-intro.md").write_text(md)

        print("review_ui")
        r = cli(ws, "start", "--port", str(PORT), "--no-open")
        check(r.get("ok"), f"start {r.get('url')}")
        url = r["url"]
        try:
            check(cli(ws, "meta", "--outline", str(ws / "artifact/outline.json"))["ok"], "meta")
            r = cli(ws, "section", "--id", "02", "--title", "Introduction", "--file", str(ws / "artifact/sections/02-intro.md"), "--figures", str(ws / "artifact/sections/02-intro.md.figures.json"))
            check(r["ok"], "section posted")
            state = json.loads(urllib.request.urlopen(url + "api/state?v=0&timeout=0").read())
            check("](/files/images/fig1.png)" in state["sections"]["02"]["markdown"], "absolute image path rewritten to /files/")
            check(urllib.request.urlopen(url + "files/images/fig1.png").status == 200, "figure served")
            q = cli(ws, "ask", "--prompt", "Clarity?", "--options", "Clear|Confusing", "--text-label", "Notes", "--no-wait")
            check(cli(ws, "wait", "--id", str(q["question_id"]), "--timeout", "1")["status"] == "pending", "wait times out as pending")
            browser_post(url, {"op": "message", "section": "02", "text": "What is omega_c?"})
            browser_post(url, {"op": "issue_add", "severity": "major", "section": "02", "location": "Eq. 1", "text": "unjustified"})
            r = cli(ws, "wait", "--id", str(q["question_id"]), "--timeout", "3")
            check(r["status"] == "message" and r["messages"][0]["text"] == "What is omega_c?", "chat message delivered")
            check(len(r["issues"]) == 1 and r["issues"][0]["severity"] == "major", "reviewer issue delivered with message")
            check(cli(ws, "say", "--text", "Cyclotron frequency.")["ok"], "say")
            browser_post(url, {"op": "answer", "question_id": q["question_id"], "answer": {"choice": "Clear", "choices": ["Clear"], "text": "", "values": {}}, "summary": "Clear"})
            r = cli(ws, "wait", "--timeout", "3")
            check(r["status"] == "answered" and r["answer"]["choice"] == "Clear", "answer delivered via wait without --id")
            check(cli(ws, "wait", "--timeout", "1")["status"] == "pending", "nothing left after delivery")
            cli(ws, "ask", "--prompt", "A", "--no-wait"); q3 = cli(ws, "ask", "--prompt", "B", "--no-wait")
            check(cli(ws, "wait", "--id", str(q3["question_id"] - 1), "--timeout", "1")["status"] == "cancelled", "older ask cancelled by newer")
            check(cli(ws, "issue", "--severity", "minor", "--text", "typo")["ok"], "claude issue")
            check(len(cli(ws, "issues")["issues"]) == 2, "issues listed")
            r = cli(ws, "export")
            check(len(r["written"]) == 3 and "unjustified" in (ws / "artifact/issues-major.md").read_text(), "export files")
            req = urllib.request.Request(url + "files/../../etc/passwd")
            try:
                urllib.request.urlopen(req); check(False, "traversal blocked")
            except urllib.error.HTTPError as e:
                check(e.code in (403, 404), "traversal blocked")
            if with_browser:
                browser_check(url, ws)
        finally:
            r = cli(ws, "stop")
            check(r["ok"], "stop")
        r = cli(ws, "start", "--port", str(PORT), "--no-open")
        try:
            check(cli(ws, "status")["current"] == "02", "state resumed after restart")
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
        page.wait_for_selector(".sec-head h2:has-text('Introduction')", timeout=15000)
        page.wait_for_timeout(1500)
        check(page.locator(".doc .katex").count() >= 2, "KaTeX rendered")
        check(page.locator(".doc .mk-G").count() == 1 and page.locator(".doc .mk-Q").count() == 1, "markers rendered")
        check(page.evaluate("() => document.querySelector('.doc img').naturalWidth") == 1, "figure loaded")
        check(page.locator(".qcard").count() == 1, "pending card visible")
        q = cli(ws, "ask", "--prompt", "Rate it", "--options", "Good|Bad", "--no-wait")
        page.wait_for_selector(".qcard .opt", timeout=5000)
        page.click(".qcard .btn.primary")
        page.wait_for_timeout(300)
        check(page.locator(".toast.on").count() == 1, "empty submit rejected when options exist")
        page.click(".qcard .opt:has-text('Bad')")
        page.click(".qcard .btn.primary")
        r = cli(ws, "wait", "--id", str(q["question_id"]), "--timeout", "5")
        check(r["status"] == "answered" and r["answer"]["choice"] == "Bad", "card submit reaches the CLI")
        page.click(".doc .mk-Q")
        check("[?]" in page.input_value("#i-text"), "marker prefills issue form")
        b.close()
    check(not errors, f"no console errors {errors}")


if __name__ == "__main__":
    main()
