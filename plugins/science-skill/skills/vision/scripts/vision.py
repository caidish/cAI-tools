#!/usr/bin/env python
"""
Vision skill: Ask Gemini a question about an image.

Usage:
    python vision.py <image_path> "<prompt>"
    python vision.py photo.png "Describe the experimental setup shown here"

Requires:
    pip install google-genai Pillow
    export GEMINI_API_KEY=<your-key>
"""

import argparse
import sys
import mimetypes
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image


MODEL_ID = "gemini-3-pro-preview"
MAX_SHORT_SIDE = 4096  # resize if the short edge exceeds this


def load_and_resize(path: Path, max_short_side: int = MAX_SHORT_SIDE) -> Image.Image:
    """Load an image and down-scale if the short side exceeds *max_short_side*."""
    img = Image.open(path)
    w, h = img.size
    if min(w, h) > max_short_side:
        scale = max_short_side / min(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)
    return img


def image_to_part(path: Path) -> types.Part:
    """Convert an image file to a Gemini inline-data Part."""
    mime, _ = mimetypes.guess_type(str(path))
    if mime is None:
        mime = "image/png"
    with open(path, "rb") as f:
        data = f.read()
    return types.Part.from_bytes(data=data, mime_type=mime)


def ask_vision(image_path: str, prompt: str) -> str:
    """Send *prompt* + *image_path* to Gemini and return the response text."""
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        sys.exit(f"Error: file not found: {path}")

    # Resize on disk only when necessary (keeps original untouched)
    img = load_and_resize(path)
    if img.size != Image.open(path).size:
        # save resized to a temp buffer and re-encode
        import io
        buf = io.BytesIO()
        fmt = img.format or "PNG"
        img.save(buf, format=fmt)
        mime = f"image/{fmt.lower()}"
        part = types.Part.from_bytes(data=buf.getvalue(), mime_type=mime)
    else:
        part = image_to_part(path)

    client = genai.Client()  # uses GEMINI_API_KEY env var
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=[part, prompt],
    )
    return response.text


def main():
    parser = argparse.ArgumentParser(description="Ask Gemini about an image")
    parser.add_argument("image", help="Path to the image file")
    parser.add_argument("prompt", help="Question / instruction about the image")
    args = parser.parse_args()

    result = ask_vision(args.image, args.prompt)
    print(result)


if __name__ == "__main__":
    main()
