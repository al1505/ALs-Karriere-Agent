#!/usr/bin/env python3
"""
build_bundle.py — Build Bewerbungs-Sammelpack PDF.
Concatenates CV.pdf + Anschreiben.pdf + optional attachments.
Requires: pypdf

Usage: python build_bundle.py <bw_path> [--out <filename>]
Output: <bw_path>/Bewerbungs-Sammelpack.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

BUNDLE_ORDER = [
    "Anschreiben.pdf",
    "Custom-CV.pdf",
]
ATTACHMENT_PATTERNS = ["Zeugnis*.pdf", "Zertifikat*.pdf", "Anlage*.pdf"]


def build_bundle(bw_path: str, out_filename: str = "Bewerbungs-Sammelpack.pdf") -> dict:
    try:
        from pypdf import PdfWriter, PdfReader
    except ImportError:
        return {"ok": False, "error": "pypdf nicht installiert (pip install pypdf)"}

    root = Path(bw_path)
    if not root.is_dir():
        return {"ok": False, "error": f"Ordner nicht gefunden: {bw_path}"}

    writer = PdfWriter()
    included = []
    missing = []

    # Add in defined order
    for pdf_name in BUNDLE_ORDER:
        f = root / pdf_name
        if f.exists():
            reader = PdfReader(str(f))
            for page in reader.pages:
                writer.add_page(page)
            included.append(pdf_name)
        else:
            missing.append(pdf_name)

    # Add optional attachments
    for pattern in ATTACHMENT_PATTERNS:
        for f in sorted(root.glob(pattern)):
            if f.name not in included:
                try:
                    reader = PdfReader(str(f))
                    for page in reader.pages:
                        writer.add_page(page)
                    included.append(f.name)
                except Exception as e:
                    missing.append(f"{f.name} (Fehler: {e})")

    if not included:
        return {"ok": False, "error": "Keine PDFs gefunden", "missing": missing}

    out_path = root / out_filename
    with open(str(out_path), "wb") as fh:
        writer.write(fh)

    return {
        "ok": True,
        "bundle": str(out_path),
        "pages": len(writer.pages),
        "included": included,
        "missing": missing,
        "size": out_path.stat().st_size,
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    out = "Bewerbungs-Sammelpack.pdf"
    paths = []
    i = 0
    while i < len(args):
        if args[i] == "--out" and i + 1 < len(args):
            out = args[i + 1]
            i += 2
        else:
            paths.append(args[i])
            i += 1

    if not paths:
        print("Usage: build_bundle.py <bw_path> [--out <filename>]")
        sys.exit(2)

    result = build_bundle(paths[0], out)
    if result["ok"]:
        print(f"✅ Sammelpack: {result['bundle']} ({result['pages']} Seiten, {result['size']//1024} KB)")
        print(f"   Enthält: {', '.join(result['included'])}")
        if result.get("missing"):
            print(f"   Fehlend: {', '.join(result['missing'])}")
    else:
        print(f"❌ {result.get('error', 'Fehler')}")
        sys.exit(1)
