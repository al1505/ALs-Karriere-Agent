"""
session_manager.py — Karriere-Agent Session Management
Manages claude-code-sdk sessions per Bewerbung. Each session is stateful:
- Streams messages as SSE events
- Intercepts QUESTION: markers from Claude output
- Awaits user answers before continuing
- Supports pause / resume / cancel
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG = logging.getLogger("karriere-agent.sessions")

MAIL_DB = Path.home() / "data" / "haribo-mail" / "mail.db"
SKILL_PATH = Path.home() / "projects" / "ALs-Karriere-Coach" / "SKILL.md"

DASHBOARD_SYSTEM_ADDENDUM = """

---
## DASHBOARD MODE (SDK) — PFLICHTLESEN

Du laefst im Karriere-Dashboard (SDK-Modus, kein interaktiver Terminal).

**STOPP-Fragen (AP5 / Regel 20):**
Statt AskUserQuestion zu nutzen, gib exakt diese Zeile aus (JSON auf einer Zeile):
QUESTION:{"question":"<Text>","options":[{"label":"<Label>","description":"<Beschreibung>"},...]}

Danach STOPP -- warte auf die naechste User-Nachricht, die die Auswahl enthaelt: "User selected: <Label>".
Fahre dann mit dem Flow fort als waere diese Option gewaehlt worden.

Nutze AskUserQuestion NICHT im Dashboard-Modus.

**Streaming:**
Gib alle Karten/Tabellen/Ergebnisse direkt als Markdown-Text aus -- der Chat-Renderer zeigt sie an.
Commit-/Schreiboperationen: Fuehre sie direkt aus (bypassPermissions ist aktiv).
"""


@dataclass
class SessionState:
    session_id: str
    application_id: int
    cwd: str
    status: str = "starting"
    events: asyncio.Queue = field(default_factory=asyncio.Queue)
    answer_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: Any = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_event_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    current_question: dict = field(default_factory=dict)
    sdk_session_id: str = ""
    error: str = ""


_sessions: dict[str, SessionState] = {}


def get_session(session_id: str):
    return _sessions.get(session_id)


def list_sessions():
    return [
        {
            "session_id": s.session_id,
            "application_id": s.application_id,
            "status": s.status,
            "created_at": s.created_at,
        }
        for s in _sessions.values()
    ]


def _load_skill():
    if SKILL_PATH.exists():
        return SKILL_PATH.read_text(encoding="utf-8") + DASHBOARD_SYSTEM_ADDENDUM
    LOG.warning("SKILL.md not found at %s", SKILL_PATH)
    return DASHBOARD_SYSTEM_ADDENDUM


def _get_application(application_id: int):
    try:
        conn = sqlite3.connect(str(MAIL_DB))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT a.id, a.application_path, a.status, a.company, a.title,
                      j.title AS jp_title, j.company AS jp_company, j.location,
                      j.salary_info, j.url, j.stage2_score, j.stage2_summary
               FROM applications a
               LEFT JOIN job_postings j ON j.id = a.job_posting_id
               WHERE a.id = ?""",
            (application_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        LOG.error("DB read error: %s", e)
        return None


def _update_application_status(application_id, status=None, agent_session_id=None,
                                paused_step=None, cancel_reason=None, progress_pct=None):
    try:
        conn = sqlite3.connect(str(MAIL_DB))
        updates = []
        params = []
        if status is not None:
            updates.append("status=?")
            params.append(status)
        if agent_session_id is not None:
            updates.append("agent_session_id=?")
            params.append(agent_session_id)
        if paused_step is not None:
            updates.append("paused_step=?")
            params.append(paused_step)
        if cancel_reason is not None:
            updates.append("cancel_reason=?")
            params.append(cancel_reason)
        if progress_pct is not None:
            updates.append("progress_pct=?")
            params.append(progress_pct)
        updates.append("updated_at=datetime('now')")
        params.append(application_id)
        conn.execute(f"UPDATE applications SET {', '.join(updates)} WHERE id=?", params)
        conn.commit()
        conn.close()
    except Exception as e:
        LOG.error("DB write error: %s", e)


def _log_session_event(application_id, session_id, event_type, data):
    try:
        conn = sqlite3.connect(str(MAIL_DB))
        conn.execute(
            "INSERT INTO session_events (application_id, session_id, event_type, data, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (application_id, session_id, event_type, data),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


QUESTION_RE = re.compile(r"QUESTION:(\{.*\})\s*$", re.MULTILINE)


def _extract_questions(text):
    results = []
    for m in QUESTION_RE.finditer(text):
        try:
            results.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            pass
    return results


def _estimate_progress(question):
    q = (question.get("question") or "").lower()
    if "s0" in q or "vorab" in q:
        return 15
    if "fitgap" in q or "stage" in q:
        return 40
    if "cv" in q or "anschreiben" in q:
        return 65
    if "pdf" in q or "versand" in q:
        return 85
    return 50


async def _run_session(state: SessionState, initial_prompt: str):
    from claude_code_sdk import ClaudeSDKClient, ClaudeCodeOptions
    from claude_code_sdk.types import AssistantMessage, TextBlock, ResultMessage

    skill_text = _load_skill()

    opts = ClaudeCodeOptions(
        system_prompt=skill_text,
        cwd=state.cwd,
        permission_mode="bypassPermissions",
        max_turns=80,
    )

    prompt_q: asyncio.Queue = asyncio.Queue()
    await prompt_q.put({
        "type": "user",
        "message": {"role": "user", "content": initial_prompt},
        "parent_tool_use_id": None,
        "session_id": None,
    })

    async def prompt_stream():
        while True:
            item = await prompt_q.get()
            if item is None:
                return
            yield item

    client = ClaudeSDKClient(options=opts)

    try:
        await client.connect(prompt=prompt_stream())
        state.status = "running"
        await state.events.put({"type": "status", "status": "running"})

        async for msg in client.receive_messages():
            state.last_event_at = datetime.now(timezone.utc).isoformat()

            if isinstance(msg, ResultMessage):
                state.sdk_session_id = msg.session_id or ""
                _update_application_status(state.application_id, agent_session_id=state.sdk_session_id)
                state.status = "completed"
                await state.events.put({"type": "status", "status": "completed"})
                _log_session_event(state.application_id, state.session_id, "completed", "")
                break

            if isinstance(msg, AssistantMessage):
                text_parts = [b.text for b in msg.content if isinstance(b, TextBlock)]
                full_text = "".join(text_parts)
                if not full_text:
                    continue

                await state.events.put({"type": "text", "text": full_text})
                _log_session_event(state.application_id, state.session_id, "assistant_text", full_text[:500])

                questions = _extract_questions(full_text)
                for q in questions:
                    state.status = "waiting"
                    state.current_question = q
                    _update_application_status(
                        state.application_id,
                        status="dashboard",
                        paused_step=q.get("question", "")[:100],
                        progress_pct=_estimate_progress(q),
                    )
                    await state.events.put({"type": "question", **q})
                    _log_session_event(state.application_id, state.session_id, "question", json.dumps(q))

                    answer = await state.answer_queue.get()

                    if answer == "__stop__":
                        state.status = "cancelled"
                        await prompt_q.put(None)
                        return

                    if answer == "__pause__":
                        state.status = "paused"
                        _update_application_status(state.application_id, status="paused")
                        await state.events.put({"type": "status", "status": "paused"})
                        while True:
                            cmd = await state.answer_queue.get()
                            if cmd == "__resume__":
                                state.status = "running"
                                await state.events.put({"type": "status", "status": "running"})
                                break
                            if cmd == "__stop__":
                                state.status = "cancelled"
                                await prompt_q.put(None)
                                return

                    state.status = "running"
                    state.current_question = {}
                    await prompt_q.put({
                        "type": "user",
                        "message": {"role": "user", "content": f"User selected: {answer}"},
                        "parent_tool_use_id": None,
                        "session_id": state.sdk_session_id or None,
                    })
                    _log_session_event(state.application_id, state.session_id, "user_answer", answer)

    except Exception as e:
        LOG.error("Session %s error: %s", state.session_id, e, exc_info=True)
        state.status = "error"
        state.error = str(e)
        await state.events.put({"type": "error", "message": str(e)})
        _log_session_event(state.application_id, state.session_id, "error", str(e))
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
        await state.events.put(None)


async def start_session(application_id: int, initial_prompt: str = ""):
    app_data = _get_application(application_id)
    if not app_data:
        raise ValueError(f"Application {application_id} not found")

    app_path = app_data.get("application_path") or ""
    if app_path and Path(app_path).is_dir():
        cwd = app_path
    else:
        company = app_data.get("company") or app_data.get("jp_company") or "Unbekannt"
        company_safe = re.sub(r"[^\w\-]", "_", company)
        bw_base = Path.home() / "CV" / "Bewerbungen" / company_safe
        bw_base.mkdir(parents=True, exist_ok=True)
        cwd = str(bw_base)

    state = SessionState(
        session_id=str(uuid.uuid4()),
        application_id=application_id,
        cwd=cwd,
    )
    _sessions[state.session_id] = state

    if not initial_prompt:
        initial_prompt = _build_initial_prompt(app_data)

    _update_application_status(application_id, status="dashboard", agent_session_id=state.session_id)
    _log_session_event(application_id, state.session_id, "started", json.dumps({"cwd": cwd}))

    loop = asyncio.get_event_loop()
    state.task = loop.create_task(_run_session(state, initial_prompt))

    return state


def _build_initial_prompt(app_data: dict) -> str:
    company = app_data.get("company") or app_data.get("jp_company") or "Unbekannt"
    title = app_data.get("title") or app_data.get("jp_title") or "IT-Fuehrungsrolle"
    location = app_data.get("location") or "k.A."
    score = app_data.get("stage2_score") or ""
    summary = app_data.get("stage2_summary") or ""

    parts = [
        "Neue Bewerbung analysieren und vollstaendig vorbereiten.",
        f"Unternehmen: {company}",
        f"Stelle: {title}",
        f"Ort: {location}",
    ]
    if score:
        parts.append(f"Haribo Stage-1 Score: {score}/10 -- {summary}")
    parts.append("Lade job-posting.md aus dem aktuellen Verzeichnis und starte mit Schritt S0.")
    return "\n".join(parts)


async def send_answer(session_id: str, answer: str) -> bool:
    state = _sessions.get(session_id)
    if not state:
        return False
    await state.answer_queue.put(answer)
    return True


async def pause_session(session_id: str) -> bool:
    state = _sessions.get(session_id)
    if not state or state.status not in ("running", "waiting"):
        return False
    await state.answer_queue.put("__pause__")
    return True


async def stop_session(session_id: str) -> bool:
    state = _sessions.get(session_id)
    if not state:
        return False
    await state.answer_queue.put("__stop__")
    return True


async def stream_session_events(session_id: str):
    state = _sessions.get(session_id)
    if not state:
        yield f"data: {json.dumps({'type': 'error', 'message': 'Session not found'})}\n\n"
        return

    while True:
        event = await state.events.get()
        if event is None:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        yield f"data: {json.dumps(event)}\n\n"
