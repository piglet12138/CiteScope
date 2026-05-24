# Contributing to CiteScope

Thanks for your interest. CiteScope is small enough that PRs from outside contributors are very welcome — there's plenty of low-hanging fruit.

## Quick orientation

```
backend/app/
  routers/             # FastAPI routes (REST)
  modules/             # Domain modules (M4 monitor, M7 diagnosis, M5 clients)
  services/
    ai_monitors/       # One adapter per AI search engine
    citation_analysis/ # Normalizer, resolver, span attribution, pipeline
  models.py            # SQLAlchemy
  config.py            # Pydantic-settings, .env reader

frontend/src/
  pages/               # One per route
  components/          # Shared (CitationSourcesPanel, MarkdownPage, …)
  docs/guides/         # Bundled in-app docs (markdown)
  api/                 # Typed REST SDK
```

## Setup

See [Quick start](./README.md#quick-start). For dev:

```bash
# Backend (hot reload)
cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000

# Frontend (Vite dev)
cd frontend && npm run dev
```

## What we'd love help with

Looking at the [issues](https://github.com/piglet12138/CiteScope/issues), but in particular:

- **More AI adapters**: Bing Copilot, Claude.ai, You.com, Brave Search… anything with a citation-returning API. Adapter template: `services/ai_monitors/chatgpt.py` is the cleanest reference.
- **i18n**: UI is currently zh-CN heavy with English mixed in. Patches for proper i18next or react-intl welcome.
- **Postgres backend**: SQLite is convenient but Postgres opens up multi-instance + ClickHouse-style scale. Currently `db.py` is single-file; would benefit from a config switch.
- **Frontend code-splitting**: Bundle is currently ~2.6 MB. `manualChunks` to split antd / echarts / react-markdown would help cold load.
- **Tests**: minimal coverage. Pytest fixtures + a couple of integration tests on the citation pipeline would be a big win.

## Coding conventions

- **Python**: 3.10+, ruff lint, type hints in new code
- **TypeScript**: `strict` mode on, prefer typed API SDK over raw `http.get`
- **Comments**: explain *why*, not *what*. The code already shows what.
- **Migration**: prefer `ALTER TABLE ADD COLUMN` via `db.py:_apply_inplace_migrations` over Alembic until SQLite isn't enough

## PR flow

1. Fork + branch from `main`
2. One commit per logical unit, conventional commit prefix (`feat:`, `fix:`, `docs:`, …)
3. PR description: what + why, one screenshot if UI-facing
4. CI runs syntax check + smoke. Maintainer reviews within ~48h on a good week.

## Code of conduct

Be kind, be specific, attack ideas not people. We don't have a long CoC doc; treat each other like coworkers you respect.

## License

By contributing you agree your code is released under [MIT](./LICENSE).
