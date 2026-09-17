#!/usr/bin/env python
"""LaTeX helpers for the paper review workflow. Prints JSON (outline) or writes Markdown (extract).

  outline  python tex_tools.py outline <paper.tex> [--out artifact/outline.json]
           -> {"title": ..., "sections": [{"id","title","level","start","end","paragraphs","figures":[...],"skip"}]}
  extract  python tex_tools.py extract <paper.tex> --id 02 --out artifact/sections/02-introduction.md
           -> rough Markdown of that section (math kept, \\cite -> [cite], figures -> images) plus
              <out>.figures.json listing the figures found in the section.

Section ids are zero-padded positions in the outline (01, 02, ...). Appendix and
supplementary sections are flagged "skip": true. Line numbers are 1-based and inclusive.
"""

import argparse
import json
import re
import sys
from pathlib import Path

SECTION_RE = re.compile(r"^\s*\\(section|subsection|subsubsection)\*?\s*(?:\[[^\]]*\])?\s*\{(.*)\}\s*$")
ABSTRACT_BEGIN = re.compile(r"^\s*\\begin\{abstract\}")
ABSTRACT_END = re.compile(r"^\s*\\end\{abstract\}")
APPENDIX_RE = re.compile(r"^\s*\\appendix\b")
END_DOC = re.compile(r"^\s*\\end\{document\}")
BIB_RE = re.compile(r"^\s*\\(bibliography|printbibliography|begin\{thebibliography\})")
SKIP_TITLE = re.compile(r"appendix|supplement|acknowledg|references|bibliography", re.I)
LEVEL = {"section": 1, "subsection": 2, "subsubsection": 3}


def brace_content(text, start):
    """Return (content, end_index) for the {...} group starting at text[start] == '{'."""
    depth, i = 0, start
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
        i += 1
    return text[start + 1:], len(text)


def strip_comments(line):
    out, i = [], 0
    while i < len(line):
        if line[i] == "\\" and i + 1 < len(line):
            out.append(line[i:i + 2]); i += 2; continue
        if line[i] == "%":
            break
        out.append(line[i]); i += 1
    return "".join(out)


def find_title(lines):
    text = "\n".join(lines)
    m = re.search(r"\\title\s*(?:\[[^\]]*\])?\s*\{", text)
    if not m:
        return ""
    content, _ = brace_content(text, m.end() - 1)
    return re.sub(r"[*`]", "", clean_inline(content)).strip()


def figures_in(block):
    figs = []
    for m in re.finditer(r"\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}", block, re.S):
        body = m.group(1)
        paths = re.findall(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", body)
        cap = ""
        cm = re.search(r"\\caption\s*(?:\[[^\]]*\])?\s*\{", body)
        if cm:
            cap, _ = brace_content(body, cm.end() - 1)
        lab = re.search(r"\\label\{([^}]*)\}", body)
        figs.append({"paths": paths, "caption": clean_inline(cap).strip(), "label": lab.group(1) if lab else ""})
    return figs


def count_paragraphs(block):
    text = re.sub(r"\\begin\{(figure|table|equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{\1\*?\}", "", block, flags=re.S)
    text = re.sub(r"\\[A-Za-z]+\*?(\[[^\]]*\])?(\{[^}]*\})*", " ", text)  # drop commands, keep prose
    paras = [p for p in re.split(r"\n\s*\n", text) if len(re.sub(r"[^A-Za-z]", "", p)) >= 20]
    return len(paras)


def outline(tex_path):
    raw = Path(tex_path).read_text(errors="replace").splitlines()
    lines = [strip_comments(l) for l in raw]
    sections, in_appendix, abstract_open = [], False, None
    end_line = len(lines)
    for n, line in enumerate(lines, 1):
        if END_DOC.match(line):
            end_line = n - 1
            break
        if ABSTRACT_BEGIN.match(line):
            abstract_open = {"title": "Abstract", "level": 1, "start": n}
            continue
        if ABSTRACT_END.match(line) and abstract_open:
            abstract_open["end"] = n
            sections.append(abstract_open); abstract_open = None
            continue
        if APPENDIX_RE.match(line):
            in_appendix = True
            continue
        m = SECTION_RE.match(line)
        if m:
            title = clean_inline(m.group(2)).strip()
            sections.append({"title": title, "level": LEVEL[m.group(1)], "start": n, "skip": in_appendix or bool(SKIP_TITLE.search(title))})
            continue
        if BIB_RE.match(line) and sections and "end" not in sections[-1]:
            sections[-1]["end"] = n - 1
            sections.append({"title": "References", "level": 1, "start": n, "skip": True})
    for i, s in enumerate(sections):
        if "end" not in s:
            nxt = sections[i + 1]["start"] - 1 if i + 1 < len(sections) else end_line
            s["end"] = max(nxt, s["start"])
    for i, s in enumerate(sections, 1):
        block = "\n".join(lines[s["start"] - 1:s["end"]])
        s["id"] = f"{i:02d}"
        s["paragraphs"] = count_paragraphs(block)
        s["figures"] = figures_in(block)
        s.setdefault("skip", False)
    return {"title": find_title(lines), "file": str(Path(tex_path).resolve()), "sections": sections}


# ---------------------------------------------------------------- LaTeX -> Markdown (rough)

SIMPLE_CMDS = {
    "textbf": "**{}**", "bf": "**{}**", "emph": "*{}*", "textit": "*{}*", "it": "*{}*",
    "texttt": "`{}`", "underline": "{}", "textsc": "{}", "textrm": "{}", "textsf": "{}",
    "mbox": "{}", "hbox": "{}", "text": "{}", "textsuperscript": "^{}", "textsubscript": "_{}",
    "footnote": " (footnote: {})", "url": "<{}>", "href": "{}",
}


def clean_inline(text):
    """Convert inline LaTeX commands to Markdown; leaves math untouched."""
    out, i = [], 0
    while i < len(text):
        if text[i] == "\\":
            m = re.match(r"\\([A-Za-z]+)\*?", text[i:])
            if m:
                name = m.group(1)
                j = i + m.end()
                if name in ("cite", "citep", "citet", "citealp", "citeauthor", "citeyear", "ref", "eqref", "autoref", "cref", "Cref", "label"):
                    opt = re.match(r"\s*(\[[^\]]*\])*\s*\{", text[j:])
                    if opt:
                        content, end = brace_content(text, j + opt.end() - 1)
                        tag = "cite" if name.startswith("cite") else name
                        out.append("" if name == "label" else f"[{tag}: {content.strip()}]")
                        i = end; continue
                if name in SIMPLE_CMDS:
                    opt = re.match(r"\s*(\[[^\]]*\])*\s*\{", text[j:])
                    if opt:
                        content, end = brace_content(text, j + opt.end() - 1)
                        if name == "href":
                            second = re.match(r"\s*\{", text[end:])
                            if second:
                                label, end2 = brace_content(text, end + second.end() - 1)
                                out.append(f"[{clean_inline(label)}]({content})"); i = end2; continue
                        out.append(SIMPLE_CMDS[name].format(clean_inline(content)))
                        i = end; continue
                if name in ("ldots", "dots"):
                    out.append("…"); i = j; continue
                if name in ("LaTeX", "TeX"):
                    out.append(name); i = j; continue
                if name in ("noindent", "centering", "small", "large", "Large", "normalsize", "vspace", "hspace", "newline", "linebreak", "clearpage", "newpage"):
                    opt = re.match(r"\s*\{[^}]*\}", text[j:])
                    i = j + (opt.end() if opt else 0); continue
                out.append(text[i:j]); i = j; continue
            if i + 1 < len(text) and text[i + 1] in "%&#$_{}":
                out.append(text[i + 1]); i += 2; continue
            if i + 1 < len(text) and text[i + 1] == "\\":
                out.append("  \n"); i += 2; continue
        out.append(text[i]); i += 1
    s = "".join(out)
    s = s.replace("``", "“").replace("''", "”").replace("~", " ").replace("---", "—").replace("--", "–")
    return s


def protect_math(text):
    slots = []

    def keep(m):
        slots.append(m.group(0)); return f"\x00{len(slots) - 1}\x00"

    text = re.sub(r"\$\$.*?\$\$", keep, text, flags=re.S)
    text = re.sub(r"\\\[.*?\\\]", keep, text, flags=re.S)
    text = re.sub(r"\\\(.*?\\\)", keep, text, flags=re.S)
    text = re.sub(r"\\begin\{(equation|align|gather|multline|eqnarray|alignat)\*?\}.*?\\end\{\1\*?\}", keep, text, flags=re.S)
    text = re.sub(r"(?<!\\)\$(?:\\.|[^$])+?\$", keep, text)
    return text, slots


def restore_math(text, slots):
    def back(m):
        s = slots[int(m.group(1))]
        if s.startswith("\\begin"):
            s = re.sub(r"\\label\{[^}]*\}", "", s)
            s = re.sub(r"\\(begin|end)\{equation\*?\}", "", s)  # KaTeX renders the bare body in $$
            return "\n$$\n" + s.strip() + "\n$$\n"
        if s.startswith("\\["):
            return "\n$$" + s[2:-2] + "$$\n"
        if s.startswith("\\("):
            return "$" + s[2:-2] + "$"
        return s

    return re.sub(r"\x00(\d+)\x00", back, text)


def tex_to_md(block, level_offset=0, tex_dir=None):
    text, slots = protect_math(block)
    figures = figures_in(block)
    md_figs = []
    for f in figures:
        paths = [str(Path(tex_dir) / p) if tex_dir and not Path(p).is_absolute() else p for p in f["paths"]]
        imgs = "\n".join(f"![{f['label'] or 'figure'}]({p})" for p in paths)
        md_figs.append(f"{imgs}\n\n*{f['label'] + ': ' if f['label'] else ''}{f['caption']}*")
    text = re.sub(r"\\begin\{figure\*?\}.*?\\end\{figure\*?\}", lambda m: "\n\n" + md_figs.pop(0) + "\n\n", text, flags=re.S)
    text = re.sub(r"\\begin\{abstract\}", "", text)
    text = re.sub(r"\\end\{abstract\}", "", text)

    def heading(m):
        depth = LEVEL[m.group(1)] + level_offset
        return "\n" + "#" * min(depth + 1, 6) + " " + clean_inline(m.group(2)).strip() + "\n"

    text = re.sub(r"\\(section|subsection|subsubsection)\*?\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", heading, text)
    text = re.sub(r"\\paragraph\*?\{([^}]*)\}", lambda m: "\n**" + clean_inline(m.group(1)).strip() + "** ", text)
    text = re.sub(r"\\begin\{(itemize|enumerate|description)\}", "", text)
    text = re.sub(r"\\end\{(itemize|enumerate|description)\}", "\n", text)
    text = re.sub(r"^\s*\\item\s*(\[[^\]]*\])?", lambda m: "- " + (m.group(1)[1:-1] + " " if m.group(1) else ""), text, flags=re.M)
    text = re.sub(r"\\begin\{(quote|quotation|center|flushleft|flushright|table\*?|tabular\*?|minipage)\}(\[[^\]]*\])?(\{[^}]*\})*", "", text)
    text = re.sub(r"\\end\{(quote|quotation|center|flushleft|flushright|table\*?|tabular\*?|minipage)\}", "", text)
    text = re.sub(r"\\(hline|toprule|midrule|bottomrule|centering|noindent|maketitle)\b", "", text)
    text = clean_inline(text)
    text = restore_math(text, slots)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def extract(tex_path, sid, out_path, level_offset=0):
    info = outline(tex_path)
    sec = next((s for s in info["sections"] if s["id"] == sid), None)
    if not sec:
        print(json.dumps({"ok": False, "error": f"no section {sid}; ids: {[s['id'] for s in info['sections']]}"}))
        sys.exit(1)
    raw = Path(tex_path).read_text(errors="replace").splitlines()
    block = "\n".join(strip_comments(l) for l in raw[sec["start"] - 1:sec["end"]])
    tex_dir = Path(tex_path).resolve().parent
    md = tex_to_md(block, level_offset, tex_dir)
    figs = []
    for f in sec["figures"]:
        for p in f["paths"]:
            figs.append({"path": str(tex_dir / p), "caption": f["caption"], "label": f["label"]})
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    figs_path = out.with_suffix(out.suffix + ".figures.json")
    figs_path.write_text(json.dumps(figs, indent=1, ensure_ascii=False))
    print(json.dumps({"ok": True, "section": sec["title"], "lines": f"L{sec['start']}-{sec['end']}", "paragraphs": sec["paragraphs"], "markdown": str(out), "figures": str(figs_path), "figure_count": len(figs)}, indent=1))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("outline"); sp.add_argument("tex"); sp.add_argument("--out")
    sp = sub.add_parser("extract"); sp.add_argument("tex"); sp.add_argument("--id", required=True); sp.add_argument("--out", required=True)
    sp.add_argument("--level-offset", type=int, default=0, help="shift heading depth in the Markdown")
    a = p.parse_args()
    if a.cmd == "outline":
        info = outline(a.tex)
        if a.out:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(json.dumps(info, indent=1, ensure_ascii=False))
            summary = [{k: s[k] for k in ("id", "title", "level", "start", "end", "paragraphs", "skip")} | {"figures": len(s["figures"])} for s in info["sections"]]
            print(json.dumps({"ok": True, "title": info["title"], "out": a.out, "sections": summary}, indent=1, ensure_ascii=False))
        else:
            print(json.dumps(info, indent=1, ensure_ascii=False))
    else:
        extract(a.tex, a.id, a.out, a.level_offset)


if __name__ == "__main__":
    main()
