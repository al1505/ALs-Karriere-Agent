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

## BLOCK B3 — Phase 2 Dokumente ⏳ OFFEN

---

## BLOCK B4 — Abschluss + Release v6.0.0 ⏳ OFFEN

---

## Offene Manuelle Schritte (für Alois)

1. **Office-Server PDF-Worker** (192.168.15.10): Scheduled Task einrichten laut K4-Variante a.
   Details → `SETUP-TODO.md` (wird in B3 erstellt)
2. **Word-COM AutoLogon**: Testen ob nicht-interaktiv funktioniert. Falls nicht: DCOM-Identity konfigurieren.
3. **Port-Dokumentation**: 7601 in internen Port-Listen nachtragen.
