# Introducing CiteScope — Open-source AI Citation Analysis

*Published 2026-05-23. ~1500 words.*

---

If you've been paying attention to how customers actually find products in 2026, you've noticed something uncomfortable: **a meaningful share of buying-intent traffic has been routed away from Google and into AI chat windows.**

When someone asks ChatGPT "what are the best B2B sock factories in China for 2026?" or Perplexity "best cold-chain logistics partner for North America imports", they get a 200-word answer with three to five named vendors and clickable citations. They don't scroll through ten blue links. They pick from the AI's shortlist.

If your brand isn't on that shortlist, you're effectively invisible — even if you rank #1 on Google for the same query.

This is **GEO** — Generative Engine Optimization. Or **AEO** — Answer Engine Optimization, the term gaining traction in mid-2026. Same idea: optimize for AI search, not just Google.

The category is hot. Topify, Profound, Peec.ai, Otterly, AthenaHQ — all built in the last 18 months, all charging $80-500/month to tell brands the same thing: "here's how often ChatGPT mentions you vs. your competitors, and here are the URLs it cited."

**Today we're open-sourcing CiteScope**, an MIT-licensed self-hostable platform that does what the commercial tools do — plus one thing none of them ships.

[github.com/your-org/CiteScope](https://github.com/your-org/CiteScope) (replace with the real URL)

## What CiteScope is

CiteScope is what you'd build if you needed AI search monitoring and had two engineers and a weekend. Concretely:

- A FastAPI backend that talks to six AI search engines (ChatGPT, Perplexity, Gemini, Doubao, Kimi, DeepSeek) through their official APIs (or, where no API exists, a documented best-effort reverse path)
- A React + Antd dashboard with the four screens every GEO tool ships: overview, run history, A/B run compare, and citation source analysis
- A background worker that resolves Gemini's `vertexaisearch.cloud.google.com/grounding-api-redirect/*` links into real domains every five minutes
- Single SQLite file. One Docker container. Runs in 1 GB of RAM.
- A bundled in-app tutorial center, because docs-buried-in-a-wiki is how products die

You can spin it up in one command:

```bash
git clone https://github.com/your-org/CiteScope.git
cd CiteScope
cp backend/.env.example backend/.env  # add your API keys
docker compose up -d
```

Open `localhost:3000`, create a client, paste your probe questions, click "New Run". Five minutes later you have data.

## The one thing no other tool does

Here's where it gets interesting. Every commercial GEO tool can tell you something like:

> "Reddit was cited in 78% of AI responses in your category last week."

CiteScope can tell you that **and** something more useful:

> "Reddit was cited in 78% of AI responses. Of those citations, 23 specifically backed sentences that mentioned your brand — vs. 55 that backed unrelated competitor mentions or general industry claims."

This is **span attribution**: cross-referencing the `[citation:N]` markers in AI answers against the positions where your brand actually appears. It tells you the difference between "Reddit is generically high-cited" (true but not actionable) and "Reddit specifically vouches for your brand at a 30% rate" (actionable: invest in Reddit presence) or "Reddit cites everyone in our category except us" (actionable: gap analysis).

The algorithm isn't hard — sentence segmentation that handles English + CJK + mixed punctuation, then interval intersection between brand-keyword positions and citation marker positions. It's about 90 lines of Python (`backend/app/services/citation_analysis/span_attribution.py`). The hard part is committing to implementing it instead of shipping a vanity dashboard.

Commercial tools haven't done this because:
1. It's expensive to compute at scale and the marketing payoff is unclear
2. It exposes how shallow most "citation tracking" actually is

We did it because we needed it. Our use case is real — a B2B export business trying to understand which of their competitors are AI-visible and where the AI authority signals are coming from. Generic "reddit is hot" wasn't enough.

## Why open source

There are three honest reasons.

**One: the underlying data isn't a moat.** Every GEO tool fundamentally does the same thing — fan out probe questions to AI engines, parse responses, store in a DB, draw charts. The differentiation is workflow polish, integrations, and occasionally a clever feature (Topify's source analysis, Profound's enterprise touch). None of this is rocket science. The whole industry is selling a $20/month service for $200/month because most buyers can't be bothered to host it themselves. That gap will close.

**Two: AI search is changing too fast for closed-source tools to keep up.** OpenAI ships a new Responses API field. Google renames `googleSearchRetrieval` to `google_search`. Perplexity decides Sonar Pro returns citations differently than Sonar. A new Chinese AI engine launches with Web Search and a brand-new response shape (this happened in Q1 2026 with Doubao's Ark Web Search). Closed-source SaaS has to wait for their roadmap, ship a release, write docs, get customer support to handle the change. With CiteScope: copy an adapter, change six lines, ship in an afternoon.

**Three: we want to encourage the long tail of GEO researchers.** Academics studying AI bias, agencies serving niche industries, brands with weird requirements ("monitor 50 industry-specific Telegram channels and also AI search"). None of these fit a $99-499/month SaaS pricing model. Open source unlocks them.

## What's in v0.1 (today)

- **Six AI engines** with normalized citation output: ChatGPT (Responses + web search), Perplexity (Sonar / OpenRouter), Gemini (`google_search` tool + grounding redirect resolution), Doubao (Volcengine Ark `web_search` builtin), Kimi (Moonshot API), DeepSeek (reverse via `chat.deepseek.com`)
- **Citation source analysis**: Top Domains report + Competitor Assets report
- **Span attribution**: per-citation `supports_brand_mention` flag
- **Run experimentation**: matrix + radar comparison across runs to validate GEO interventions
- **Website GEO audit**: single-URL diagnostic (robots.txt, llms.txt, schema.org, AI-bot crawlability)
- **In-app tutorial center**: 8 modular guides
- **Anti-ban defaults**: random delays, daily quotas, hard caps

## What's not in v0.1 (yet)

- Per-region monitoring (OpenAI `user_location`, Perplexity ccTLD pinning)
- Alerting (Slack / webhook on mention-rate regression)
- Multi-tenant API key isolation
- Postgres backend (SQLite only for now)
- Frontend code splitting (current bundle is ~2.6 MB)
- Public read-only report URLs (shareable per-client)

Roadmap is in the README. PRs welcome.

## Setup, in one paragraph

You need API keys for OpenAI (the `OPENAI_OFFICIAL_API_KEY` that ChatGPT web search needs), Perplexity (direct or OpenRouter), and Google AI Studio. Optional: Volcengine Ark for Doubao, Moonshot for Kimi. Drop them in `backend/.env`, run `docker compose up -d`, open `localhost:3000`. The Settings UI explains every field in detail with signup links. The in-app tutorial center (`/guides`) walks you through your first Run.

Expected first-week API spend for a typical 100-prompt × 3-platform × weekly cadence: ~$5-15. Same data Topify gives you for $99/month.

## What we'd love to hear

- **Bug reports** of any kind — adapter shape mismatches when a vendor changes their response format, weird Unicode in the span attribution, ops issues
- **Adapter contributions** for AI engines we don't cover yet — Bing Copilot, Claude.ai, You.com, Brave Search are all on the wishlist
- **Use case stories** — what would you do with this data that the commercial tools don't let you do? Tell us, we'll prioritize features that unlock those workflows

## Final thought

GEO is going to be table-stakes by 2027. Every brand that cares about discoverability will be measuring it. The question is whether they measure it through a Topify dashboard at $99/month, or through their own SQLite file at $0/month with the option to extend.

We're betting on the second world. If you agree, [give us a star](https://github.com/your-org/CiteScope), try a Run, and tell us what's missing.

---

**Get CiteScope**: [github.com/your-org/CiteScope](https://github.com/your-org/CiteScope)
**License**: MIT
**Built with**: FastAPI, React + Antd, react-markdown, tldextract, httpx, APScheduler
**Comparison vs. commercial tools**: [docs/COMPARISON.md](./COMPARISON.md)
