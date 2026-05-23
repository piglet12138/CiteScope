# CiteScope Architecture

## Overview

CiteScope is intentionally small. One Python process, one SQLite file, one React bundle. The complexity is in the **AI adapters** (one per engine) and the **citation pipeline** (normalizer → resolver → span attribution).

## Directory map

```
backend/app/
├── main.py                        # FastAPI app factory + startup hooks
├── config.py                      # Pydantic-settings, .env reader
├── db.py                          # SQLAlchemy engine + WAL + in-place migrations
├── models.py                      # ORM models
├── schemas.py                     # Response envelope
├── deps.py                        # Dependencies (get_db)
├── routers/
│   ├── clients.py                 # CRUD for monitor targets
│   ├── questions.py               # Probe question library
│   ├── monitor.py                 # M4: Runs + per-result endpoints
│   ├── citation_reports.py        # /citation-reports/top-domains, /competitor-assets
│   ├── diagnosis.py               # M7: single-URL GEO audit
│   ├── settings.py                # Runtime config CRUD + schema endpoint
│   ├── tasks.py                   # Async task polling
│   ├── usage.py                   # LLM cost rollups
│   └── docs.py                    # File upload library
├── modules/
│   ├── m4_monitor/service.py      # Run orchestration + quota
│   ├── m5_clients/                # Client management helpers
│   └── m7_diagnosis/              # Website audit pipeline
├── services/
│   ├── ai_monitors/               # ★ One adapter per AI engine
│   │   ├── base.py                # ABC: query() → {raw_answer, search_results, …}
│   │   ├── chatgpt.py             # OpenAI Chat Completions + gpt-4o-mini-search-preview
│   │   ├── perplexity.py          # Sonar via api.perplexity.ai OR OpenRouter
│   │   ├── google_ai.py           # Gemini 2.5 + google_search tool, parses groundingMetadata
│   │   ├── doubao.py              # Volcengine Ark Responses API + web_search builtin tool
│   │   ├── kimi.py                # Moonshot official API
│   │   ├── deepseek.py            # chat.deepseek.com refresh_token + WASM POW (best-effort)
│   │   └── factory.py             # Dynamic dispatch by platform string
│   ├── citation_analysis/         # ★ The differentiated layer
│   │   ├── normalizer.py          # tldextract domain extraction + redirect/internal URL detection
│   │   ├── resolver.py            # Async httpx batch redirect resolver
│   │   ├── span_attribution.py    # [citation:N] markers ∩ brand-mention sentences
│   │   └── pipeline.py            # ingest_citations_from_result + resolve_pending_citations
│   ├── llm_metering.py            # Per-call cost/token recording
│   ├── search_pricing.py          # Cost estimation per platform
│   ├── playwright_client.py       # Sync wrapper around the adapter dispatch
│   ├── runtime_config.py          # ALLOWED_KEYS + SECRET_KEYS + JSON overlay
│   └── scheduler.py               # APScheduler singleton
└── tasks/jobs.py                  # Run/resolve jobs registered with scheduler

frontend/src/
├── App.tsx                        # Routes + sidebar layout
├── api/                           # Typed REST SDK (axios-based)
├── pages/
│   ├── Overview.tsx               # Cross-client dashboard
│   ├── ClientDetail.tsx           # One-client deep view
│   ├── MonitorCenter.tsx          # 4 tabs: overview / runs / compare / citations
│   ├── UsageCenter.tsx            # LLM cost
│   ├── Settings.tsx               # API key management UI
│   ├── GuidesHub.tsx              # /guides hub
│   └── GuidePage.tsx              # /guides/:slug dynamic page
├── components/
│   ├── CitationSourcesPanel.tsx   # Top Domains + Competitor Assets UI
│   ├── MarkdownPage.tsx           # Shared Antd-styled MD renderer
│   └── ClientForm.tsx
└── docs/guides/                   # Bundled .md tutorials (Vite ?raw imports)
```

## Data flow: a single Run

```
User clicks "新建实验运行"
  ↓ POST /api/clients/{id}/runs
  ↓ creates MonitorRun row (status=running) + task_id
  ↓ APScheduler enqueues run_monitor()

For each (question, platform) in selected:
  ├── Check daily quota (SELECT COUNT FROM monitor_results WHERE platform=…)
  │     ↓ if exceeded, skip platform for the rest of this Run
  ├── adapter.query(question, brand_keywords)
  │     ↓ HTTP call to AI engine
  │     ↓ parse engine-specific response into:
  │       { raw_answer, search_results: [{cite_index, url, title, snippet}], usage }
  ├── INSERT INTO monitor_results (raw_answer, search_results JSON, …)
  ├── pipeline.ingest_citations_from_result(db, mr, brand_keywords)
  │     ↓ for each citation:
  │       - is_redirect_wrapper(url) → status=pending (worker resolves later)
  │       - is_platform_internal(url) → status=skipped (google.com/maps placeholders)
  │       - else → extract_domain() → status=ok
  │     ↓ span_attribution.compute_supports_brand_mention():
  │       [citation:N] markers ∩ brand-mention sentences → supports map
  │     ↓ INSERT into monitor_citations
  ├── llm_metering.record_call(provider, model, tokens, cost, latency)
  └── sleep 8-20s (anti-ban)

Run finishes → UPDATE monitor_runs SET status=completed
```

## Background: citation resolver

`tasks/jobs.py:resolve_citations_job` runs every 5 minutes (APScheduler interval trigger). Pulls up to 50 `monitor_citations WHERE resolve_status='pending'`, feeds raw URLs to async resolver, writes back `resolved_url + domain + status='ok'` (or `failed`).

Mostly chews Gemini's `vertexaisearch.cloud.google.com/grounding-api-redirect/*` links. Other engines return resolvable URLs at ingest time.

## Adding a new AI adapter

1. New file `services/ai_monitors/<engine>.py` extending `BaseMonitor`:
   ```python
   class FooMonitor(BaseMonitor):
       platform_id = "foo"

       def query(self, question, *, brand_keywords=None) -> dict[str, Any]:
           # call the engine API
           # parse response into: {raw_answer, search_results: [...], usage}
           ...
   ```
2. Register in `factory.py:_REGISTRY`
3. Add API-key field(s) to `config.py` Settings + `runtime_config.py:ALLOWED_KEYS`
4. Add `FIELD_SCHEMA` entry in `routers/settings.py` with `category=monitor` + your `platform` slug
5. (Optional) extend `test/monitor/{platform}` for key validation

The hardest part of adapter writing is **citation parsing**. Different engines return citations in wildly different shapes:

| Engine | Where citations live |
|---|---|
| OpenAI ChatGPT | `choices[0].message.annotations[]` with `type=url_citation` |
| Perplexity Sonar | `citations[]` at top level, URLs only |
| Google Gemini | `candidates[0].groundingMetadata.groundingChunks[]` |
| Volcengine Ark (Doubao) | `output[].content[].annotations[]` with `type=url_citation` |

CiteScope's job is to normalize all of these into:
```python
[{"cite_index": N, "title": str, "url": str, "snippet": str}]
```
…and inject `[citation:N]` markers into the answer text so span attribution can run.

## DB schema

```sql
clients (id, name, industry, region, business_info JSON, language, …)
questions (id, client_id, text, category, priority, is_active, …)
monitor_runs (id, client_id, name, note, platforms, status, …)
monitor_results (id, client_id, question_id, run_id, platform,
                 is_mentioned, position, has_link, sentiment,
                 raw_answer, search_results JSON, …)
monitor_citations (id, monitor_result_id, client_id, platform,
                   cite_index, raw_url, resolved_url, domain,
                   title, snippet, supports_brand_mention,
                   resolve_status, …)
llm_call_logs (id, created_at, client_id, purpose, provider, model,
               prompt_tokens, completion_tokens, total_tokens,
               usd_cost, latency_ms, status, error)
diagnosis_results (id, base_url, page_url, client_id, overall_score,
                   scores_json, checks_json, actions_json, …)
reports (id, client_id, period_start, period_end, summary, metrics_snapshot, …)
```

WAL mode is enabled (`PRAGMA journal_mode=WAL`) so reads don't block writes.

## Why not Postgres / ClickHouse from day one?

Most CiteScope deployments will hold < 100k citations. SQLite handles that comfortably in single digit milliseconds per query. Swapping to Postgres is a `db_url` change away when scale demands; ClickHouse-tier aggregation (oneglanse-style) is on the roadmap for the day someone is doing 10M citations.

## Frontend boundaries

- All state is server-driven; no client-side caching beyond per-page React state
- Antd `Tabs` + `Card` are the primary layout primitives — keeps the design opinionated and consistent
- `react-markdown + remark-gfm` renders the bundled guides; ~50 KB
- Total bundle ~2.6 MB minified (~850 KB gzip) — fine for an internal tool, could be code-split later

## Anti-abuse defaults

The platform talks to AI engines that don't take kindly to rapid-fire identical-IP queries. Defaults (in `m4_monitor/service.py`):

- 8-20 second random jitter between queries
- 30 queries per platform per day, hard cap
- 5 questions default per Run (20 hard cap)

These are *defaults* — tune if you know what you're doing, or get permission to crank up.
