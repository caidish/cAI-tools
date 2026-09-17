#!/usr/bin/env python
"""render_check — render a .pptx to PNG so you can SEE the slide.

Building a slide blind is how subscripts end up as literal underscores, headers
silently wrap to two lines, and text boxes overlap. Always render after
building, open the PNG, and read it back before declaring victory.

Uses LibreOffice headless (`soffice`). Note: LibreOffice's renderer is only an
approximation — the .pptx is the deliverable, and the user should do a final
check in PowerPoint (CJK font substitution can shift spacing). But it catches
the big layout/text bugs immediately and for free.

Usage
-----
  python render_check.py slide.pptx [out_dir]     # default out_dir: ./_render
"""
import os
import subprocess
import sys


def find_soffice():
    for c in ("soffice", "libreoffice",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        try:
            subprocess.run([c, "--version"], capture_output=True, check=True)
            return c
        except Exception:
            continue
    return None


def render(pptx, out_dir="_render"):
    soffice = find_soffice()
    if not soffice:
        print("soffice/libreoffice not found — install LibreOffice to preview.",
              file=sys.stderr)
        return None
    os.makedirs(out_dir, exist_ok=True)
    subprocess.run([soffice, "--headless", "--convert-to", "png",
                    "--outdir", out_dir, pptx], check=True,
                   capture_output=True, timeout=180)
    png = os.path.join(out_dir, os.path.splitext(os.path.basename(pptx))[0] + ".png")
    if os.path.exists(png):
        print(png)
        return png
    print("conversion produced no PNG", file=sys.stderr)
    return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else "_render"
    render(sys.argv[1], out)
