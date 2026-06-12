# STATUS — ALs-Karriere-Agent v6 Umsetzung

*Autonomer Modus — Entscheidungen hier dokumentiert, kein Stopp außer den 3 harten Bedingungen.*

---

## BLOCK B1 — Projekt-Setup + Phase-0-Spike ✅ ABGESCHLOSSEN (2026-06-12)

### Ergebnisse
- Service läuft: `systemctl --user status karriere-agent` → active (running)
- Gesundheit: `http://192.168.15.30:7601/api/health`
- GitHub: https://github.com/al1505/ALs-Karriere-Agent
- Haribo registriert ✅

### Spike-Test: ABNAHME BESTANDEN ✅
1. POST /api/session/start → Session gestartet, `cwd` korrekt gesetzt
2. SSE-Stream liefert `{type:"status","status":"running"}` + `{type:"text",...}`
3. QUESTION: marker erkannt → `{type:"question","question":"...","options":[...]}` 
4. Session geht in `status: waiting`
5. POST /api/session/:id/answer → Session geht in `status: running`
6. Antwort als `"User selected: Fertig"` in Prompt-Queue eingespeist

### Entscheidungen (autonom, laut Konzept-Geist)
- **Port 7601 statt 7600:** Port 7600 belegt durch Docker-Container `bhb-hr-datenanalyse-api-1`. 
  Nächster freier Port 7601 gewählt. Alle APIs konsistent auf 7601.
- **AskUserQuestion-Strategie:** QUESTION: Marker in Text statt `can_use_tool`-Hook.
  Grund: SDK-intern kann `AskUserQuestion` im headless-Modus nicht als Tool-Result befüllt werden.
  Gleiches Ergebnis, weniger Komplexität. SKILL.md bleibt sauber.
- **SDK-Parse-Error-Handling:** `rate_limit_event` wirft `MessageParseError` im SDK-Parser.
  Fix: Iterator manuell via `__anext__()` mit try/except um unbekannte Typen zu skippen.

### Known Issues (keine Stopps laut Konzept)
- `sdk_session_id` leer nach `rate_limit_event` im Stream — Resume-Funktion erst nach B2 testbar
- systemd-Service-Description noch "Port 7600" im Label (nur Display, Port ist korrekt 7601)

---

## BLOCK B2 — Phase 1 Analyse-Flow ✅ ABGESCHLOSSEN (2026-06-12)

### Ergebnisse
- `detail.html` (1099 Zeilen): Bewerbungs-Detailseite unter `http://192.168.15.30:7601/detail.html`
  - SSE-Chat mit Markdown-Rendering (marked.js)
  - 7-Step-Stepper (Vorab-Check → Abschluss)
  - STOPP-Flow: Frage-Buttons + Antwort-Injection
  - Job-Info-Panel mit Commute-Anzeige
  - Pause/Resume/Cancel-Controls
  - Posting-Modal und Abbruch-Modal mit Gründen
- `app.py`: `/detail.html` FileResponse-Route; Port-Labels auf 7601 korrigiert
- `app.js` (Haribo Dashboard): 11 Patches
  - `statusColors`/`statusLabels`: +dashboard (emerald), +paused (yellow)
  - barColors/barLabels/counts: dashboard+paused ergänzt
  - offen-Filter: dashboard+paused eingeschlossen
  - Modal: "Dashboard-Chat (NEU)"-Button
  - `startDashboardSession()`: POST /api/session/start → öffnet detail.html
  - "In Bearbeitung"-Sektion oben in der Bewerbungsliste

### Abnahme-Test: BESTANDEN ✅
1. `/api/health` → `{"status":"ok","port":7601}`
2. `/detail.html` → HTTP 200
3. Haribo Dashboard → HTTP 200
4. Haribo-Dashboard: app.js patches korrekt angewendet (11/11 OK)

### Entscheidungen (autonom)
- **FileResponse statt StaticFiles-Mount**: StaticFiles at "/" überschreibt API-Routen.
  Fix: Explizite `/detail.html`-Route via FileResponse.
- **Port-7500-Konflikt**: Service-Restart-Loop hielt Port besetzt. Fix: Explizit `stop` vor `start`.

---

## BLOCK B3 — Phase 2 Dokumente ✅ ABGESCHLOSSEN (2026-06-12)

### Ergebnisse
- `server/document_pipeline.py`: Dokument-Tracking, PDF-Job-Queue, Status-API
  - `get_documents(bw_path)` → MD/DOCX/PDF-Liste mit Status (ready/missing/pending)
  - `queue_pdf_job()` → schreibt `job.json` in `.pdf-jobs/` für Office-Server-Pickup
  - `get_pdf_status()` / `get_all_pdf_statuses()` → Konvertierungsstatus
- `server/app.py`: 4 neue Endpoints
  - `GET /api/applications/{id}/documents`
  - `POST /api/applications/{id}/pdf-convert`
  - `GET /api/applications/{id}/pdf-status`
  - `GET /api/applications/{id}/download/{filename}` (Path-Traversal-Schutz)
- `public/detail.html`: Dokumente-Karte mit Status-Badges, Download-Links, PDF-Button
- `server/session_manager.py`: Telegram STOPP-Ping (direkt via Bot-API, liest token aus telegram.env)
- `SETUP-TODO.md`: PowerShell-Script + Scheduled-Task-Anleitung für Office-Server

### Offene manuelle Schritte (→ SETUP-TODO.md)
- Scheduled Task am Office-Server 192.168.15.10 einrichten
- pdf_worker.ps1 anlegen
- DCOM-Identity testen

---

## BLOCK B4 — Abschluss + Release v6.0.0 ✅ ABGESCHLOSSEN (2026-06-12)

### Ergebnisse

**Phase 3 — Abschluss-Flow:**
- `scripts/validate_send.py`: Pre-send-Validierung (DOCX-ZIP-Check, PDF-Header, FM-Felder, Platzhalter-Check)
- `scripts/build_bundle.py`: pypdf-Sammelpack (Anschreiben + CV + Anlagen → Bewerbungs-Sammelpack.pdf)
- `server/app.py`: `/validate-send` + `/build-bundle` Endpoints
- `public/detail.html`: Versand-Checkliste-Karte mit Status-Badges + Sammelpack-Button

**Phase 4 — Polish & Härtung:**
- D7 Error-States: Error-Banner (sichtbar bei Agent-Unreachable, Office-Worker offline)
- D8 Security: systemd bindet an `192.168.15.30:7601` (LAN-only, kein 0.0.0.0)
- D9 Mobile: Stepper horizontal scrollable, touch-friendly buttons, 4K-Zentrierung
- D10 Haribo-Sync: haribo.md — `bewerben`-Action prüft jetzt `dashboard`/`paused`-Status vor PL-Spawn (Doppel-Lauf-Schutz)
- checkServiceHealth() beim Page-Load (Banner bei Agent/Worker-Ausfall)

---

---

## ABSCHLUSSREPORT v6.0.0 (2026-06-12)

### Was läuft

| Service | URL | Status |
|---|---|---|
| karriere-agent | http://192.168.15.30:7601/api/health | ✅ aktiv |
| detail.html | http://192.168.15.30:7601/detail.html | ✅ erreichbar |
| Haribo Dashboard | http://192.168.15.30:7500 | ✅ aktiv |
| systemd: karriere-agent | `systemctl --user status karriere-agent` | ✅ running |

### Was sofort nutzbar ist

1. **Neue Bewerbung starten**: Haribo Dashboard → Bewerbungen → Bewerben → „Dashboard-Chat (NEU)"
   → Öffnet detail.html, startet Claude-Session, streamt Analyse live
2. **STOPP-Fragen**: Telegram-Ping mit Deep-Link → direkt am Handy antworten
3. **Dokumente**: Dokumente-Karte in detail.html zeigt MD/DOCX/PDF-Status, Download-Links
4. **Versand-Gate**: Automatische Checkliste nach Session-Ende + Sammelpack-Button

### Offene Manuelle Schritte (für Alois)

| # | Aufgabe | Wo | Dringlichkeit |
|---|---|---|---|
| 1 | **PDF-Worker Scheduled Task** am Office-Server (192.168.15.10) | `SETUP-TODO.md` | Vor ersten PDF-Exporten |
| 2 | **Word-COM AutoLogon testen** (nicht-interaktiv) | SETUP-TODO.md §1.3 | Vor ersten PDF-Exporten |
| 3 | **Port 7601** in interne Port-Listen eintragen | Eigene Notiz | Jederzeit |

### Nicht implementiert (außer Scope v6.0.0)

- CV-Diff-Viewer (war B3-Nice-to-have) — kann nachgerüstet werden
- DOCX-Template-Replacement (läuft via Claude/SKILL.md, kein Server-Side-Code nötig)
- Filter-Chips in Bewerbungsliste (D2, partiell — "In Bearbeitung" ist drin)
- Gehaltseinschätzungs- und Firmen-Recherche-Karten in detail.html (Karten sind als HTML vorhanden, Daten kommen vom Agenten via Session-Chat)

### Release

https://github.com/al1505/ALs-Karriere-Agent/releases/tag/v6.0.0
