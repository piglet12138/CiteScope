# Operations / Deployment

> Self-hosting CiteScope. Reference for ops folks; not needed for casual users.

## Stack

- **Backend**: FastAPI + uvicorn + SQLAlchemy + APScheduler (~25 MB resident)
- **Frontend**: Vite + React + Antd → static `dist/` served by any nginx/Caddy
- **Database**: SQLite (WAL mode) by default; swap to Postgres by changing `db_url`
- **Background worker**: APScheduler in-process; no external broker needed

Footprint: comfortably runs on a 1 vCPU / 1 GB VM. Single binary deployment.

## Quick start with Docker Compose

```bash
git clone https://github.com/piglet12138/CiteScope.git
cd CiteScope
cp backend/.env.example backend/.env
# Fill in at least OPENAI_OFFICIAL_API_KEY + PERPLEXITY_API_KEY + GOOGLE_AI_API_KEY
docker compose up -d
# Open http://localhost:3000
```

## Manual install (no Docker)

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env  # edit and fill API keys
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run build   # outputs dist/
# Serve dist/ with nginx, Caddy, or `npm run preview` for dev
```

## Systemd unit (recommended for prod)

```ini
# /etc/systemd/system/citescope.service
[Unit]
Description=CiteScope backend
After=network-online.target

[Service]
Type=simple
User=citescope
WorkingDirectory=/opt/citescope/backend
ExecStart=/opt/citescope/backend/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5
StandardOutput=append:/var/log/citescope/backend.log
StandardError=append:/var/log/citescope/backend.log

[Install]
WantedBy=multi-user.target
```

Then `sudo systemctl daemon-reload && sudo systemctl enable --now citescope.service`.

## Logs

```bash
sudo tail -f /var/log/citescope/backend.log
grep "citation resolver" /var/log/citescope/backend.log | tail
grep -E "ERROR|exception" /var/log/citescope/backend.log | tail -20
```

## Updating

```bash
cd /opt/citescope
git pull
cd backend && .venv/bin/pip install -e .
cd ../frontend && npm install && npm run build
sudo systemctl restart citescope.service
```

If your host has no Node, build the frontend on your laptop and `scp dist/` to the server.

## SQLite backup

```bash
cp /opt/citescope/backend/data/geo.db{,.bak.$(date +%F-%H%M)}
```

For continuous backup, use the SQLite `.backup` command or [litestream](https://litestream.io/) → S3.

## Tables (after the 2026-05 refactor)

| Table | Purpose |
|---|---|
| `clients` | Brands being monitored |
| `questions` | Probe prompts |
| `monitor_runs` | One Run = one experiment cohort |
| `monitor_results` | Per (question, platform) AI response |
| `monitor_citations` | Normalized citations (powers Top Domains + Competitor Assets reports) |
| `llm_call_logs` | Per-call cost/latency metering |
| `diagnosis_results` | Website GEO audit snapshots |
| `reports` | Monthly aggregated report snapshots |

## Background worker (citation resolver)

`backend/app/tasks/jobs.py:resolve_citations_job` polls `monitor_citations.resolve_status='pending'` every 5 minutes and resolves Gemini grounding redirects to real domains.

```bash
grep "resolve_citations_job\|citation.resolve" /var/log/citescope/backend.log | tail -10
```

## Historical citation backfill

If you have existing `MonitorResult` rows from before citation analysis went live:

```bash
cd /opt/citescope/backend && \
  .venv/bin/python -m scripts.backfill_citations [--limit N] [--client-id ID] [--since YYYY-MM-DD]
```

Idempotent — safe to re-run.

## LLM cost monitoring

`/usage` page aggregates `llm_call_logs` by provider / model / purpose. Watch the OpenAI Responses + web_search line items — they add up.

Per-call cost is estimated by `services/search_pricing.py`; tune the rate table there if your pricing differs.

## Common ops scenarios

**Q: UI returns 500 / network error?**
A: `systemctl status citescope.service`. Inactive → restart. Active → check log.

**Q: Run fails with 401?**
A: `/api/settings/runtime` shows `configured=false` for the relevant key — fill it via Settings UI.

**Q: Disk filling up?**
A: Mostly `backend.log` (no rotation by default) + SQLite `.bak.*` files. Truncate or set up logrotate.

## Related

- See module-specific guides for feature deep dives.
- Code is at the repo root: `backend/app/` + `frontend/src/`.
