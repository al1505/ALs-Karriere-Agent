# ALs-Karriere-Agent

FastAPI service (Port 7600) — provides claude-code-sdk based career session management for the Haribo Unified Dashboard.

## What it does

- Runs claude-code-sdk sessions per Bewerbung (cwd = BW-Ordner)
- Loads Karriere-Coach Skill v5.6 as system prompt
- Streams assistant output as SSE events to the Dashboard
- Intercepts `QUESTION:` markers → sends question events → waits for user answers
- Supports pause / resume / cancel with reasons
- Writes to mail.db (applications, session_events)

## Architecture

```
Dashboard (7500) → POST /api/session/start → starts SDK session
                 → GET  /api/session/:id/stream → SSE events
                 → POST /api/session/:id/answer → feeds user choice back
```

## Setup

```bash
pip install -r requirements.txt
```

### systemd

```bash
cp systemd/karriere-agent.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now karriere-agent
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/health | Health check |
| POST | /api/session/start | Start new session |
| GET | /api/session/:id/stream | SSE event stream |
| GET | /api/session/:id | Session state |
| POST | /api/session/:id/answer | Feed user answer |
| POST | /api/session/:id/pause | Pause session |
| POST | /api/session/:id/resume | Resume session |
| POST | /api/session/:id/stop | Stop session |
| POST | /api/applications/new | Create new application |
| GET | /api/applications/:id/posting | Get job-posting.md |
| POST | /api/applications/:id/cancel | Cancel with reason |
| GET | /api/commute | Calculate commute from Krieglach |
| GET | /api/settings/providers | Provider config |
| GET | /api/pdf-worker/status | Office Server status |

## Port

**7600** — reserved for Karriere-Agent per CustomDev port rules.

## PayPal

If this project is useful to you: [PayPal](https://paypal.me/aloisschacherl)
