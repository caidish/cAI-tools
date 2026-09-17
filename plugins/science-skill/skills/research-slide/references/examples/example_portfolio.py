#!/usr/bin/env python
"""EXAMPLE — thesis/evidence/conclusion template (several results as an argument).

Reproduces the "光电联合表征" defense slide. Use this shape when the slide isn't
one story but a CLAIM supported by several breakthroughs. The logic must be
explicit — that's what makes it read as an argument rather than a poster:

  THESIS     □ 研究思路 line + a navy statement banner (the claim)
  EVIDENCE   N columns (■ 突破一/二/三 ...), each = header + method tag +
             figure + one-line 亮点 + citation, separated by dashed dividers
  CONCLUSION a full-width ▶ 结论 line that synthesizes the evidence

Every column should visibly support the SAME thesis (here: each breakthrough is
the same 光/电 platform applied to a different material class), and the tags name
how (光: RMCD/激子谱学; 电: 输运). Avoid large saturated title bars — clean ■
headers keep the focus on the data.

Run it (panels must exist at PANELS):
  python example_portfolio.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
from slide_kit import Deck, run, ALIGN, ANCHOR, NAVY, LBLUE, BLUE, BLACK, BODY, GRAY, RED, WHITE

PANELS = os.path.join(HERE, "fig2_images")  # replace with your cropped, trimmed panels (see scripts/crop_panels.py)

deck = Deck()
s = deck.slide()
s.corner_accent()

# ---- THESIS ----
s.header(0.42, 0.24, 12.5,
         [run("研究思路：拓扑与莫尔量子材料的无损、高质量制备与光电联合表征", size=16, bold=True, color=BLACK)],
         mark="□", mark_color=NAVY)
s.banner([run("同一制备—表征范式，在磁体、超导、莫尔三类量子材料中获得", size=15.5, bold=True, color=WHITE),
          run("验证性进展", size=15.5, bold=True, color=LBLUE)],
         x=0.40, y=0.78, w=12.53, h=0.56)

# ---- EVIDENCE: three columns ----
CX = [0.40, 4.62, 8.84]
CW = 4.05
COL_TOP = 1.56
HDR_Y, TAG_Y, FIG_TOP, CITE_Y = COL_TOP, COL_TOP + 0.62, COL_TOP + 0.92, 6.28
for dx in (4.53, 8.75):
    s.vdivider(dx, COL_TOP + 0.04, 6.42, w=2.0)

# 突破一 — MnBi2Te4 (tall panel)
cx = CX[0]
s.header(cx, HDR_Y, CW, [run("突破一　拓扑磁体 MnBi₂Te₄", size=13.5, bold=True, color=BLACK)], mark="■")
s.tag(cx + 0.28, TAG_Y, CW - 0.28, "无损加工高质量样品 · RMCD（光）+ 量子输运（电）")
wa, ha = s.picture(os.path.join(PANELS, "Picture_5.png"), cx + (CW - 1.38) / 2, FIG_TOP, h=2.62)
s.text(cx + 0.06, FIG_TOP + ha + 0.06, CW - 0.12, 1.4,
       [[run("同一器件同步测量 RMCD 磁序与量子输运；纵向零耗散、", size=11.5, color=BODY),
         run("ρ", size=11.5, italic=True, color=BODY, serif=True),
         run("yx", size=11.5, italic=True, color=BODY, sub=True, serif=True),
         run(" 量子化至 ±h/e²，实证反铁磁拓扑绝缘体的量子反常霍尔与轴子态。", size=11.5, color=BODY)]],
       line_spacing=1.16)
s.cite(cx + 0.06, CITE_Y, CW - 0.12,
       [run("Nat. Commun.", size=10.5, italic=True, color=RED, serif=True),
        run(" 13", size=10.5, bold=True, color=RED, serif=True),
        run(", 1668 (2022)；", size=10.5, color=RED, serif=True),
        run("13", size=10.5, bold=True, color=RED, serif=True),
        run(", 5967 (2022)  共同一作", size=10.5, color=RED, serif=True)])

# 突破二 — (Bi,Sb)2Te3/FeTe
cx = CX[1]
s.header(cx, HDR_Y, CW, [run("突破二　候选拓扑超导体 (Bi,Sb)₂Te₃/FeTe", size=13.5, bold=True, color=BLACK)], mark="■")
s.tag(cx + 0.28, TAG_Y, CW - 0.28, "界面高质量制备 · R(T)、Ryx（电）+ RMCD（光）")
wb, hb = s.picture(os.path.join(PANELS, "Picture_14.jpg"), cx + (CW - 3.30) / 2, FIG_TOP + 0.08, w=3.30)
s.text(cx + 0.06, FIG_TOP + 0.08 + hb + 0.08, CW - 0.12, 1.2,
       [[run("R", size=11.5, italic=True, color=BODY, serif=True),
         run("(T) 显示超导转变 (", size=11.5, color=BODY, serif=True),
         run("T", size=11.5, italic=True, color=BODY, serif=True),
         run("c", size=11.5, italic=True, color=BODY, sub=True, serif=True),
         run(" ≈ 12 K)；", size=11.5, color=BODY, serif=True),
         run("R", size=11.5, italic=True, color=BODY, serif=True),
         run("yx", size=11.5, italic=True, color=BODY, sub=True, serif=True),
         run(" 与 RMCD 磁滞一致，揭示界面铁磁与候选拓扑超导共存。", size=11.5, color=BODY)]],
       line_spacing=1.16)
s.cite(cx + 0.06, CITE_Y, CW - 0.12,   # journal-first citation -> build runs directly
       [run("Science", size=10.5, italic=True, color=RED, serif=True),
        run(" 381", size=10.5, bold=True, color=RED, serif=True),
        run("(6655), 325–330 (2023)  共同一作", size=10.5, color=RED, serif=True)])

# 突破三 — 魔角石墨烯-tWSe2
cx = CX[2]
s.header(cx, HDR_Y, CW, [run("突破三　魔角石墨烯–tWSe₂ 莫尔关联", size=13.5, bold=True, color=BLACK)], mark="■")
s.tag(cx + 0.28, TAG_Y, CW - 0.28, "高质量转角异质结 · 激子谱学（光）+ 输运（电）")
wc, hc = s.picture(os.path.join(PANELS, "Picture_18.png"), cx + (CW - 3.80) / 2, FIG_TOP + 0.30, w=3.80)
s.text(cx + 0.06, FIG_TOP + 0.30 + hc + 0.12, CW - 0.12, 1.6,
       [[run("以 ", size=11.5, color=BODY),
         run("tWSe₂", size=11.5, color=BODY, serif=True),
         run(" 层间激子为传感器，光学读出邻近魔角石墨烯的关联填充与能带结构，并与 ", size=11.5, color=BODY),
         run("R", size=11.5, italic=True, color=BODY, serif=True),
         run("xx", size=11.5, italic=True, color=BODY, sub=True, serif=True),
         run(" 输运特征相互印证。", size=11.5, color=BODY)]],
       line_spacing=1.16)
s.cite(cx + 0.06, CITE_Y, CW - 0.12,
       [run("Nat. Mater.", size=10.5, italic=True, color=RED, serif=True),
        run(" 23", size=10.5, bold=True, color=RED, serif=True),
        run(", 224–229 (2024)  共同一作", size=10.5, color=RED, serif=True)])

# ---- CONCLUSION ----
s.conclusion([run("▶  结论：", size=14.5, bold=True, color=NAVY),
              run("磁体 · 超导 · 莫尔三类体系一致印证 —— 无损、高质量制备与光电联合表征范式具备跨材料的",
                  size=14, bold=True, color=BLACK),
              run("普适性与可靠性", size=14, bold=True, color=NAVY)],
             y=6.70)

deck.save(os.path.join(HERE, "example_portfolio.pptx"))
print("saved example_portfolio.pptx")
