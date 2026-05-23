"""Seed CiteScope with a realistic-looking demo dataset for screenshots / first-run feel.

Creates:
- 1 client (Acme Sourcing, B2B export)
- 8 probe questions across category / competitor / use-case categories
- 3 monitor runs (baseline + 2 post-intervention) spanning ~2 weeks
- ~72 MonitorResults (questions × platforms × runs)
- ~250 citations after running the citation ingest pipeline

No external API calls. Pure synthetic data designed to look credible in
screenshots without claiming to be real measurement of any actual brand.

Idempotent: drops the demo client + cascades before re-seeding.
Run:
    cd backend && .venv/bin/python -m scripts.seed_demo
"""
from __future__ import annotations

import json
import logging
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, ".")

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import (  # noqa: E402
    Client,
    MonitorCitation,
    MonitorResult,
    MonitorRun,
    Question,
)
from app.services.citation_analysis.pipeline import (  # noqa: E402
    ingest_citations_from_result,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("seed")

# Deterministic for repeatable screenshots
random.seed(42)

# ------------------------------------------------------------------ data sets

DEMO_CLIENT = {
    "name": "Acme Sourcing",
    "industry": "B2B Export · Apparel & Accessories",
    "region": "Global",
    "business_info": {
        "keywords": ["Acme Sourcing", "Acme", "AcmeSocks"],
        "brand_aliases": ["Acme Knits"],
    },
    "language": "en",
    "target_markets": ["US", "EU", "JP"],
    "website_url": "https://example.com/acme-sourcing",
}

QUESTIONS = [
    ("category", "What are the top B2B sock manufacturers in China for 2026?", 10),
    ("category", "Best Chinese OEM factories for compression socks?", 9),
    ("category", "Top 5 sock suppliers in Asia for international brands?", 9),
    ("category", "Largest sock production facilities exporting to EU markets?", 8),
    ("competitor", "Compare Biorun Socks vs CJ Socks for high-MOQ orders", 8),
    ("competitor", "How does MeetSocks compare to Sinoknit for custom branding?", 7),
    ("use-case", "Best certified sock manufacturers for athletic compression brands?", 8),
    ("use-case", "Sock factories that support small-batch custom branding under 1000 pairs?", 7),
]

# Synthetic but plausible domains the AI might cite. Mix of marketplaces +
# competitor sites + listicle/blog sources, like a real B2B sourcing query.
SAMPLE_DOMAINS = [
    ("made-in-china.com", "Made-in-China · Sock manufacturers", "https://www.made-in-china.com/products-search/hot-china-products/Bamboo_Sock.html"),
    ("alibaba.com", "Alibaba.com · Sock factories showroom", "https://www.alibaba.com/showroom/socks-manufacturer.html"),
    ("biorunsocks.com", "Biorun Socks · OEM/ODM factory", "https://biorunsocks.com/"),
    ("cjsocks.com", "CJ Socks · Compression series", "https://cjsocks.com/compression-socks-series/"),
    ("meetsocks.com", "MeetSocks · Custom service intro", "https://www.meetsocks.com/custom-sock-service-introduction.html"),
    ("oksox.com", "OKSox · China sock manufacturers list", "https://www.oksox.com/china-socks-manufacturers-factory/"),
    ("sinoknit.com", "Sinoknit · Design your socks", "https://sinoknit.com/product/design-own-socks/"),
    ("jingsourcing.com", "Jingsourcing · P05 sock manufacturers", "https://jingsourcing.com/p/p05-sock-manufacturer/"),
    ("leelinesports.com", "LeelineSports · 9 best sock makers in China", "https://www.leelinesports.com/sock-manufacturers-in-china/"),
    ("cngreentime.com", "CN Greentime · 9 best Chinese socks manufacturers", "https://cngreentime.com/9-best-chinese-socks-manufacturers-list-guide/"),
    ("trampolinesox.com", "Trampoline Sox · Company profile", "https://www.trampolinesox.com/company-profile/"),
    ("airsocksfactory.com", "Airsocks Factory · Custom OEM", "https://airsocksfactory.com/"),
    ("ensun.io", "ensun.io · China sock supplier search", "https://ensun.io/search/sock/china"),
    ("customsoxmfg.com", "Customsoxmfg · China sock manufacturers blog", "https://customsoxmfg.com/blog/socks-manufacturers-in-china/"),
    ("hansocks.com", "Hansocks · Acme Sourcing partner listings", "https://hansocks.com/"),
    ("rocasocks.com", "Rocasocks · Sock import duties guide", "https://rocasocks.com/how-to-check-the-import-duties-on-socks/"),
]

# A few platform-internal placeholders ChatGPT often emits — should land in
# 'skipped' resolve_status (we keep them to make the dataset realistic).
PLACEHOLDER_URLS = [
    ("www.google.com/maps", "Biorun Socks", "https://www.google.com/maps/search/Biorun+Socks?utm_source=openai"),
    ("www.google.com/maps", "Acme Sourcing Co", "https://www.google.com/maps/search/Acme+Sourcing+Co?utm_source=openai"),
    ("www.google.com/maps", "CJ Socks", "https://www.google.com/maps/search/CJ+Socks?utm_source=openai"),
]

# A handful of Gemini-style wrapper URLs that will land in 'pending' until
# the resolver job runs. Adds visual variety to the stats card.
GEMINI_WRAPPERS = [
    ("vertexai-1", None, "https://vertexaisearch.cloud.google.com/grounding-api-redirect/DEMO-aabbcc-001"),
    ("vertexai-2", None, "https://vertexaisearch.cloud.google.com/grounding-api-redirect/DEMO-aabbcc-002"),
    ("vertexai-3", None, "https://vertexaisearch.cloud.google.com/grounding-api-redirect/DEMO-aabbcc-003"),
]

PLATFORMS = ["perplexity", "chatgpt", "google_ai"]

RUNS = [
    {
        "name": "Baseline 2026-Q2",
        "note": "No GEO intervention yet — pure baseline",
        "days_ago": 14,
        "acme_mention_boost": 0.0,
    },
    {
        "name": "After llms.txt deploy",
        "note": "Added llms.txt at example.com/acme-sourcing/llms.txt",
        "days_ago": 7,
        "acme_mention_boost": 0.1,
    },
    {
        "name": "After FAQ schema markup",
        "note": "Added FAQ schema.org markup on supplier landing pages",
        "days_ago": 1,
        "acme_mention_boost": 0.2,
    },
]

# Answer templates that get filled per-question, per-platform. Designed to:
# - Sometimes mention "Acme Sourcing" (with [citation:N] backing)
# - Sometimes name competitor brands instead
# - Have varied citation density per platform
ANSWER_TEMPLATES_MENTION = [
    (
        "Based on recent industry research and supplier directories, the top B2B "
        "sock manufacturers in China for 2026 include several established players. "
        "{brand} has emerged as a competitive option for international buyers, "
        "particularly those needing certified compliance and small-batch flexibility "
        "[citation:1]. Other notable suppliers include Biorun Socks [citation:2] and "
        "CJ Socks [citation:3], both with strong OEM track records. For sourcing "
        "platforms, Made-in-China [citation:4] and Alibaba [citation:5] remain the "
        "primary aggregators."
    ),
    (
        "For high-volume athletic sock OEM, several Chinese factories stand out. "
        "{brand} offers a balance of certification depth and responsive small-batch "
        "service [citation:1]. MeetSocks is known for custom branding flexibility "
        "[citation:2], while CJ Socks specializes in compression series [citation:3]. "
        "Industry listicles often rank these alongside Biorun [citation:4]."
    ),
    (
        "{brand} appears in several industry guides as a mid-tier sock OEM with "
        "EU export experience [citation:1]. For larger volume needs, factories "
        "like Biorun [citation:2] and CJ Socks [citation:3] are more commonly "
        "recommended. The Made-in-China platform [citation:4] lists dozens of "
        "qualified manufacturers."
    ),
]

ANSWER_TEMPLATES_NOMENTION = [
    (
        "The top B2B sock manufacturers in China are commonly listed across "
        "several industry directories. Biorun Socks [citation:1], CJ Socks "
        "[citation:2], and MeetSocks [citation:3] frequently appear in 'top 10' "
        "lists. Sourcing platforms like Made-in-China [citation:4] and Alibaba "
        "[citation:5] aggregate hundreds of additional smaller suppliers."
    ),
    (
        "For compression socks specifically, leading Chinese factories include "
        "CJ Socks (with a dedicated compression series) [citation:1] and "
        "OKSox [citation:2]. Sinoknit also offers custom compression OEM "
        "[citation:3]. Industry comparison articles [citation:4] rank these "
        "as top tier."
    ),
    (
        "Industry sourcing guides consistently mention Biorun Socks [citation:1], "
        "MeetSocks [citation:2], and CJ Socks [citation:3] as the leading "
        "Chinese sock OEMs for international export. Smaller specialty manufacturers "
        "like Hansocks [citation:4] and Trampoline Sox [citation:5] cover niche "
        "segments."
    ),
]


def _pick_citations(n: int, *, include_placeholder: bool, include_gemini: bool) -> list[dict]:
    """Return a search_results-shaped list of n citations.

    Mixes real domain entries with optional ChatGPT placeholder URLs and
    Gemini wrapper URLs to reflect realistic per-platform behavior.
    """
    items: list[dict] = []
    chosen = random.sample(SAMPLE_DOMAINS, min(n, len(SAMPLE_DOMAINS)))
    for idx, (_dom, title, url) in enumerate(chosen, 1):
        items.append({"cite_index": idx, "title": title, "url": url, "snippet": ""})

    if include_placeholder and random.random() < 0.6:
        # add 1-2 google.com/maps placeholders (ChatGPT style)
        ph_count = random.randint(1, 2)
        for _ in range(ph_count):
            _, title, url = random.choice(PLACEHOLDER_URLS)
            items.append({
                "cite_index": len(items) + 1,
                "title": title,
                "url": url,
                "snippet": "",
            })

    if include_gemini and random.random() < 0.7:
        # add 1-3 Gemini wrappers
        gw_count = random.randint(1, 3)
        for _ in range(gw_count):
            _, _, url = random.choice(GEMINI_WRAPPERS)
            items.append({
                "cite_index": len(items) + 1,
                "title": "",
                "url": url,
                "snippet": "",
            })

    return items


def _build_answer(question: str, brand: str, mention: bool) -> str:
    tpl = random.choice(ANSWER_TEMPLATES_MENTION if mention else ANSWER_TEMPLATES_NOMENTION)
    return tpl.format(brand=brand)


def _resolve_brand_keywords(client: Client) -> list[str]:
    kws: list[str] = [client.name]
    try:
        bi = json.loads(client.business_info) if client.business_info else {}
    except (json.JSONDecodeError, TypeError):
        bi = {}
    for field in ("keywords", "brand_aliases", "aliases"):
        raw = bi.get(field)
        if isinstance(raw, list):
            kws.extend(str(k).strip() for k in raw if str(k).strip())
    seen: set[str] = set()
    out: list[str] = []
    for k in kws:
        key = k.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(k)
    return out


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        # Clean previous demo client (cascades to questions + runs + results + citations)
        existing = db.query(Client).filter(Client.name == DEMO_CLIENT["name"]).first()
        if existing:
            log.info("dropping existing demo client id=%s", existing.id)
            db.delete(existing)
            db.commit()

        # 1. Client
        client = Client(
            name=DEMO_CLIENT["name"],
            industry=DEMO_CLIENT["industry"],
            region=DEMO_CLIENT["region"],
            business_info=json.dumps(DEMO_CLIENT["business_info"], ensure_ascii=False),
            language=DEMO_CLIENT["language"],
            target_markets=json.dumps(DEMO_CLIENT["target_markets"]),
            website_url=DEMO_CLIENT["website_url"],
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        log.info("created client id=%s name=%s", client.id, client.name)

        # 2. Questions
        questions: list[Question] = []
        for category, text, priority in QUESTIONS:
            q = Question(
                client_id=client.id,
                text=text,
                category=category,
                priority=priority,
                is_active=True,
                language="en",
            )
            db.add(q)
            questions.append(q)
        db.commit()
        for q in questions:
            db.refresh(q)
        log.info("created %d questions", len(questions))

        brand_keywords = _resolve_brand_keywords(client)
        brand = client.name

        # 3. Runs + results + citations
        for run_spec in RUNS:
            run_dt = datetime.utcnow() - timedelta(days=run_spec["days_ago"])
            run = MonitorRun(
                client_id=client.id,
                name=run_spec["name"],
                note=run_spec["note"],
                platforms=json.dumps(PLATFORMS),
                question_count=len(questions),
                status="completed",
                finished_at=run_dt + timedelta(minutes=8),
            )
            run.created_at = run_dt
            db.add(run)
            db.commit()
            db.refresh(run)
            log.info("created run id=%s '%s' (days_ago=%s)", run.id, run.name, run_spec["days_ago"])

            mention_base_rate = 0.45  # baseline mention probability
            boost = run_spec["acme_mention_boost"]

            for q in questions:
                # competitor questions don't drive Acme mentions much
                effective_rate = (
                    (mention_base_rate + boost) if q.category != "competitor"
                    else (0.15 + boost * 0.5)
                )

                for platform in PLATFORMS:
                    # Skip ~10% randomly to simulate quota / errors
                    if random.random() < 0.05:
                        continue

                    mention = random.random() < effective_rate
                    answer = _build_answer(q.text, brand, mention)

                    # Citation density varies by platform — Perplexity is densest
                    if platform == "perplexity":
                        n_cites = random.randint(5, 8)
                        sr = _pick_citations(n_cites, include_placeholder=False, include_gemini=False)
                    elif platform == "chatgpt":
                        n_cites = random.randint(3, 5)
                        sr = _pick_citations(n_cites, include_placeholder=True, include_gemini=False)
                    else:  # google_ai (Gemini)
                        n_cites = random.randint(4, 7)
                        sr = _pick_citations(n_cites, include_placeholder=False, include_gemini=True)

                    # has_link is true if any http url in search_results
                    has_link = any("http" in (c.get("url") or "") for c in sr)
                    # crude position from answer if mention
                    position = None
                    if mention:
                        lower = answer.lower()
                        for kw in brand_keywords:
                            idx = lower.find(kw.lower())
                            if idx >= 0:
                                # 1-based paragraph index
                                position = answer.count("\n", 0, idx) + 1
                                break

                    mr = MonitorResult(
                        client_id=client.id,
                        question_id=q.id,
                        run_id=run.id,
                        platform=platform,
                        is_mentioned=mention,
                        position=position,
                        has_link=has_link,
                        sentiment="positive" if mention else None,
                        raw_answer=answer,
                        search_results=sr,
                        screenshot_path=None,
                    )
                    # Spread checked_at across the run window so trend chart looks live
                    offset = random.randint(0, 8 * 60)  # within ~8 minutes
                    mr.checked_at = run_dt + timedelta(seconds=offset)
                    db.add(mr)
                    db.commit()
                    db.refresh(mr)

                    # Ingest citations
                    ingest_citations_from_result(db, mr, brand_keywords)

        # Counts summary
        n_runs = db.query(MonitorRun).filter(MonitorRun.client_id == client.id).count()
        n_results = db.query(MonitorResult).filter(MonitorResult.client_id == client.id).count()
        n_citations = db.query(MonitorCitation).filter(
            MonitorCitation.client_id == client.id
        ).count()
        log.info("=== seed done: %d run(s), %d result(s), %d citation(s) ===",
                 n_runs, n_results, n_citations)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
