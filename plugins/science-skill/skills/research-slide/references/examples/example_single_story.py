#!/usr/bin/env python
"""EXAMPLE — single-story template (one result: approach -> findings).

Reproduces the FQAHE / tMoTe2 defense slide. Read this to see how the pieces of
slide_kit compose into the two-column "research-highlight" layout:

  LEFT  研究思路 : □ header, navy statement banner, device panels, 实验挑战 (red),
                  技术突破 (□ header + body), mechanism panel
  RIGHT 研究发现 : ■ headers, data panels, a plain-language finding line,
                  a bordered conclusion box, red-italic citation
  divider: dashed vertical line between the columns

Run it (panels must exist at PANELS):
  python example_single_story.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
from slide_kit import Deck, run, ALIGN, ANCHOR, NAVY, BLACK, BODY, RED, WHITE, LBLUE, GRAY

# Point this at your cropped, trimmed panels (see crop_panels.py).
PANELS = os.path.join(HERE, "fig4_panels")

deck = Deck()                      # 16:9
s = deck.slide()
s.corner_accent()

# ---- column geometry ----
LX, LW = 0.42, 6.00
RX, RW = 6.94, 6.00
LCX, RCX = LX + LW / 2, RX + RW / 2
s.vdivider(6.66, 0.34, 7.16)

# ================================================================= LEFT
s.header(LX, 0.40, LW, [run("研究思路：零磁场实现分数量子反常霍尔效应", size=16, bold=True, color=BLACK)],
         mark="□", mark_color=BLACK)

s.banner([run("拓扑平带 + 强关联相互作用  →  ", size=15, bold=True, color=WHITE),
          run("零磁场分数量子化", size=15, bold=True, color=LBLUE)],
         x=LX + 0.10, y=1.00, w=LW - 0.20, h=0.56)

# device panels a + b
w, h = s.picture(os.path.join(PANELS, "a.png"), 0, 0, h=1.58)   # measure
s.s.shapes._spTree.remove(s.s.shapes[-1]._element)             # discard measuring copy
wa = w
w, h = s.picture(os.path.join(PANELS, "b.png"), 0, 0, h=1.58); s.s.shapes._spTree.remove(s.s.shapes[-1]._element)
wb = w
gap = 0.55
ax = LCX - (wa + gap + wb) / 2
s.picture(os.path.join(PANELS, "a.png"), ax, 1.80, h=1.58)
s.picture(os.path.join(PANELS, "b.png"), ax + wa + gap, 1.80, h=1.58)
s.caption(ax, 1.80 + 1.58 + 0.01, wa, "器件截面结构")
s.caption(ax + wa + gap, 1.80 + 1.58 + 0.01, wb, "三栅极堆叠结构")

# experimental challenge (red)
s.text(LX + 0.02, 3.74, LW, 0.72,
       [[run("实验挑战：", size=15, bold=True, color=RED),
         run("如何在零磁场下实现并精确测量分数量子化的霍尔电阻？", size=15, bold=True, color=RED)]],
       line_spacing=1.12)

# technical breakthrough
s.header(LX, 4.52, LW, [run("技术突破", size=16.5, bold=True, color=BLACK)], mark="□", mark_color=BLACK)
s.text(LX + 0.42, 4.98, LW - 0.42, 0.80,
       [[run("三栅极器件独立调控载流子密度与位移场，", size=14.5, color=BODY)],
        [run("并结合半金属化 TMD 的低温欧姆接触实现精密输运测量。", size=14.5, color=BODY)]],
       line_spacing=1.12)

# mechanism panel c
wc, hc = s.picture(os.path.join(PANELS, "c.png"), 0, 0, h=1.28); s.s.shapes._spTree.remove(s.s.shapes[-1]._element)
cx = LCX - wc / 2
s.picture(os.path.join(PANELS, "c.png"), cx, 5.86, h=1.28)
s.caption(cx, 5.86 + 1.28 + 0.01, wc, "半金属化 TMD 欧姆接触")

# ================================================================= RIGHT
s.header(RX, 0.40, RW, [run("观测到量子反常霍尔与分数量子反常霍尔效应", size=16.5, bold=True, color=BLACK)], mark="■", mark_color=BLACK)
s.picture(os.path.join(PANELS, "def.png"), RCX - (1.78 * 3.237) / 2, 1.02, h=1.78)

s.text(RX + 0.02, 1.02 + 1.78 + 0.06, RW, 0.60,
       [[run("磁滞回线证实自发时间反演对称破缺；", size=14, color=BODY),
         run("ν = −1", size=14, italic=True, color=BODY, serif=True),
         run(" 为整数 QAH，", size=14, color=BODY),
         run("ν = −2/3、−3/5", size=14, italic=True, color=BODY, serif=True),
         run(" 为分数态。", size=14, color=BODY)]], line_spacing=1.1)

s.header(RX, 3.62, RW, [run("霍尔电阻的精确分数量子化", size=16.5, bold=True, color=BLACK)], mark="■", mark_color=BLACK)
wg, hg = s.picture(os.path.join(PANELS, "g.png"), RX + 0.05, 4.22, h=2.30)
s.caption(RX + 0.05, 4.22 + 2.30, wg, "R 随填充数 ν 的演化")

bxx = RX + 0.05 + wg + 0.28
bxw = RX + RW - bxx
s.box(bxx, 4.27, bxw, 2.10, [
    [run("霍尔电阻量子化平台：", size=13.5, bold=True, color=BLACK)],
    [run("R", size=13.5, italic=True, color=BLACK, serif=True),
     run("xy", size=13.5, italic=True, color=BLACK, sub=True, serif=True),
     run(" = (1/|ν|)·h/e²", size=13.5, color=BLACK, serif=True)],
    [run("纵向电阻 ", size=13.5, color=BLACK),
     run("R", size=13.5, italic=True, color=BLACK, serif=True),
     run("xx", size=13.5, italic=True, color=BLACK, sub=True, serif=True),
     run(" → 0，体系无耗散", size=13.5, color=BLACK)],
    [run("零磁场下确立分数量子反常", size=13.5, color=BLACK)],
    [run("霍尔效应，实证莫尔陈能带", size=13.5, color=BLACK)],
    [run("中的分数化激发", size=13.5, color=BLACK)],
])

s.cite(RX + 0.02, 6.92, RW,
       s.citation_runs("Park et al.", "Nature", "622", ", 74 (2023)", "共同一作", size=12.5))

deck.save(os.path.join(HERE, "example_single_story.pptx"))
print("saved example_single_story.pptx")
