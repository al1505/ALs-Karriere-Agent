"""
document_pipeline.py — Document status tracking + PDF job queue
Manages the MD → DOCX → PDF pipeline for each Bewerbung.
PDF conversion uses a job-queue approach: NUC writes job.json,
Office Server (192.168.15.10) picks it up via Scheduled Task.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger("karriere-agent.docs")

# File patterns tracked per Bewerbung folder
TRACKED_PATTERNS = [
    "Custom-CV.md",
    "Anschreiben.md",
    "changes.md",
    "*.docx",
    "*.pdf",
    "job-posting.md",
    "outcome.md",
]

# Files that map through the MD → DOCX → PDF chain
DOCX_CHAIN = {
    "Custom-CV.md": "Custom-CV.docx",
    "Anschreiben.md": "Anschreiben.docx",
}
PDF_CHAIN = {
    "Custom-CV.docx": "Custom-CV.pdf",
    "Anschreiben.docx": "Anschreiben.pdf",
}


def _bw_path(app_data: dict) -> Path | None:
    p = app_data.get("application_path") or ""
    if p and Path(p).is_dir():
        return Path(p)
    return None


def get_documents(bw_path: str | Path) -> list[dict]:
    """
    Return a list of tracked documents for a Bewerbung folder.
    Each entry: {name, path, size, modified, type, status, download_url}
    status: "ready" | "missing" | "pending"
    """
    root = Path(bw_path)
    if not root.is_dir():
        return []

    seen = set()
    docs = []

    def _entry(f: Path, file_type: str, status: str = "ready") -> dict:
        return {
            "name": f.name,
            "path": str(f),
            "size": f.stat().st_size if f.exists() else 0,
            "modified": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat() if f.exists() else "",
            "type": file_type,
            "status": status,
        }

    # Scan for existing files
    for pattern in TRACKED_PATTERNS:
        for f in sorted(root.glob(pattern)):
            if f.name in seen:
                continue
            seen.add(f.name)
            if f.suffix == ".md":
                docs.append(_entry(f, "markdown"))
            elif f.suffix == ".docx":
                # Check if a pending PDF job exists
                pdf_name = PDF_CHAIN.get(f.name, f.stem + ".pdf")
                pdf_path = root / pdf_name
                job_dir = root / ".pdf-jobs"
                job_file = job_dir / f"{f.stem}.job.json"
                done_file = job_dir / f"{f.stem}.done.json"

                docs.append(_entry(f, "docx"))

                if pdf_path.exists():
                    if pdf_path.name not in seen:
                        seen.add(pdf_path.name)
                        docs.append(_entry(pdf_path, "pdf"))
                elif done_file.exists():
                    # done but PDF might have moved or name mismatch
                    docs.append({"name": pdf_name, "path": "", "size": 0, "modified": "",
                                 "type": "pdf", "status": "ready_check"})
                    if pdf_name not in seen:
                        seen.add(pdf_name)
                elif job_file.exists():
                    docs.append({"name": pdf_name, "path": "", "size": 0, "modified": "",
                                 "type": "pdf", "status": "pending"})
                    if pdf_name not in seen:
                        seen.add(pdf_name)
            elif f.suffix == ".pdf":
                if f.name not in seen:
                    seen.add(f.name)
                    docs.append(_entry(f, "pdf"))

    # Add placeholder entries for expected-but-missing chain targets
    for md_name, docx_name in DOCX_CHAIN.items():
        if (root / md_name).exists() and docx_name not in seen:
            seen.add(docx_name)
            docs.append({"name": docx_name, "path": "", "size": 0, "modified": "",
                         "type": "docx", "status": "missing"})

    return docs


def queue_pdf_job(bw_path: str | Path, docx_filename: str) -> dict:
    """
    Write a PDF conversion job for the given DOCX file.
    The Office Server Scheduled Task picks this up.
    Returns: {job_id, job_file, status}
    """
    root = Path(bw_path)
    docx_path = root / docx_filename
    if not docx_path.exists():
        raise FileNotFoundError(f"DOCX not found: {docx_path}")

    job_dir = root / ".pdf-jobs"
    job_dir.mkdir(parents=True, exist_ok=True)

    job_id = str(uuid.uuid4())[:8]
    stem = docx_path.stem
    job_file = job_dir / f"{stem}.job.json"
    done_file = job_dir / f"{stem}.done.json"

    # Remove stale done marker if DOCX is newer
    if done_file.exists():
        done_mtime = done_file.stat().st_mtime
        docx_mtime = docx_path.stat().st_mtime
        if docx_mtime > done_mtime:
            done_file.unlink()

    job = {
        "job_id": job_id,
        "docx_path": str(docx_path),
        "docx_filename": docx_filename,
        "pdf_filename": stem + ".pdf",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "queued",
    }
    job_file.write_text(json.dumps(job, indent=2), encoding="utf-8")
    LOG.info("PDF job queued: %s → %s.pdf", docx_filename, stem)
    return {"job_id": job_id, "job_file": str(job_file), "status": "queued"}


def get_pdf_status(bw_path: str | Path, docx_filename: str) -> dict:
    """
    Check status of a PDF conversion job.
    Returns: {status: queued|converting|done|error|not_found, pdf_path?, error?}
    """
    root = Path(bw_path)
    stem = Path(docx_filename).stem
    job_dir = root / ".pdf-jobs"
    job_file = job_dir / f"{stem}.job.json"
    done_file = job_dir / f"{stem}.done.json"
    err_file = job_dir / f"{stem}.error.json"
    pdf_path = root / (stem + ".pdf")

    if pdf_path.exists():
        return {"status": "done", "pdf_path": str(pdf_path)}
    if done_file.exists():
        try:
            done = json.loads(done_file.read_text(encoding="utf-8"))
            if done.get("error"):
                return {"status": "error", "error": done["error"]}
            return {"status": "done", "pdf_path": done.get("pdf_path", "")}
        except Exception:
            return {"status": "done", "pdf_path": ""}
    if err_file.exists():
        try:
            err = json.loads(err_file.read_text(encoding="utf-8"))
            return {"status": "error", "error": err.get("error", "unknown error")}
        except Exception:
            return {"status": "error", "error": "conversion failed"}
    if job_file.exists():
        try:
            job = json.loads(job_file.read_text(encoding="utf-8"))
            return {"status": job.get("status", "queued")}
        except Exception:
            return {"status": "queued"}
    return {"status": "not_found"}


def get_all_pdf_statuses(bw_path: str | Path) -> dict:
    """Return PDF status for all tracked DOCX files in the folder."""
    root = Path(bw_path)
    result = {}
    for docx_name in PDF_CHAIN:
        if (root / docx_name).exists():
            result[docx_name] = get_pdf_status(bw_path, docx_name)
    return result


def list_downloadable(bw_path: str | Path) -> list[dict]:
    """Return files available for download (existing MD, DOCX, PDF)."""
    root = Path(bw_path)
    if not root.is_dir():
        return []
    result = []
    for pattern in ["*.md", "*.docx", "*.pdf"]:
        for f in sorted(root.glob(pattern)):
            if f.name.startswith("."):
                continue
            result.append({
                "name": f.name,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(
                    f.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
                "type": f.suffix.lstrip("."),
            })
    return result
