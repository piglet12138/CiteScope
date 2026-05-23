# CiteScope

> **Open-source AI Citation Analysis & GEO Monitoring Platform**
> See where AI engines cite your brand — and where they cite your competitors.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![CI](https://github.com/<your-org>/CiteScope/actions/workflows/ci.yml/badge.svg)](https://github.com/<your-org>/CiteScope/actions/workflows/ci.yml)
![Made with FastAPI](https://img.shields.io/badge/backend-FastAPI-009688.svg)
![Frontend](https://img.shields.io/badge/frontend-React_18_+_Antd_5-1677ff.svg)

[简体中文 →](./README.zh.md)

---

## What is CiteScope

CiteScope is a self-hosted platform for **GEO (Generative Engine Optimization)** — measuring and improving how AI search engines mention your brand. It runs your probe questions through ChatGPT / Perplexity / Gemini / Doubao / Kimi / DeepSeek, captures the answers and the URLs the AI cited, and tells you:

1. **Are you being mentioned?** Per-engine and per-experiment mention rate.
2. **Where does the AI cite?** Top domains across your category — the playbook for content placement.
3. **What's your competitor's GEO footprint?** Reverse-attribution: when AI mentions competitor X, which URLs back that mention.

It's the OSS alternative to commercial tools like Topify, Profound, Peec.ai — with one feature none of them ship: **citation-to-brand-mention span attribution**. CiteScope tells you not just that `made-in-china.com` was cited 39 times, but that 7 of those 39 specifically backed sentences mentioning your brand.

## Screenshots

> _(replace with real screenshots after first deploy)_

| Citation Sources tab | Top domains report | Competitor assets |
|---|---|---|
| `monitoring center > 引用来源` | `made-in-china.com × 39 (3 platforms)` | `Biorun → biorunsocks.com × 12` |

## Features

- **Multi-engine monitoring** — single SQL schema across ChatGPT (OpenAI Responses + web search), Perplexity (Sonar / OpenRouter), Google AI (Gemini grounding), Doubao (Volcengine Ark), Kimi (Moonshot), DeepSeek (best-effort reverse)
- **Citation source analysis** — normalized `monitor_citations` table; aggregate `Top Domains` + `Competitor Assets` reports
- **URL redirect resolution** — async httpx batch resolver chews Gemini `vertexaisearch.cloud.google.com/grounding-api-redirect/*` into real domains in the background
- **Span attribution** — `[citation:N]` markers ∩ brand-mention sentences → `supports_brand_mention` per citation. Sentence boundary handles EN, CJK, and mixed punctuation
- **Experiment runs** — every monitoring round is a versioned Run. Matrix + radar compare across Runs to validate GEO interventions (`llms.txt`, schema markup, FAQ blocks, etc.)
- **Website GEO diagnosis** — single-URL audit: robots.txt, llms.txt, schema.org, AI-bot crawlability, FAQ presence, content quality. Outputs a 0-100 score + actionable fix list
- **In-app tutorial center** — 8 module guides bundled via `react-markdown`, browsable at `/guides`
- **Anti-ban defaults** — random 8-20s gaps between queries, daily per-platform quota cap (default 30), hard cap of 20 probes per Run

## Quick start

### Docker Compose (1 minute)

```bash
git clone https://github.com/<your-org>/CiteScope.git
cd CiteScope
cp backend/.env.example backend/.env
# Open backend/.env and fill at least:
#   OPENAI_OFFICIAL_API_KEY=sk-...
#   PERPLEXITY_API_KEY=...
#   GOOGLE_AI_API_KEY=...
docker compose up -d
# Open http://localhost:3000
```

You're done. Create a client, paste your probe questions, click **新建实验运行 / New Run**.

### Manual install

See [docs/INSTALL.md](./docs/INSTALL.md) (or the [Operations guide](./frontend/src/docs/guides/operations.md) bundled with the app).

## Architecture (30-second tour)

```
┌─────────────┐    HTTP/REST     ┌──────────────────┐
│ React + Vite│ <──────────────> │ FastAPI + uvicorn │
│  + Antd 5   │                  │  + SQLAlchemy     │
└─────────────┘                  │  + APScheduler    │
                                 └────────┬──────────┘
                                          │
                       ┌──────────────────┼──────────────────┐
                       ▼                  ▼                  ▼
                ┌────────────┐     ┌─────────────┐    ┌──────────────┐
                │ AI engines │     │   SQLite    │    │  Background  │
                │ adapters   │     │  (WAL mode) │    │ citation     │
                │ (6 of them)│     │             │    │ resolver job │
                └────────────┘     └─────────────┘    └──────────────┘
```

One process, one DB file, no Redis / Celery / Postgres needed for getting started. Runs in 1 vCPU / 1 GB.

Deep dive: [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md).

## Comparison to commercial tools

| | CiteScope | Topify | Profound | Peec.ai |
|---|---|---|---|---|
| **Price** | Free (self-host) | $99-199/mo | $499+/mo enterprise | €80-120/mo + addons |
| **AI engines** | 6 (incl. Doubao/Kimi/DeepSeek) | 7+ | 10+ (no Doubao) | 5 (DS as €80 add-on) |
| **Citation domain aggregation** | ✅ Top Domains report | ✅ Source Analysis | ✅ Citations | ✅ |
| **Competitor reverse attribution** | ✅ Competitor Assets | ✅ Competitor Mon. | ✅ | partial |
| **Brand-mention span attribution** | ✅ unique | ❌ | ❌ | ❌ |
| **Self-host** | ✅ Docker compose | ❌ SaaS only | ❌ SaaS only | ❌ SaaS only |
| **Prompt limit** | unlimited | 100 (Basic) / 250 (Pro) | per quote | per tier |
| **Source code** | MIT, all of it | proprietary | proprietary | proprietary |

Full breakdown: [docs/COMPARISON.md](./docs/COMPARISON.md).

## Roadmap

- [ ] Postgres backend (currently SQLite only)
- [ ] More AI adapters: Bing Copilot, Claude.ai, You.com, Brave Search
- [ ] Per-region monitoring (`user_location` for OpenAI, ccTLD pinning for Perplexity)
- [ ] Built-in alerting (Slack/Webhook) on mention-rate regression
- [ ] Multi-tenant (per-client API key isolation)
- [ ] Read-only public reports (shareable URLs per client)

Want one of these? Open an issue or PR.

## Documentation

- [Getting Started](./frontend/src/docs/guides/getting-started.md) — 5-step tour
- [API Configuration](./frontend/src/docs/guides/settings.md) — keys + endpoint details
- [Citation Sources](./frontend/src/docs/guides/citation-sources.md) — the core feature
- [Architecture](./docs/ARCHITECTURE.md) — internals deep-dive
- [Comparison](./docs/COMPARISON.md) — vs commercial tools
- [Contributing](./CONTRIBUTING.md) — PR flow + open issues

## Status

Currently used in production by a B2B export business for GEO monitoring across English-speaking AI search engines. Public OSS release: **2026-05-23**.

## License

[MIT](./LICENSE) — go wild.

## Acknowledgments

CiteScope draws inspiration from commercial GEO platforms (Topify, Profound, Peec.ai) and the OSS community building around AI-search optimization. Built on top of FastAPI, Antd, react-markdown, tldextract, httpx, APScheduler.
