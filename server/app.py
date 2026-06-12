"""
app.py — Karriere-Agent FastAPI Service (Port 7600)
Provides session management API for the Haribo Unified Dashboard.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from server import session_manager as sm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s]: %(message)s",
)
LOG = logging.getLogger("karriere-agent")

app = FastAPI(title="Karriere-Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:7500", "http://192.168.15.30:7500",
                   "http://localhost:7400", "http://192.168.15.30:7400"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MAIL_DB = Path.home() / "data" / "haribo-mail" / "mail.db"


# ─── DB migration (idempotent) ───────────────────────────────────────────────

def run_migrations():
    """Add v6 columns to applications + create session_events table."""
    try:
        conn = sqlite3.connect(str(MAIL_DB))
        # applications: v6 columns (additive only)
        for col, typedef in [
            ("cancel_reason", "TEXT DEFAULT ''"),
            ("paused_step", "TEXT DEFAULT ''"),
            ("agent_session_id", "TEXT DEFAULT ''"),
            ("progress_pct", "INTEGER DEFAULT 0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE applications ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                pass  # already exists

        # Update status CHECK if needed — skip, just add values as text
        # status values: dashboard, paused are now valid

        # session_events audit table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_events (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id INTEGER,
                session_id     TEXT NOT NULL,
                event_type     TEXT NOT NULL,
                data           TEXT DEFAULT '',
                created_at     TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sevt_app ON session_events(application_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sevt_sid ON session_events(session_id)")

        # job_postings: v6 columns
        for col, typedef in [
            ("standort", "TEXT DEFAULT ''"),
            ("arbeitsmodell", "TEXT DEFAULT ''"),
            ("gehalt_posting", "TEXT DEFAULT ''"),
            ("gehalt_einschaetzung", "TEXT DEFAULT ''"),
            ("geo_lat", "REAL"),
            ("geo_lon", "REAL"),
            ("commute_json", "TEXT DEFAULT ''"),
            ("company_research_json", "TEXT DEFAULT ''"),
            ("researched_at", "TEXT DEFAULT ''"),
        ]:
            try:
                conn.execute(f"ALTER TABLE job_postings ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                pass

        conn.commit()
        conn.close()
        LOG.info("DB migrations applied")
    except Exception as e:
        LOG.error("Migration error: %s", e)


@app.on_event("startup")
async def startup():
    run_migrations()
    LOG.info("Karriere-Agent started on port 7600")


# ─── Pydantic models ─────────────────────────────────────────────────────────

class StartSessionPayload(BaseModel):
    application_id: int
    initial_prompt: Optional[str] = None


class AnswerPayload(BaseModel):
    answer: str  # option label or free text


class CancelPayload(BaseModel):
    reason: str  # cancel reason text


class NewApplicationPayload(BaseModel):
    source: str  # "url" | "text" | "initiative"
    firma: Optional[str] = None
    zielrolle: Optional[str] = None
    ansprechpartner: Optional[str] = None
    posting_text: Optional[str] = None
    url: Optional[str] = None
    job_posting_id: Optional[int] = None


# ─── Health ──────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "karriere-agent", "port": 7600}


# ─── Session API ─────────────────────────────────────────────────────────────

@app.post("/api/session/start")
async def session_start(payload: StartSessionPayload):
    try:
        state = await sm.start_session(
            application_id=payload.application_id,
            initial_prompt=payload.initial_prompt or "",
        )
        return {
            "session_id": state.session_id,
            "application_id": state.application_id,
            "status": state.status,
            "cwd": state.cwd,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        LOG.error("session_start error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/session/{session_id}/stream")
async def session_stream(session_id: str):
    """SSE endpoint — streams events from the career session."""
    return StreamingResponse(
        sm.stream_session_events(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/session/{session_id}")
async def session_get(session_id: str):
    state = sm.get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": state.session_id,
        "application_id": state.application_id,
        "status": state.status,
        "current_question": state.current_question,
        "sdk_session_id": state.sdk_session_id,
        "error": state.error,
    }


@app.post("/api/session/{session_id}/answer")
async def session_answer(session_id: str, payload: AnswerPayload):
    ok = await sm.send_answer(session_id, payload.answer)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


@app.post("/api/session/{session_id}/pause")
async def session_pause(session_id: str):
    ok = await sm.pause_session(session_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Cannot pause session in current state")
    return {"ok": True}


@app.post("/api/session/{session_id}/resume")
async def session_resume(session_id: str):
    ok = await sm.send_answer(session_id, "__resume__")
    return {"ok": ok}


@app.post("/api/session/{session_id}/stop")
async def session_stop(session_id: str):
    ok = await sm.stop_session(session_id)
    return {"ok": ok}


# ─── Application lifecycle API (proxied to main DB) ──────────────────────────

@app.post("/api/applications/{app_id}/pause")
async def app_pause(app_id: int):
    """Pause the active session for an application."""
    sessions = [s for s in sm._sessions.values() if s.application_id == app_id]
    for s in sessions:
        await sm.pause_session(s.session_id)
    sm._update_application_status(app_id, status="paused")
    return {"ok": True}


@app.post("/api/applications/{app_id}/cancel")
async def app_cancel(app_id: int, payload: CancelPayload):
    """Cancel application with mandatory reason."""
    sessions = [s for s in sm._sessions.values() if s.application_id == app_id]
    for s in sessions:
        await sm.stop_session(s.session_id)
    sm._update_application_status(
        app_id,
        status="cancelled",
        cancel_reason=payload.reason,
    )
    # Write outcome.md
    try:
        rows = _get_application_rows(app_id)
        if rows:
            app_path = rows.get("application_path", "")
            if app_path and Path(app_path).is_dir():
                outcome = Path(app_path) / "outcome.md"
                outcome.write_text(
                    f"# Bewerbung verworfen\n\nGrund: {payload.reason}\n\nDatum: {_now()}\n",
                    encoding="utf-8",
                )
    except Exception as e:
        LOG.warning("outcome.md write failed: %s", e)
    return {"ok": True}


@app.post("/api/applications/{app_id}/resume")
async def app_resume(app_id: int):
    """Resume a paused application session."""
    sessions = [s for s in sm._sessions.values() if s.application_id == app_id
                and s.status == "paused"]
    for s in sessions:
        await sm.send_answer(s.session_id, "__resume__")
    return {"ok": True}


@app.get("/api/applications/{app_id}/posting")
async def app_posting(app_id: int):
    """Return job-posting.md content for an application."""
    rows = _get_application_rows(app_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Application not found")
    app_path = rows.get("application_path", "")
    posting = None
    for candidate in [
        Path(app_path) / "job-posting.md" if app_path else None,
    ]:
        if candidate and candidate.exists():
            posting = candidate.read_text(encoding="utf-8")
            break
    if posting is None:
        raise HTTPException(status_code=404, detail="job-posting.md not found")
    return {"content": posting}


@app.get("/api/applications/{app_id}/events")
async def app_events(app_id: int, limit: int = 100):
    """Return session_events for an application (transcript)."""
    try:
        conn = sqlite3.connect(str(MAIL_DB))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM session_events WHERE application_id=? ORDER BY created_at DESC LIMIT ?",
            (app_id, limit),
        ).fetchall()
        conn.close()
        return {"events": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── New application creation ─────────────────────────────────────────────────

@app.post("/api/applications/new")
async def new_application(payload: NewApplicationPayload):
    """
    Create a new application from URL, paste text, or initiative.
    Returns application_id + suggested BW-folder path.
    """
    import re as _re
    from datetime import datetime as _dt

    firma = payload.firma or "Unbekannt"
    firma_safe = _re.sub(r"[^\w\-]", "_", firma)
    now = _dt.now().strftime("%Y-%m")

    if payload.source == "initiative":
        zielrolle = payload.zielrolle or "CIO"
        folder_name = f"Initiativbewerbung-{now}"
        bw_path = Path.home() / "CV" / "Bewerbungen" / firma_safe / folder_name
    else:
        rolle_safe = _re.sub(r"[^\w\-]", "_", payload.zielrolle or "Stelle")
        folder_name = f"{rolle_safe}-{now}"
        bw_path = Path.home() / "CV" / "Bewerbungen" / firma_safe / folder_name

    bw_path.mkdir(parents=True, exist_ok=True)

    # Write job-posting.md skeleton
    posting_path = bw_path / "job-posting.md"
    if not posting_path.exists():
        frontmatter_lines = [
            "---",
            f"firma: {firma}",
            f"rolle: {payload.zielrolle or ''}",
            f"quelle: {payload.source}",
        ]
        if payload.url:
            frontmatter_lines.append(f"url: {payload.url}")
        if payload.source == "initiative":
            frontmatter_lines.append("initiativbewerbung: true")
        frontmatter_lines.append("---")
        frontmatter_lines.append("")

        if payload.posting_text:
            frontmatter_lines.append(payload.posting_text)
        elif payload.source == "initiative":
            frontmatter_lines.append(
                f"Initiativbewerbung an {firma} als {payload.zielrolle or 'CIO'}."
            )

        posting_path.write_text("\n".join(frontmatter_lines), encoding="utf-8")

    # Create application DB entry
    try:
        conn = sqlite3.connect(str(MAIL_DB))
        # Find matching job_posting if available
        jp_id = payload.job_posting_id
        if jp_id is None and payload.url:
            row = conn.execute(
                "SELECT id FROM job_postings WHERE url=? LIMIT 1", (payload.url,)
            ).fetchone()
            if row:
                jp_id = row[0]

        cur = conn.execute(
            "INSERT INTO applications (job_posting_id, status, application_path, company, title, created_at, updated_at) "
            "VALUES (?, 'dashboard', ?, ?, ?, datetime('now'), datetime('now'))",
            (jp_id, str(bw_path), firma, payload.zielrolle or ""),
        )
        app_id = cur.lastrowid
        conn.commit()
        conn.close()
    except Exception as e:
        LOG.error("new_application DB error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "application_id": app_id,
        "bw_path": str(bw_path),
        "posting_path": str(posting_path),
    }


# ─── Commute service (D4) ─────────────────────────────────────────────────────

KRIEGLACH_LAT = 47.5478
KRIEGLACH_LON = 15.5613


@app.get("/api/commute")
async def get_commute(job_posting_id: int):
    """Calculate commute from Krieglach to job location."""
    try:
        conn = sqlite3.connect(str(MAIL_DB))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT location, standort, geo_lat, geo_lon, commute_json FROM job_postings WHERE id=?",
            (job_posting_id,),
        ).fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Job posting not found")

        if row["commute_json"]:
            return json.loads(row["commute_json"])

        location = row["standort"] or row["location"] or ""
        result = await _calculate_commute(location, job_posting_id, row["geo_lat"], row["geo_lon"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        LOG.error("Commute error: %s", e)
        return {"error": str(e), "fallback": "Anfahrt manuell pruefen"}


async def _calculate_commute(location: str, job_posting_id: int, cached_lat, cached_lon):
    """Geocode location + calculate driving/train commute."""
    import urllib.request
    import urllib.parse

    lat, lon = cached_lat, cached_lon

    if not lat and location:
        try:
            q = urllib.parse.quote(location + ", Austria")
            url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1"
            req = urllib.request.Request(url, headers={"User-Agent": "ALs-Karriere-Agent/1.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            if data:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
        except Exception as e:
            LOG.warning("Geocoding failed for %s: %s", location, e)

    car_km = None
    car_min = None
    if lat and lon:
        try:
            url = (
                f"https://router.project-osrm.org/route/v1/driving/"
                f"{KRIEGLACH_LON},{KRIEGLACH_LAT};{lon},{lat}"
                f"?overview=false"
            )
            resp = urllib.request.urlopen(url, timeout=15)
            data = json.loads(resp.read())
            if data.get("routes"):
                route = data["routes"][0]
                car_km = round(route["distance"] / 1000, 1)
                car_min = round(route["duration"] / 60)
        except Exception as e:
            LOG.warning("OSRM routing failed: %s", e)

    # Train heuristic (straight-line distance * 1.4 / 80 km/h average)
    train_min = None
    if lat and lon:
        import math
        dx = (lon - KRIEGLACH_LON) * 111.32 * math.cos(math.radians(KRIEGLACH_LAT))
        dy = (lat - KRIEGLACH_LAT) * 110.57
        straight_km = math.sqrt(dx**2 + dy**2)
        train_km = straight_km * 1.4
        train_min = round(train_km / 80 * 60)

    # Pendel recommendation
    pendel = "Anfahrt manuell pruefen"
    if car_min:
        if car_min <= 60:
            pendel = "Tagespendeln problemlos"
        elif car_min <= 100:
            pendel = "Tagespendeln grenzwertig"
        else:
            pendel = "Wochenpendeln empfohlen"

    result = {
        "location": location,
        "car": {"km": car_km, "min": car_min} if car_km else None,
        "train": {"min": train_min} if train_min else None,
        "pendel": pendel,
        "lat": lat,
        "lon": lon,
    }

    if job_posting_id and lat:
        try:
            conn = sqlite3.connect(str(MAIL_DB))
            conn.execute(
                "UPDATE job_postings SET geo_lat=?, geo_lon=?, commute_json=? WHERE id=?",
                (lat, lon, json.dumps(result), job_posting_id),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    return result


# ─── Settings / Provider config ──────────────────────────────────────────────

@app.get("/api/settings/providers")
async def get_providers():
    config_path = Path.home() / ".config" / "haribo" / "provider-config.json"
    if not config_path.exists():
        return {"providers": {}}
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    # Inject karriere_agent defaults if missing
    ka = cfg.setdefault("karriere_agent", {
        "provider": "claude",
        "model": "sonnet",
        "max_parallel_sessions": 1,
        "cost_limit_eur_per_application": 2.0,
        "pdf_worker": "office-server",
        "telegram_pings": True,
    })
    return {"providers": cfg.get("providers", {}), "karriere_agent": ka}


@app.post("/api/settings/providers")
async def update_providers(payload: dict):
    config_path = Path.home() / ".config" / "haribo" / "provider-config.json"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="provider-config.json not found")
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    if "karriere_agent" in payload:
        cfg["karriere_agent"] = payload["karriere_agent"]
    config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}


# ─── PDF Worker status ────────────────────────────────────────────────────────

@app.get("/api/pdf-worker/status")
async def pdf_worker_status():
    """Check if Office Server PDF worker is reachable."""
    import socket
    office_server = "192.168.15.10"
    try:
        socket.setdefaulttimeout(2)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((office_server, 445))
        sock.close()
        online = result == 0
    except Exception:
        online = False
    return {"office_server": office_server, "online": online, "method": "queue"}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_application_rows(app_id: int):
    try:
        conn = sqlite3.connect(str(MAIL_DB))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def _now():
    return datetime.now(timezone.utc).isoformat()
