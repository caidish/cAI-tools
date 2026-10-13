#!/usr/bin/env python
"""Split a paper (.tex / .md / .txt) into reviewable prose sentences with stable ids.

  python segment.py <paper> [--out artifact/sentences.json]

Prints (and optionally writes) one JSON object:

  {"title": "...", "source": "<path>", "format": "tex|md|txt", "count": N,
   "sections":  [{"id": "02", "title": "Introduction", "level": 1, "skip": false}, ...],
   "sentences": [{"id": "S001", "section": "01", "para": 1, "kind": "prose|caption",
                  "line": 12, "text": "<source text, whitespace-normalised>",
                  "display": "<Markdown for the browser>"}, ...]}

Rules (see ../references/segmentation.md): preamble, math environments, tables, code,
comments, bibliography and bare commands are skipped; figure/table captions are kept;
`\\cite`, `\\ref` and math stay inside their sentence untouched. `text` is joined with single
spaces, so when you Edit the working copy match on a distinctive phrase, not on the
whole string, if the source wraps lines. The heuristic is deliberately simple: fix the
odd bad split in the JSON by hand before loading it into the UI.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ABBREV = [
    "e.g.", "i.e.", "et al.", "cf.", "vs.", "viz.", "ca.", "approx.", "resp.", "etc.",
    "Fig.", "Figs.", "Eq.", "Eqs.", "Eqn.", "Ref.", "Refs.", "Sec.", "Secs.", "Tab.", "Ch.",
    "Thm.", "Lem.", "Cor.", "Def.", "Prop.", "Dr.", "Prof.", "Mr.", "Ms.", "Mrs.", "St.",
    "No.", "Nos.", "vol.", "pp.", "p.", "Vol.", "Univ.", "Inc.", "Ltd.", "Jr.", "Sr.",
]
MATH_ENVS = {
    "equation", "equation*", "align", "align*", "alignat", "alignat*", "gather", "gather*",
    "multline", "multline*", "eqnarray", "eqnarray*", "displaymath", "math", "flalign", "flalign*",
    "subequations",
}
SKIP_ENVS = MATH_ENVS | {
    "tabular", "tabular*", "tabularx", "longtable", "verbatim", "lstlisting", "minted", "tikzpicture",
    "thebibliography", "algorithm", "algorithmic", "algorithm2e", "comment", "filecontents", "pgfpicture",
}
CAPTION_ENVS = {"figure", "figure*", "table", "table*", "wrapfigure", "sidewaysfigure", "subfigure"}
LIST_ENVS = {"itemize", "enumerate", "description"}
SECTION_RE = re.compile(r"^\s*\\(section|subsection|subsubsection|chapter|paragraph)\*?\s*(?:\[[^\]]*\])?\s*\{")
SKIP_TITLE = re.compile(r"appendix|supplement|acknowledg|references|bibliography|author contributions|competing interests|data availability", re.I)
BARE_CMD_RE = re.compile(
    r"^\s*\\(maketitle|tableofcontents|newpage|clearpage|centering|label|vspace\*?|hspace\*?|bibliography|bibliographystyle|"
    r"appendix|noindent|medskip|smallskip|bigskip|linenumbers|nolinenumbers|input|include|setcounter|addtocounter|"
    r"includegraphics|onecolumngrid|twocolumngrid|date|affiliation|author|email|keywords|pacs|hline|toprule|midrule|bottomrule|"
    r"printbibliography|balance|end\{document\}|begin\{document\}|documentclass|usepackage|newcommand|renewcommand|def)\b"
)
DROP_CMDS = ["footnotetext", "thanks", "affiliation", "author", "email", "date", "keywords", "pacs", "orcid", "address", "altaffiliation"]
LEVEL = {"chapter": 0, "section": 1, "subsection": 2, "subsubsection": 3, "paragraph": 4}


# --------------------------------------------------------------------------- LaTeX helpers


def strip_comments(line):
    out, i = [], 0
    while i < len(line):
        if line[i] == "\\" and i + 1 < len(line):
            out.append(line[i:i + 2]); i += 2; continue
        if line[i] == "%":
            break
        out.append(line[i]); i += 1
    return "".join(out)


def brace_content(text, start):
    """(content, index after the closing brace) for the {...} group whose '{' is at text[start]."""
    depth, i = 0, start
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2; continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
        i += 1
    return text[start + 1:], len(text)


def find_title(text):
    m = re.search(r"\\title\s*(?:\[[^\]]*\])?\s*\{", text)
    if not m:
        return ""
    raw, _ = brace_content(text, m.end() - 1)
    return re.sub(r"[*_`]+", "", re.sub(r"\s+", " ", to_display(raw))).strip()


def protect_math(text):
    slots = []

    def keep(m):
        slots.append(m.group(0))
        return f"\x00{len(slots) - 1}\x00"

    text = re.sub(r"\$\$[\s\S]+?\$\$", keep, text)
    text = re.sub(r"\\\[[\s\S]+?\\\]", keep, text)
    text = re.sub(r"\\\([\s\S]+?\\\)", keep, text)
    text = re.sub(r"(?<!\\)\$(?:\\.|[^$])+?\$", keep, text)
    return text, slots


def restore(text, slots):
    """Put protected spans back; loops because a protected span may itself hold placeholders."""
    pat = re.compile(r"\x00(\d+)\x00")
    for _ in range(10):
        if not pat.search(text):
            break
        text = pat.sub(lambda m: slots[int(m.group(1))], text)
    return text


def _replace_cmd(text, names, fn):
    """Replace \\name[opt]{arg} (balanced braces) with fn(name, opt, arg)."""
    pat = re.compile(r"\\(" + "|".join(re.escape(n) for n in names) + r")\*?\s*(\[[^\]]*\])?\s*\{")
    out, pos = [], 0
    while True:
        m = pat.search(text, pos)
        if not m:
            out.append(text[pos:]); break
        arg, end = brace_content(text, m.end() - 1)
        out.append(text[pos:m.start()])
        out.append(fn(m.group(1), (m.group(2) or "")[1:-1], arg))
        pos = end
    return "".join(out)


def to_display(text):
    """Rough Markdown for one LaTeX prose snippet (math kept verbatim for KaTeX)."""
    text, slots = protect_math(text)
    for _ in range(3):  # nested formatting
        text = _replace_cmd(text, ["emph", "textit", "textsl"], lambda n, o, a: f"*{a}*")
        text = _replace_cmd(text, ["textbf"], lambda n, o, a: f"**{a}**")
        text = _replace_cmd(text, ["texttt", "verb"], lambda n, o, a: f"`{a}`")
        text = _replace_cmd(text, ["textsc", "textrm", "textsf", "textnormal", "mbox", "text", "underline", "textsuperscript", "textsubscript"], lambda n, o, a: a)
    text = _replace_cmd(text, ["cite", "citep", "citet", "citealp", "citeauthor", "citeyear", "onlinecite", "parencite", "textcite", "autocite"],
                        lambda n, o, a: f"[cite: {a.strip()}]" + (f" ({o})" if o else ""))
    text = _replace_cmd(text, ["ref", "eqref", "autoref", "cref", "Cref", "pageref", "nameref"], lambda n, o, a: f"[ref: {a.strip()}]")
    text = _replace_cmd(text, ["footnote"], lambda n, o, a: f" (footnote: {a.strip()})")
    text = _replace_cmd(text, ["url", "href"], lambda n, o, a: a)
    text = _replace_cmd(text, ["label", "index", "vspace", "hspace", "phantom"], lambda n, o, a: "")
    text = re.sub(r"\\\\\*?(\[[^\]]*\])?", " ", text)
    text = text.replace("~", " ").replace("\\,", " ").replace("\\;", " ").replace("\\!", "").replace("\\ ", " ")
    text = re.sub(r"\\([&%_#{}])", r"\1", text)
    text = re.sub(r"``|''", '"', text).replace("`", "'")
    for _ in range(2):  # unknown \cmd{arg} -> arg ; bare \cmd -> ''
        text = re.sub(r"\\[A-Za-z]+\*?\s*\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\[A-Za-z]+\*?", "", text)
    text = restore(text, slots)
    return re.sub(r"[ \t]+", " ", text).strip()


# --------------------------------------------------------------------------- sentence splitting


def split_sentences(text):
    """Split one paragraph into sentences; math, citations and abbreviations never split."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    protected, slots = protect_math(text)

    def keep(m):
        slots.append(m.group(0))
        return f"\x00{len(slots) - 1}\x00"

    protected = re.sub(r"\\[A-Za-z]+\*?\s*(\[[^\]]*\])?\s*\{[^{}]*\}", keep, protected)  # \cite{...}, \ref{...}
    for ab in ABBREV:  # e.g. -> e\x01g\x01 (no split inside)
        protected = re.sub(r"(?<![A-Za-z])" + re.escape(ab), ab.replace(".", "\x01"), protected)
    protected = re.sub(r"(?<=\b[A-Z])\.(?= )", "\x01", protected)  # initials: "J. Smith"
    protected = re.sub(r"\.\.\.", "\x01\x01\x01", protected)
    protected = re.sub(r"(?<=\d)\.(?=\d)", "\x01", protected)
    out, start = [], 0
    for m in re.finditer(r"[.?!][)\]\"'”’]*\s+(?=[\"'“‘(\[]?[A-Z\\$\x00])", protected):
        out.append(protected[start:m.end()].strip())
        start = m.end()
    tail = protected[start:].strip()
    if tail:
        out.append(tail)
    return [restore(s.replace("\x01", "."), slots) for s in out if s]


# --------------------------------------------------------------------------- per-format walkers


class Collector:
    def __init__(self, fmt):
        self.fmt = fmt
        self.sections = []
        self.sentences = []
        self.para = 0

    def add_section(self, title, level=1):
        sid = f"{len(self.sections) + 1:02d}"
        self.sections.append({"id": sid, "title": title, "level": level, "skip": bool(SKIP_TITLE.search(title))})
        return sid

    def current_section(self):
        if not self.sections:
            self.add_section("Body")
        return self.sections[-1]["id"]

    def add_paragraph(self, text, line, kind="prose"):
        if self.fmt == "tex":
            text = _replace_cmd(text, DROP_CMDS, lambda n, o, a: "")
        sents = split_sentences(text)
        if not sents:
            return
        self.para += 1
        sid = self.current_section()
        for s in sents:
            self.sentences.append({
                "id": f"S{len(self.sentences) + 1:03d}",
                "section": sid,
                "para": self.para,
                "kind": kind,
                "line": line,
                "text": s,
                "display": to_display(s) if self.fmt == "tex" else s,
            })


def walk_tex(raw):
    col = Collector("tex")
    title = find_title(raw)
    lines = [strip_comments(l) for l in raw.split("\n")]
    body_start = next((i for i, l in enumerate(lines) if re.match(r"^\s*\\begin\{document\}", l)), -1) + 1
    buf, buf_line = [], None
    skip_env = None  # name of the environment being skipped
    cap_env = None  # inside figure/table: collect captions only

    def flush():
        nonlocal buf, buf_line
        if buf:
            col.add_paragraph(" ".join(buf), buf_line)
        buf, buf_line = [], None

    i = body_start
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if re.match(r"^\s*\\end\{document\}", line):
            break
        if skip_env:
            if re.match(r"^\s*\\end\{" + re.escape(skip_env) + r"\}", line):
                skip_env = None
            i += 1; continue
        if cap_env:
            if re.match(r"^\s*\\end\{" + re.escape(cap_env) + r"\}", line):
                cap_env = None
            else:
                m = re.search(r"\\caption\*?\s*(\[[^\]]*\])?\s*\{", line)
                if m:
                    rest = "\n".join(lines[i:])
                    off = m.end() - 1
                    cap, end = brace_content(rest, off)
                    col.add_paragraph(re.sub(r"\s+", " ", cap), i + 1, kind="caption")
                    i += rest[:end].count("\n")
            i += 1; continue
        m = re.match(r"^\s*\\begin\{([A-Za-z*]+)\}", line)
        if m:
            env = m.group(1)
            if env == "abstract":
                flush(); col.add_section("Abstract", 1)
            elif env in SKIP_ENVS:
                flush(); skip_env = env
            elif env in CAPTION_ENVS:
                flush(); cap_env = env
            elif env in LIST_ENVS:
                flush()
            else:
                pass  # unknown environment: treat its contents as prose
            i += 1; continue
        if re.match(r"^\s*\\end\{([A-Za-z*]+)\}", line):
            flush(); i += 1; continue
        m = SECTION_RE.match(line)
        if m:
            flush()
            rest = "\n".join(lines[i:])
            t, end = brace_content(rest, m.end() - 1)
            col.add_section(to_display(t) or "(untitled)", LEVEL.get(m.group(1), 1))
            i += rest[:end].count("\n") + 1; continue
        if re.match(r"^\s*\\appendix\b", line):
            flush(); i += 1; continue
        if not s:
            flush(); i += 1; continue
        if BARE_CMD_RE.match(line) and not re.search(r"[A-Za-z]{3,}\s+[A-Za-z]{3,}", re.sub(r"\\[A-Za-z]+(\{[^}]*\})?", "", line)):
            flush(); i += 1; continue
        s = re.sub(r"^\\item\s*(\[[^\]]*\])?\s*", "", s)
        if s.startswith("\\item") or not s:
            i += 1; continue
        if buf_line is None:
            buf_line = i + 1
        buf.append(s)
        i += 1
    flush()
    return title, col


def walk_md(raw):
    col = Collector("md")
    lines = raw.split("\n")
    i, buf, buf_line, title = 0, [], None, ""
    if lines and lines[0].strip() == "---":  # YAML front matter
        j = next((k for k in range(1, len(lines)) if lines[k].strip() == "---"), None)
        if j is not None:
            fm = "\n".join(lines[1:j])
            m = re.search(r"^title:\s*(.+)$", fm, re.M)
            title = m.group(1).strip().strip("\"'") if m else ""
            i = j + 1

    def flush():
        nonlocal buf, buf_line
        if buf:
            col.add_paragraph(" ".join(buf), buf_line)
        buf, buf_line = [], None

    in_fence = False
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("```") or s.startswith("~~~"):
            flush(); in_fence = not in_fence; i += 1; continue
        if in_fence:
            i += 1; continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush()
            if m.group(1) == "#" and not title:
                title = m.group(2).strip()
            col.add_section(m.group(2).strip().rstrip("#").strip(), len(m.group(1)))
            i += 1; continue
        if not s or s.startswith("|") or re.match(r"^(-{3,}|\*{3,}|_{3,})$", s) or s.startswith("<!--") or re.match(r"^!\[", s):
            flush(); i += 1; continue
        if re.match(r"^\$\$", s):  # display math block
            flush()
            if not (s.endswith("$$") and len(s) > 2):
                i += 1
                while i < len(lines) and "$$" not in lines[i]:
                    i += 1
            i += 1; continue
        s = re.sub(r"^([-*+]|\d+[.)])\s+", "", s)
        s = re.sub(r"^>\s?", "", s)
        if buf_line is None:
            buf_line = i + 1
        buf.append(s)
        i += 1
    flush()
    return title, col


def walk_txt(raw):
    col = Collector("txt")
    buf, buf_line = [], None
    for n, line in enumerate(raw.split("\n"), 1):
        s = line.strip()
        if not s:
            if buf:
                col.add_paragraph(" ".join(buf), buf_line)
            buf, buf_line = [], None
            continue
        if buf_line is None:
            buf_line = n
        buf.append(s)
    if buf:
        col.add_paragraph(" ".join(buf), buf_line)
    return "", col


def segment(path):
    path = Path(path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    ext = path.suffix.lower()
    fmt = "tex" if ext == "tex" or ext == ".tex" else "md" if ext in (".md", ".markdown") else "txt"
    title, col = {"tex": walk_tex, "md": walk_md, "txt": walk_txt}[fmt](raw)
    return {
        "title": title or path.stem,
        "source": str(path),
        "format": fmt,
        "count": len(col.sentences),
        "sections": col.sections,
        "sentences": col.sentences,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paper")
    p.add_argument("--out", help="write the JSON here as well (folders created)")
    args = p.parse_args()
    if not Path(args.paper).exists():
        print(json.dumps({"ok": False, "error": f"{args.paper} not found"}))
        sys.exit(1)
    result = segment(args.paper)
    text = json.dumps(result, indent=1, ensure_ascii=False)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n")
        result_short = dict(result)
        result_short["sentences"] = f"<{result['count']} sentences written to {out}>"
        print(json.dumps(result_short, indent=1, ensure_ascii=False))
    else:
        print(text)


if __name__ == "__main__":
    main()
