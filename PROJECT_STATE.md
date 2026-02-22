# NormProject Weather - Project State

**Last Updated:** 2026-02-22

---

## System Status

| Component | Status | Notes |
|-----------|--------|-------|
| Core functionality | Complete | NWS forecast + geocoding + Claude Q&A |
| Tests | Complete | 53 tests, >96% coverage on core modules |
| Documentation | Complete | Docstrings on all public APIs |
| Cloud Deployment | Ready | All config via env vars, container-ready |

---

## Current Production State

- **Version:** 1.0.0
- **Environment:** Local development
- **Run:** `streamlit run src/app.py`

---

## Architecture

```
src/
├── app.py          # Streamlit UI (visual dashboard + chat)
├── config.py       # Env-var configuration
├── geocoding.py    # Location → lat/lon (Nominatim)
├── nws_client.py   # NWS API → forecast data (standard + hourly)
└── chat.py         # Claude-powered weather Q&A
```

---

## Critical Files

| File | Purpose | Do Not Break |
|------|---------|--------------|
| CLAUDE.md | Session reference | Yes |
| .claude/settings.json | Configuration & hooks | Yes |
| src/config.py | All env-var configuration | Yes |
| src/nws_client.py | NWS API integration | Yes |
| src/geocoding.py | Location resolution | Yes |
| src/chat.py | Conversational Q&A | Yes |

---

## Recent Changes

- 2026-02-22: Built full weather forecast app with visual dashboard, hourly/daily forecasts, dynamic backgrounds, and Claude-powered Q&A
- 2026-02-20: Project initialized with Claude Code setup v4.0

---

## Known Issues

None yet.

---

## Next Milestone

Deploy to cloud environment (AWS/GCP/Azure).
