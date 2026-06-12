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

## BLOCK B2 — Phase 1 Analyse-Flow 🔄 IN ARBEIT

### Geplante Änderungen
- Dashboard (7500): Detailseite mit Chat-Panel, Stepper, Job-Info-Panel
- Listen-Umbau: Filter-Chips, "In Bearbeitung"-Sektion oben (D1-D3, D11)
- Commute-Service (D4) — bereits in app.py implementiert
- DB-Migrationen (D1, D6, D12) — bereits bei Startup angewendet
- Responsive-Grundgerüst (D13)

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
