#!/usr/bin/env python3
"""
validate_send.py — Pre-send validation for a Bewerbung folder.
Checks: required documents exist, DOCX is valid ZIP, frontmatter complete.
Exit: 0 = OK, 1 = failures.
Usage: python validate_send.py <bw_path> [--json]
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

REQUIRED_DOCS = ["job-posting.md", "Custom-CV.md", "Anschreiben.md"]
REQUIRED_DOCX = ["Custom-CV.docx", "Anschreiben.docx"]
REQUIRED_PDF  = ["Custom-CV.pdf", "Anschreiben.pdf"]
REQUIRED_FRONTMATTER = ["firma", "rolle"]


def validate(bw_path: str) -> dict:
    root = Path(bw_path)
    checks = []
    ok = True

    def fail(name, msg):
        nonlocal ok
        ok = False
        checks.append({"name": name, "ok": False, "msg": msg})

    def pass_(name, msg=""):
        checks.append({"name": name, "ok": True, "msg": msg})

    if not root.is_dir():
        fail("Ordner", f"Bewerbungsordner nicht gefunden: {bw_path}")
        return {"ok": False, "checks": checks}

    # Check required MD docs
    for doc in REQUIRED_DOCS:
        f = root / doc
        if f.exists() and f.stat().st_size > 50:
            pass_(doc, f"{f.stat().st_size} Bytes")
        else:
            fail(doc, "Fehlt oder leer")

    # Check job-posting.md frontmatter
    posting = root / "job-posting.md"
    if posting.exists():
        text = posting.read_text(encoding="utf-8")
        if text.startswith("---"):
            fm_end = text.find("---", 3)
            if fm_end > 0:
                fm = text[3:fm_end]
                for key in REQUIRED_FRONTMATTER:
                    if f"{key}:" in fm:
                        pass_(f"FM: {key}")
                    else:
                        fail(f"FM: {key}", f"Frontmatter-Feld '{key}' fehlt")
            else:
                fail("Frontmatter", "Kein schließendes ---")
        else:
            fail("Frontmatter", "job-posting.md hat kein YAML-Frontmatter")

    # Check DOCX validity (must be valid ZIP)
    for docx_name in REQUIRED_DOCX:
        f = root / docx_name
        if not f.exists():
            fail(docx_name, "Fehlt")
            continue
        try:
            with zipfile.ZipFile(f) as z:
                names = z.namelist()
                if "word/document.xml" not in names:
                    fail(docx_name, "Kein word/document.xml — kein gültiges DOCX")
                else:
                    pass_(docx_name, f"{f.stat().st_size // 1024} KB, ZIP-Struktur OK")
        except zipfile.BadZipFile:
            fail(docx_name, "Kein gültiges ZIP/DOCX")

    # Check PDFs
    for pdf_name in REQUIRED_PDF:
        f = root / pdf_name
        if f.exists() and f.stat().st_size > 1024:
            # Minimal PDF header check
            with open(f, "rb") as fh:
                header = fh.read(5)
            if header.startswith(b"%PDF-"):
                pass_(pdf_name, f"{f.stat().st_size // 1024} KB")
            else:
                fail(pdf_name, "Kein gültiges PDF (kein %PDF- Header)")
        else:
            # PDF conversion not done yet — soft warning
            checks.append({"name": pdf_name, "ok": None, "msg": "Ausstehend (PDF-Konvertierung)"})

    # Check no empty placeholder
    cv = root / "Custom-CV.md"
    if cv.exists():
        content = cv.read_text(encoding="utf-8")
        placeholder_markers = ["TODO", "PLACEHOLDER", "{{", "INSERT_"]
        for marker in placeholder_markers:
            if marker in content:
                fail("CV-Platzhalter", f"'{marker}' gefunden in Custom-CV.md")
                break
        else:
            pass_("CV-Platzhalter", "Keine Platzhalter")

    return {"ok": ok, "checks": checks, "path": str(root)}


if __name__ == "__main__":
    args = sys.argv[1:]
    as_json = "--json" in args
    paths = [a for a in args if not a.startswith("--")]

    if not paths:
        print("Usage: validate_send.py <bw_path> [--json]")
        sys.exit(2)

    result = validate(paths[0])

    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"{'✅' if result['ok'] else '❌'} Validierung: {paths[0]}")
        for c in result["checks"]:
            sym = "✅" if c["ok"] is True else ("⏳" if c["ok"] is None else "❌")
            print(f"  {sym} {c['name']}: {c['msg']}")

    sys.exit(0 if result["ok"] else 1)
