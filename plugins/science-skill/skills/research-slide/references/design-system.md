# Research-slide design system

The reference for building slides in this style. Read the section you need — you
don't have to read all of it. `scripts/slide_kit.py` implements every token and
component here; `examples/` shows both templates fully assembled.

## Contents
- [Design tokens](#design-tokens) — palette, fonts, canvas
- [Editability rules](#editability-rules) — what stays native vs. image
- [Panel prep](#panel-prep) — figure PDF → placeable panels (and the PDF trap)
- [Template A — single story](#template-a--single-story) — one result: approach → findings
- [Template B — thesis / evidence / conclusion](#template-b--thesis--evidence--conclusion) — several results as an argument
- [Writing the narrative](#writing-the-narrative) — section vocabulary + tone
- [Citations](#citations)
- [Verify checklist](#verify-checklist)

---

## Design tokens

Colors (in `slide_kit` as named constants):

| Name | Hex | Role |
|------|-----|------|
| `NAVY` | `#1F3864` | statement banner fill, ■ markers, conclusion accent |
| `LBLUE` | `#9EC6F0` | one accent keyword inside the navy banner |
| `BLUE` | `#2E75D6` | corner accent, dashed column divider |
| `BLACK` | `#1A1A1A` | header text |
| `BODY` | `#333940` | body / highlight text |
| `GRAY` | `#6B7078` | captions, method tags |
| `RED` | `#C00000` | citations, 实验挑战 emphasis |
| `WHITE` | `#FFFFFF` | banner text, box fill |
| `HAIRLINE` | `#C7CED6` | thin rules, panel borders |

Restraint is the whole look: **navy + one blue accent + red for citations**, on
white. Saturated fills bigger than the banner (e.g. a full row of bright-blue
title bars) read as heavy and busy — prefer □/■ text headers. Color carries
meaning here (navy = structure, red = provenance), so don't add hues casually.

Fonts: **CJK = PingFang SC**, **Latin/math/citations = Times New Roman** (serif,
so formulas and journal names look like a paper). PingFang is macOS-only; on
other machines swap `CJK` in `slide_kit.py` to an installed face (Microsoft
YaHei, Noto Sans CJK SC).

Canvas: **16:9, 13.333 × 7.5 in**. All coordinates in the kit are inches.

---

## Editability rules

The point of building with python-pptx (instead of exporting a flat image) is
that the presenter can edit it. So:

- **All text and chrome are native shapes** — banners, headers, tags, citations,
  boxes, dividers. Retypable, recolorable, movable.
- **Only figure panels are placed images.** Schematics and data plots are
  inherently raster in the final slide; that's expected and loses nothing
  editable, because the explanatory text around them stays native.
- **`word_wrap=False` on short labels** (headers, panel letters, tags). CJK text
  boxes otherwise wrap on a hair of overflow and silently split `(a)` onto two
  lines. `slide_kit`'s `header`/`tag` handle typical cases; if a label still
  wraps, widen the box or drop a point of size.
- **Subscripts/superscripts via `sub=True`/`sup=True`** on the run (ρ_yx, R_xx,
  e²). A literal `R_yx` with an underscore in the text is the #1 tell of a
  blind build — always use real runs. For **chemical formulas** use unicode
  subscripts `₂₃₄` inside a normal run (MnBi₂Te₄, tWSe₂): they sit on the
  baseline and kern better than manual sub runs.

---

## Panel prep

**Do not convert the figure PDF straight to PPTX.** LibreOffice's PDF→PPTX
importer ignores clipping paths and z-order, so Illustrator paper-figures (the
common case) come out with hidden/clipped images splattered full-bleed over the
slide. The reliable path is render → crop → place:

```
python scripts/crop_panels.py detect figure.pdf --dpi 400   # prints candidate boxes (inches)
python scripts/crop_panels.py render figure.pdf fig.png --dpi 400
python scripts/crop_panels.py crop fig.png 0.34 0.55 4.54 2.54 panels/ab.png   # auto-trims whitespace
```

`detect` is a hint, not an answer — open the render, confirm the boxes by eye,
adjust. Trim every panel to tight bounds so placement math is clean. If the
figure already exists as separate panel image files (some LaTeX/TikZ figures
keep them in an `images/` folder), just use those and skip cropping.

Panels carry their own sub-labels (a/b/c, axes). If a source panel-letter would
collide with a header you add, crop it out or omit your duplicate.

---

## Template A — single story

**Use when the slide is ONE result** with a clear arc: a problem, the approach,
and what was found. Two columns split by a dashed divider; the eye reads left
(why/how) then right (what). This is `examples/example_single_story.py`.

```
┌───────────────────────────────┊───────────────────────────────┐
│ □ 研究思路：<one-line framing>  ┊ ■ <finding 1 headline>        │
│ ┌───────── navy banner ──────┐ ┊  [ data panels ]              │
│ │ core idea, 1 line          │ ┊  <plain-language finding line>│
│ └────────────────────────────┘ ┊ ■ <finding 2 headline>        │
│  [ concept / device panels ]   ┊  [ panel ]   ┌── conclusion ─┐│
│ 实验挑战：<the hard part> (red) ┊              │ R_xy=…, R_xx→0││
│ □ 技术突破：<what unlocked it>  ┊              └───────────────┘│
│  [ mechanism panel ]           ┊  FirstAuthor et al., J V, P (Y) role │
└───────────────────────────────┊───────────────────────────────┘
```

Coordinates that work (inches), left column `LX,LW = 0.42, 6.00`; right column
`RX,RW = 6.94, 6.00`; divider at `x=6.66`:

| Element | x | y | note |
|---|---|---|---|
| 研究思路 header (□) | LX | 0.40 | black bold ~16 |
| navy banner | LX+0.10 | 1.00 | w=LW−0.20, h=0.56 |
| concept panels row | centered | 1.80 | h≈1.6 |
| 实验挑战 (red) | LX | 3.74 | bold red, ≤2 lines |
| 技术突破 header (□) | LX | 4.52 | + body at 4.98 |
| mechanism panel | centered | 5.86 | h≈1.3 |
| finding-1 header (■) | RX | 0.40 | |
| data panel(s) | RCX-centered | 1.02 | h≈1.8 |
| finding line | RX | ~2.9 | body |
| finding-2 header (■) | RX | 3.62 | |
| panel + conclusion box | RX | 4.22 | panel left, box right |
| citation (red) | RX | 6.92 | |

The **conclusion box** (black hairline border) is where the quantitative punch
line lives — the equation or number that the whole slide argues for. It's what
makes the slide feel rigorous rather than descriptive.

---

## Template B — thesis / evidence / conclusion

**Use when the slide is SEVERAL results marshalled into one claim** (a
capability, a platform, a body of work). The danger is that it becomes a loose
poster of unrelated panels; the fix is to make the logic explicit — a thesis on
top, parallel evidence columns, and a synthesizing conclusion. This is
`examples/example_portfolio.py`.

```
□ 研究思路：<the overarching capability / claim>
┌──────────────── navy banner: the thesis, one line ────────────────┐
└───────────────────────────────────────────────────────────────────┘
 ■ 突破一 <class A>   ┊  ■ 突破二 <class B>   ┊  ■ 突破三 <class C>
 <method tag 光/电>   ┊  <method tag>         ┊  <method tag>
 [ panel ]            ┊  [ panel ]            ┊  [ panel ]
 <one-line 亮点>      ┊  <one-line 亮点>      ┊  <one-line 亮点>
 cite (red)           ┊  cite (red)           ┊  cite (red)
─────────────────────────────────────────────────────────────────────
 ▶ 结论：<synthesis — why the three together prove the thesis>
```

Three columns at `CX = [0.40, 4.62, 8.84]`, `CW = 4.05`; dashed dividers at
`x=4.53, 8.75`; header y=1.56, tag y=2.18, figure y=2.48, citations aligned at
y=6.28, conclusion at y=6.70 (hairline at 6.62).

Make it an argument, not a gallery:
- **Every column supports the same thesis.** State the shared axis explicitly
  (here: the same 光电联合表征 platform applied to three material classes —
  magnet / superconductor / moiré). If the columns don't share an axis, this
  template is the wrong choice.
- **Method tags earn the claim.** The gray tag under each header names *how*
  (光: RMCD / 激子谱学; 电: 输运), so the reader sees the common method thread.
- **The conclusion synthesizes, it doesn't summarize.** "Three systems validate
  the platform's universality and reliability" — a claim the three columns
  jointly earn, not a list of what's above.

Number the evidence (突破一/二/三) so the enumeration reads as deliberate.

Panels with very different aspect ratios (a tall stack next to two wide plots)
are fine — center each in its column, align tops and the citation row; let the
bottoms differ and let the 亮点 text take up the slack.

---

## Writing the narrative

The text is what turns a figure into a defense slide. Keep it tight and
grounded — describe what the panel actually shows, then state the significance;
don't overclaim.

Section vocabulary (the words that signal rigor to a Chinese committee):

| Term | Role in the argument |
|---|---|
| 研究思路 / 科学问题 | the framing question or goal |
| 实验挑战 | the hard part that made it non-trivial (render in red) |
| 技术突破 | the method/tool that unlocked it |
| 研究发现 / 结果 | what the data show (■ headers) |
| 研究亮点 | one-line significance of a result |
| 结论 | the synthesized takeaway |

Tone:
- **One idea per line.** The banner is a single sentence; each 亮点 is one
  sentence. If it needs two, it's two thoughts — split or cut.
- **Name the observable, then the meaning.** "R_xy 量子化至 (1/|ν|)·h/e²，R_xx→0"
  (observable) "→ 零场分数量子反常霍尔" (meaning). Committees trust the chain.
- **Prefer verbs of evidence** — 证实 / 揭示 / 实证 / 印证 — over hype (突破性、
  首次、世界领先). The data should carry the weight.
- **Author's role** goes after the citation (共同一作 / 共同通讯作者 / 合作者) —
  it's expected on a defense/report slide and it's honest to state it.

---

## Citations

Format: `FirstAuthor et al., <Journal> <Vol>, <Page> (<Year>)  <role>` — journal
*italic*, volume **bold**, everything in serif, colored `RED`. Author-first
citations use `slide_kit`'s `citation_runs("Park et al.", "Nature", "622",
", 74 (2023)", "共同一作")`. Some slides cite journal-first with no author
(`Science 381(6655), 325–330 (2023)，共同一作`) — build those runs directly
(journal italic, vol bold), as `example_portfolio.py` does.

---

## Verify checklist

Always render and read it back (`scripts/render_check.py slide.pptx`) — building
blind is how these bugs ship:

- [ ] No text box overlaps another or a panel (tall panels crowd the text below —
      shrink the panel or move the citation down).
- [ ] No literal underscores (`R_yx`) — those should be subscript runs.
- [ ] No header wrapped to an unintended second line.
- [ ] Chemical formulas show real subscripts (MnBi₂Te₄, not MnBi2Te4).
- [ ] Citations aligned; roles present.
- [ ] The logic is legible without narration: a stranger sees claim → evidence →
      conclusion (B) or problem → approach → result (A).

LibreOffice's renderer is an approximation. The `.pptx` is the deliverable —
tell the user to do a final pass in PowerPoint, where CJK font substitution can
shift spacing slightly.
