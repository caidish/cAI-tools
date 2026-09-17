#!/usr/bin/env python
"""crop_panels — turn a flat figure PDF into tight, placeable panel images.

Why not just convert the PDF to PPTX?  LibreOffice's PDF->PPTX importer ignores
clipping paths and z-order, so Illustrator figures (very common for paper
figures) come out with hidden/clipped images splattered full-bleed over
everything. The reliable path for THIS style of slide is:

    render the PDF to a high-DPI PNG  ->  crop each panel  ->  trim whitespace
    ->  place the panels as images in a native slide (slide_kit).

Panels (schematics, data plots) are inherently raster in the final slide anyway,
so nothing editable is lost — the text/chrome around them stays native.

Usage
-----
  # 1) See what's there. Renders the PDF and prints candidate panel boxes
  #    (in inches) by scanning for content bands and column clusters:
  python crop_panels.py detect figure.pdf [--dpi 400]

  # 2) Render once to a PNG you can crop repeatedly:
  python crop_panels.py render figure.pdf out.png [--dpi 400]

  # 3) Crop a box (inches) from a rendered PNG, auto-trimming whitespace:
  python crop_panels.py crop out.png 0.34 0.55 4.54 2.54 panels/ab.png

`detect` is a starting point, not gospel — read the printed boxes, then verify
by eye (open the render) and adjust the crop coordinates. Requires `pdftoppm`
(poppler) on PATH for rendering; cropping/trimming needs only Pillow.
"""
import argparse
import os
import subprocess
import sys

import numpy as np
from PIL import Image


def render(pdf, out_png, dpi=400):
    """PDF (first page) -> PNG via pdftoppm."""
    base = out_png[:-4] if out_png.lower().endswith(".png") else out_png
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-singlefile", pdf, base],
                   check=True)
    produced = base + ".png"
    if produced != out_png and os.path.exists(produced):
        os.replace(produced, out_png)
    im = Image.open(out_png)
    print(f"rendered {out_png}  {im.size[0]}x{im.size[1]}px  "
          f"= {im.size[0]/dpi:.2f}x{im.size[1]/dpi:.2f} in @ {dpi}dpi")
    return out_png


def _mask(png, thr=248):
    a = np.asarray(Image.open(png).convert("RGB")).astype(int)
    return a.sum(2) < 3 * thr, a


def detect(png, dpi=400, min_w=0.25, gap=0.18):
    """Print candidate panel boxes (inches). Strategy: find horizontal content
    bands (rows with ink), then within each band split into column clusters
    separated by >`gap` inches of whitespace. Drops slivers < `min_w` wide
    (usually stray axis ticks or panel letters)."""
    nonwhite, _ = _mask(png)
    H, W = nonwhite.shape
    rowink = nonwhite.mean(1)
    # bands = maximal runs of rows with a bit of ink
    bands = []
    ys = np.where(rowink > 0.01)[0]
    if len(ys):
        s = ys[0]; p = ys[0]
        for y in ys[1:]:
            if y - p > int(0.25 * dpi):
                bands.append((s, p)); s = y
            p = y
        bands.append((s, p))
    print(f"# {os.path.basename(png)}  {W}x{H}px  {W/dpi:.2f}x{H/dpi:.2f}in @ {dpi}dpi")
    print(f"# found {len(bands)} content band(s). Boxes are x0 y0 x1 y1 (inches):")
    for bi, (by0, by1) in enumerate(bands):
        band = nonwhite[by0:by1 + 1, :]
        xs = np.where(band.any(0))[0]
        clusters = []
        if len(xs):
            s = xs[0]; p = xs[0]
            for x in xs[1:]:
                if x - p > int(gap * dpi):
                    clusters.append((s, p)); s = x
                p = x
            clusters.append((s, p))
        for (cx0, cx1) in clusters:
            if (cx1 - cx0) < int(min_w * dpi):
                continue
            sub = nonwhite[by0:by1 + 1, cx0:cx1 + 1]
            rr = np.where(sub.any(1))[0]
            ty, byy = rr.min() + by0, rr.max() + by0
            print(f"band{bi}:  {cx0/dpi:6.2f} {ty/dpi:6.2f} {cx1/dpi:6.2f} {byy/dpi:6.2f}"
                  f"   (w={ (cx1-cx0)/dpi:.2f} h={ (byy-ty)/dpi:.2f})")


def crop(png, x0, y0, x1, y1, out, dpi=400, trim=True, pad=6, thr=248):
    """Crop a box (inches) from a rendered PNG and (optionally) trim surrounding
    whitespace to tight bounds, leaving `pad` px of margin."""
    im = Image.open(png).convert("RGB")
    box = (int(x0 * dpi), int(y0 * dpi), int(x1 * dpi), int(y1 * dpi))
    c = im.crop(box)
    if trim:
        a = np.asarray(c).astype(int)
        m = a.sum(2) < 3 * thr
        ys, xs = np.where(m)
        if len(xs):
            cx0 = max(0, xs.min() - pad); cy0 = max(0, ys.min() - pad)
            cx1 = min(c.width, xs.max() + pad); cy1 = min(c.height, ys.max() + pad)
            c = c.crop((cx0, cy0, cx1, cy1))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    c.save(out)
    print(f"cropped {out}  {c.size[0]}x{c.size[1]}px  aspect(w/h)={c.width/c.height:.3f}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("render", help="PDF -> PNG")
    p.add_argument("pdf"); p.add_argument("out_png"); p.add_argument("--dpi", type=int, default=400)

    p = sub.add_parser("detect", help="render + print candidate panel boxes")
    p.add_argument("pdf"); p.add_argument("--dpi", type=int, default=400)
    p.add_argument("--gap", type=float, default=0.18); p.add_argument("--min-w", type=float, default=0.25)

    p = sub.add_parser("crop", help="crop a box (inches) from a rendered PNG")
    p.add_argument("png"); p.add_argument("x0", type=float); p.add_argument("y0", type=float)
    p.add_argument("x1", type=float); p.add_argument("y1", type=float); p.add_argument("out")
    p.add_argument("--dpi", type=int, default=400); p.add_argument("--no-trim", action="store_true")

    a = ap.parse_args()
    if a.cmd == "render":
        render(a.pdf, a.out_png, a.dpi)
    elif a.cmd == "detect":
        tmp = os.path.splitext(os.path.basename(a.pdf))[0] + f"_{a.dpi}dpi.png"
        render(a.pdf, tmp, a.dpi)
        detect(tmp, a.dpi, min_w=a.min_w, gap=a.gap)
        print(f"# (render kept at {tmp} — crop from it, then delete)")
    elif a.cmd == "crop":
        crop(a.png, a.x0, a.y0, a.x1, a.y1, a.out, a.dpi, trim=not a.no_trim)


if __name__ == "__main__":
    sys.exit(main())
