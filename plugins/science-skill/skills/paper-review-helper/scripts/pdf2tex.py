#!/usr/bin/env python
"""Convert PDF to LaTeX using Mathpix API.

Usage:
    python pdf2tex.py <pdf_path> [output_dir]

Environment variables:
    MATHPIX_APP_ID  - Mathpix application ID
    MATHPIX_API_KEY - Mathpix API key

Output:
    Extracts .tex file and images to output_dir (default: same dir as PDF)
"""

import os
import sys
import json
import time
import zipfile
import requests
from pathlib import Path

API_BASE = "https://api.mathpix.com/v3/pdf"


def get_credentials():
    app_id = os.environ.get("MATHPIX_APP_ID")
    app_key = os.environ.get("MATHPIX_API_KEY")
    if not app_id or not app_key:
        missing = []
        if not app_id:
            missing.append("MATHPIX_APP_ID")
        if not app_key:
            missing.append("MATHPIX_API_KEY")
        print(f"Error: Missing environment variables: {', '.join(missing)}", file=sys.stderr)
        print("Get credentials at https://accounts.mathpix.com/", file=sys.stderr)
        sys.exit(1)
    return {"app_id": app_id, "app_key": app_key}


def upload_pdf(pdf_path: Path, headers: dict) -> str:
    """Upload PDF and return pdf_id."""
    options = {
        "conversion_formats": {"tex.zip": True},
        "math_inline_delimiters": ["$", "$"],
        "rm_spaces": True,
    }
    with open(pdf_path, "rb") as f:
        resp = requests.post(
            API_BASE,
            headers=headers,
            data={"options_json": json.dumps(options)},
            files={"file": f},
        )
    resp.raise_for_status()
    data = resp.json()
    if "pdf_id" not in data:
        print(f"Error: {data}", file=sys.stderr)
        sys.exit(1)
    return data["pdf_id"]


def wait_for_completion(pdf_id: str, headers: dict, timeout: int = 600) -> dict:
    """Poll until processing completes. Returns final status data."""
    url = f"{API_BASE}/{pdf_id}"
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        pct = data.get("percent_done", 0)
        print(f"\rStatus: {status} ({pct}%)", end="", flush=True)
        if status == "completed":
            print()
            return data
        if status == "error":
            print(f"\nError: {data}", file=sys.stderr)
            sys.exit(1)
        time.sleep(2)
    print("\nTimeout waiting for conversion", file=sys.stderr)
    sys.exit(1)


def download_tex(pdf_id: str, headers: dict, output_dir: Path, status_data: dict) -> Path:
    """Download and extract tex.zip."""
    # Try to get URL from status response first
    tex_url = None
    if "tex.zip" in status_data:
        tex_url = status_data["tex.zip"].get("url")
    if not tex_url:
        tex_url = f"{API_BASE}/{pdf_id}.tex.zip"

    print(f"Downloading from: {tex_url}")
    resp = requests.get(tex_url, headers=headers)
    if resp.status_code == 404:
        # Fallback to .tex endpoint
        tex_url = f"{API_BASE}/{pdf_id}.tex"
        print(f"Trying fallback: {tex_url}")
        resp = requests.get(tex_url, headers=headers)
    resp.raise_for_status()

    zip_path = output_dir / f"{pdf_id}.tex.zip"
    with open(zip_path, "wb") as f:
        f.write(resp.content)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(output_dir)
    zip_path.unlink()
    # Search recursively for .tex files
    tex_files = list(output_dir.rglob("*.tex"))
    if tex_files:
        print(f"Extracted: {tex_files[0]}")
        return tex_files[0]
    return output_dir


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    pdf_path = Path(sys.argv[1]).resolve()
    if not pdf_path.exists():
        print(f"Error: {pdf_path} not found", file=sys.stderr)
        sys.exit(1)
    output_dir = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else pdf_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    headers = get_credentials()
    print(f"Uploading {pdf_path.name}...")
    pdf_id = upload_pdf(pdf_path, headers)
    print(f"Processing (id: {pdf_id})...")
    status_data = wait_for_completion(pdf_id, headers)
    tex_path = download_tex(pdf_id, headers, output_dir, status_data)
    print(f"Done: {tex_path}")


if __name__ == "__main__":
    main()
