---
name: research-slide
description: >-
  Turn a research figure or result into a polished, EDITABLE Chinese
  defense/report slide (答辩/组会/项目汇报) in the house "research-highlight"
  style — navy statement banner, two-column layout with a dashed divider, □/■
  section headers, red-italic citations, and boxed conclusions, built as native
  python-pptx shapes (not a flat image). Use this whenever the user wants to
  turn a scientific figure (a PDF or PNG, or panel images), an experimental
  result, or a paper into a presentation slide, or to reorganize/redo an
  existing figure as a slide — including phrasings like 做成答辩ppt, 把这张图做成
  幻灯片, 组会/答辩/汇报用的slide, research highlight slide, 把figure X重新组织成
  一页, reorganize this figure into a slide, 按这个模版做. Optimized for
  physics/materials/quantum figures (device schematics + transport/optical
  data) but works for any科研 result. Supports single-story (研究思路→发现) and
  multi-result thesis/evidence/conclusion layouts. Trigger it even when the user
  doesn't say "skill" or "template" — if they're moving a figure toward a talk,
  this is the tool.
---

# research-slide

Build editable Chinese research/defense slides from a figure. The deliverable is
a `.pptx` where text and chrome are **native shapes** (retypable, movable) and
only the figure panels are placed images — so the presenter can actually edit it.
The look is deliberately restrained: navy + one blue accent + red citations on
white, with the argument's logic made visible.

Two layout templates, chosen by what the slide has to say:
- **Single story** — one result, argued as approach → findings. (`研究思路` on the
  left; `研究发现` + a boxed quantitative conclusion on the right.)
- **Thesis / evidence / conclusion** — several results marshalled into one claim.
  (A thesis banner on top; parallel evidence columns; a synthesizing `结论`.)

## Bundled resources

- `scripts/slide_kit.py` — the helper library. **Import it and build with it**;
  don't re-derive the CJK/subscript/shape plumbing by hand. `Deck`, `Slide`, and
  components (`banner`, `header`, `vdivider`, `highlight`, `cite`,
  `citation_runs`, `box`, `conclusion`, `picture`, `corner_accent`, …).
- `scripts/crop_panels.py` — figure PDF → tight panel images (render / detect /
  crop). Read its header for the "don't convert PDF→PPTX directly" trap.
- `scripts/render_check.py` — render the `.pptx` to PNG so you can see it.
- `references/design-system.md` — palette, fonts, the two templates with
  coordinate tables, narrative vocabulary, citations, verify checklist. **Read
  this before building** — it has the numbers that make layouts land.
- `references/examples/example_single_story.py` and `example_portfolio.py` —
  each template fully assembled on `slide_kit`. The fastest way to start is to
  copy the closer one and swap in the new content.

## Workflow

### 1. Gather the material
You need, per result: the **figure** (a PDF, or panel images), the **citation(s)**
with the author's role (共同一作 / 共同通讯作者 / 合作者), and enough **physics
context** to write honest narrative. If the figure is a paper's, its `.tex` or
caption usually has the exact titles and citations — check for them before
inventing anything. If citation or role is genuinely unknown, ask or use a clear
placeholder rather than guessing.

### 2. Choose the template
- One coherent result with a problem→method→finding arc → **single story**.
- Several results that jointly support a capability/claim → **thesis / evidence /
  conclusion**. (If the results don't share a thesis, don't force this — use
  separate slides.)

Look at the figure's own shape too: a tall flagship panel + smaller ones suits a
two-column split; three comparable panels suit three evidence columns.

### 3. Prepare the panels
If you have clean panel images already, use them. Otherwise crop them from the
figure PDF — render high-DPI, detect candidate boxes, crop with auto-trim:

```bash
python scripts/crop_panels.py detect figure.pdf --dpi 400
python scripts/crop_panels.py render figure.pdf fig.png --dpi 400
python scripts/crop_panels.py crop fig.png <x0> <y0> <x1> <y1> panels/a.png
```

Never run the figure PDF through LibreOffice's PDF→PPTX importer — it ignores
clipping and dumps hidden images full-bleed. Render → crop → place instead.

### 4. Write the narrative
This is where a figure becomes a defense slide. Grounded and tight: name what the
panel shows, then its significance; one idea per line; verbs of evidence (证实/
揭示/实证/印证), not hype. Use the section vocabulary (研究思路 / 实验挑战 /
技术突破 / 研究发现 / 研究亮点 / 结论). For the thesis template, make every
column support the same claim and tag each with its method. See
`references/design-system.md` → "Writing the narrative". You may draft this from
the physics, but flag anything you inferred (especially citations) so the user
can correct it.

### 5. Build with slide_kit
Copy the closer example and adapt, or start from this skeleton:

```python
import sys, os
sys.path.insert(0, "<skill>/scripts")
from slide_kit import Deck, run, NAVY, LBLUE, BLACK, BODY, RED, WHITE, GRAY

deck = Deck()                       # 16:9
s = deck.slide()
s.corner_accent()
s.header(0.42, 0.30, 12.5, [run("研究思路：…", size=16, bold=True, color=BLACK)], mark="□")
s.banner([run("核心论点，一句话，", size=15, bold=True, color=WHITE),
          run("关键词", size=15, bold=True, color=LBLUE)], y=0.80)
# … columns, panels (s.picture), highlights (s.text/s.highlight), citations (s.cite) …
deck.save("out.pptx")
```

Coordinates are inches; the design-system doc gives working values for both
templates. `s.picture(path, x, y, h=…)` keeps aspect ratio and returns `(w, h)`
so you can place neighbours and captions.

### 6. Verify — render and read it back
```bash
python scripts/render_check.py out.pptx
```
Open the PNG and check it against the verify checklist in `design-system.md`:
overlaps, literal `R_yx` underscores (should be subscript runs), headers wrapped
to a stray second line, chemical subscripts (MnBi₂Te₄), aligned citations, and —
most important — that the logic reads without narration. Fix, rebuild, re-render
until clean.

LibreOffice's renderer only approximates PowerPoint. The `.pptx` is the
deliverable; tell the user to do a final check in PowerPoint, where CJK font
substitution (PingFang SC) can shift spacing slightly.

## Notes

- Keep the original figure/assets untouched — write a new `*_slide.pptx`.
- Save the build script next to the output (like the examples); it makes the next
  round of edits trivial and documents the layout.
- Restraint is the aesthetic. Resist adding colors, gradients, or big saturated
  title bars — clean □/■ headers and one navy banner carry it.
