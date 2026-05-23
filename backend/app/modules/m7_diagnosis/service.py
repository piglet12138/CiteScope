"""M7 Website GEO Diagnosis Service.

Upgraded scoring aligned with geo-auditor weights:
  robots_txt (30) + llms_txt (15) + sitemap (10) + page_quality (45) = 100

Checks:
- robots.txt: AI crawler access with priority-based penalty (CRITICAL/HIGH/MEDIUM)
- llms.txt: llmstxt.org spec compliance (H1, blockquote, sections, links, size)
- Sitemap: existence, lastmod, HTTPS, URL count
- Page quality: Schema field validation, meta/indexability, content structure,
  contact/entity trust, performance, compliance
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("geo.diagnosis")

# ---------------------------------------------------------------------------
# AI Crawler registry with priority levels
# penalty = points deducted when blocked (from 30-pt robots budget)
# ---------------------------------------------------------------------------
AI_CRAWLERS = [
    # CRITICAL — blocking these severely hurts GEO visibility
    {"name": "GPTBot",           "platform": "OpenAI",     "priority": "CRITICAL", "penalty": 8},
    {"name": "Googlebot",        "platform": "Google",     "priority": "CRITICAL", "penalty": 8},
    # HIGH
    {"name": "OAI-SearchBot",    "platform": "OpenAI",     "priority": "HIGH",     "penalty": 5},
    {"name": "ChatGPT-User",     "platform": "OpenAI",     "priority": "HIGH",     "penalty": 5},
    {"name": "ClaudeBot",        "platform": "Anthropic",  "priority": "HIGH",     "penalty": 5},
    {"name": "Claude-SearchBot", "platform": "Anthropic",  "priority": "HIGH",     "penalty": 5},
    {"name": "PerplexityBot",    "platform": "Perplexity", "priority": "HIGH",     "penalty": 5},
    {"name": "Google-Extended",  "platform": "Google",     "priority": "HIGH",     "penalty": 5},
    {"name": "CCBot",            "platform": "CommonCrawl","priority": "HIGH",     "penalty": 5},
    # MEDIUM
    {"name": "anthropic-ai",     "platform": "Anthropic",  "priority": "MEDIUM",   "penalty": 2},
    {"name": "Applebot-Extended","platform": "Apple",      "priority": "MEDIUM",   "penalty": 2},
    {"name": "Bytespider",       "platform": "ByteDance",  "priority": "MEDIUM",   "penalty": 2},
    {"name": "meta-externalagent","platform": "Meta",      "priority": "MEDIUM",   "penalty": 2},
    {"name": "DuckAssistBot",    "platform": "DuckDuckGo", "priority": "MEDIUM",   "penalty": 2},
    {"name": "DeepSeekBot",      "platform": "DeepSeek",   "priority": "MEDIUM",   "penalty": 2},
    {"name": "cohere-ai",        "platform": "Cohere",     "priority": "MEDIUM",   "penalty": 2},
]

# Schema types and their required/recommended fields for validation
SCHEMA_VALIDATION = {
    "Organization": {
        "required": ["name", "url"],
        "recommended": ["description", "logo", "sameAs", "email", "telephone", "address"],
    },
    "LocalBusiness": {
        "required": ["name", "url"],
        "recommended": ["description", "logo", "address", "telephone", "openingHours", "sameAs"],
    },
    "Product": {
        "required": ["name"],
        "recommended": ["description", "image", "offers", "brand", "aggregateRating"],
    },
    "FAQPage": {
        "required": ["mainEntity"],
        "recommended": [],
    },
    "Article": {
        "required": ["headline", "author", "datePublished"],
        "recommended": ["dateModified", "description", "image", "publisher"],
    },
    "WebSite": {
        "required": ["name", "url"],
        "recommended": ["inLanguage", "potentialAction"],
    },
    "BreadcrumbList": {
        "required": ["itemListElement"],
        "recommended": [],
    },
    "HowTo": {
        "required": ["name", "step"],
        "recommended": ["description", "totalTime", "image"],
    },
    "SoftwareApplication": {
        "required": ["name", "offers"],
        "recommended": ["description", "applicationCategory", "operatingSystem"],
    },
    "Manufacturer": {
        "required": ["name"],
        "recommended": ["description", "url", "logo", "address"],
    },
}

COMPLIANCE_PAGES = {
    "privacy_policy": [
        "/privacy", "/privacy-policy", "/en/privacy", "/en/privacy-policy",
        "/legal/privacy", "/pages/privacy-policy",
    ],
    "terms": [
        "/terms", "/terms-of-service", "/terms-and-conditions",
        "/en/terms", "/legal/terms", "/pages/terms",
    ],
    "cookie_policy": [
        "/cookie", "/cookie-policy", "/en/cookie-policy",
    ],
    "imprint": [
        "/imprint", "/impressum", "/en/imprint", "/legal/imprint",
    ],
}

# Grade scale
GRADE_SCALE = [
    (90, "A"), (75, "B"), (60, "C"), (40, "D"), (0, "F"),
]


def _grade(score: int) -> str:
    for threshold, grade in GRADE_SCALE:
        if score >= threshold:
            return grade
    return "F"


def run_diagnosis(url: str) -> dict[str, Any]:
    """Run a full GEO diagnosis on the given URL. Returns structured report."""
    if not url.startswith("http"):
        url = "https://" + url
    url = url.rstrip("/")
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    report: dict[str, Any] = {
        "url": url,
        "base_url": base,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": {},
        "scores": {},
        "overall_score": 0,
        "grade": "F",
        "action_items": [],
    }

    http = httpx.Client(
        timeout=30.0,
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        },
    )

    try:
        _check_robots(http, base, report)
        _check_llms_txt(http, base, report)
        _check_sitemap(http, base, report)
        _check_page(http, url, report)
        _check_compliance_pages(http, base, report)
        _calculate_scores(report)
    except Exception as e:
        logger.exception("Diagnosis failed for %s", url)
        report["error"] = str(e)
    finally:
        http.close()

    return report


# ---------------------------------------------------------------------------
# Check: robots.txt (budget: 30 pts)
# ---------------------------------------------------------------------------

def _check_robots(http: httpx.Client, base: str, report: dict) -> None:
    """Analyze robots.txt with priority-based crawler penalty scoring."""
    result: dict[str, Any] = {
        "exists": False,
        "crawlers": [],          # per-crawler status
        "blocked_critical": [],
        "blocked_high": [],
        "blocked_medium": [],
        "allowed_count": 0,
        "blocked_count": 0,
        "has_sitemap_ref": False,
        "has_wildcard_block": False,
        "raw_snippet": "",
    }

    try:
        resp = http.get(f"{base}/robots.txt")
        if resp.status_code == 200:
            text = resp.text
            result["exists"] = True
            result["raw_snippet"] = text[:3000]

            result["has_sitemap_ref"] = bool(
                re.search(r"(?i)^sitemap:", text, re.MULTILINE)
            )

            # Check wildcard Disallow: /
            wildcard_block = False
            wildcard_pattern = re.compile(
                r"User-agent:\s*\*\s*\n((?:(?:Allow|Disallow|Crawl-delay|Content-Signal):[^\n]*\n?)*)",
                re.IGNORECASE,
            )
            wm = wildcard_pattern.search(text)
            if wm:
                block = wm.group(0)
                if re.search(r"Disallow:\s*/\s*$", block, re.MULTILINE):
                    wildcard_block = True
            result["has_wildcard_block"] = wildcard_block

            # Per-crawler analysis
            for crawler_info in AI_CRAWLERS:
                name = crawler_info["name"]
                status = "allowed"  # default

                pattern = re.compile(
                    rf"User-agent:\s*{re.escape(name)}\s*\n"
                    rf"((?:(?:Allow|Disallow|Crawl-delay|Content-Signal):[^\n]*\n?)*)",
                    re.IGNORECASE,
                )
                match = pattern.search(text)
                if match:
                    block = match.group(0)
                    has_disallow_root = bool(re.search(r"Disallow:\s*/\s*$", block, re.MULTILINE))
                    has_allow = bool(re.search(r"Allow:\s*/", block, re.MULTILINE))
                    if has_disallow_root and not has_allow:
                        status = "blocked"
                    elif has_disallow_root and has_allow:
                        status = "partial"
                else:
                    # Inherits wildcard
                    status = "blocked" if wildcard_block else "allowed"

                entry = {
                    "name": name,
                    "platform": crawler_info["platform"],
                    "priority": crawler_info["priority"],
                    "status": status,
                }
                result["crawlers"].append(entry)

                if status == "blocked":
                    result["blocked_count"] += 1
                    if crawler_info["priority"] == "CRITICAL":
                        result["blocked_critical"].append(name)
                    elif crawler_info["priority"] == "HIGH":
                        result["blocked_high"].append(name)
                    else:
                        result["blocked_medium"].append(name)
                else:
                    result["allowed_count"] += 1
        else:
            # No robots.txt — all crawlers technically allowed
            result["allowed_count"] = len(AI_CRAWLERS)
            for ci in AI_CRAWLERS:
                result["crawlers"].append({
                    "name": ci["name"], "platform": ci["platform"],
                    "priority": ci["priority"], "status": "allowed",
                })
    except httpx.HTTPError:
        pass

    report["checks"]["robots_txt"] = result


# ---------------------------------------------------------------------------
# Check: llms.txt (budget: 15 pts)
# ---------------------------------------------------------------------------

def _check_llms_txt(http: httpx.Client, base: str, report: dict) -> None:
    """Validate llms.txt against llmstxt.org spec."""
    result: dict[str, Any] = {
        "exists": False,
        "spec_score": 0,       # 0-100 internal score
        "has_h1_title": False,
        "has_blockquote": False,
        "has_sections": False,
        "has_links": False,
        "link_count": 0,
        "word_count": 0,
        "file_size_kb": 0,
        "issues": [],
    }

    try:
        resp = http.get(f"{base}/llms.txt")
        if resp.status_code == 200 and len(resp.text.strip()) > 20:
            text = resp.text
            result["exists"] = True
            result["word_count"] = len(text.split())
            result["file_size_kb"] = round(len(text.encode("utf-8")) / 1024, 1)

            spec_pts = 0

            # H1 title (25 pts)
            h1_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
            if h1_match:
                result["has_h1_title"] = True
                spec_pts += 25
                # Check if H1 is first non-empty line
                first_line = ""
                for line in text.split("\n"):
                    if line.strip():
                        first_line = line.strip()
                        break
                if first_line.startswith("# "):
                    spec_pts += 5  # bonus: H1 is first line
            else:
                result["issues"].append("Missing H1 title (# Title)")

            # Blockquote description (20 pts)
            if re.search(r"^>\s+.+", text, re.MULTILINE):
                result["has_blockquote"] = True
                spec_pts += 20
            else:
                result["issues"].append("Missing blockquote description (> Description)")

            # Sections H2 (15 pts)
            sections = re.findall(r"^##\s+(.+)$", text, re.MULTILINE)
            if sections:
                result["has_sections"] = True
                result["section_names"] = sections[:10]
                spec_pts += 15
            else:
                result["issues"].append("No ## sections found")

            # Markdown links (15 pts)
            links = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", text)
            result["link_count"] = len(links)
            if links:
                result["has_links"] = True
                spec_pts += 15
            else:
                result["issues"].append("No markdown links found")

            # Size validation (10 pts)
            size_kb = result["file_size_kb"]
            if size_kb <= 512:
                spec_pts += 10
            elif size_kb <= 1024:
                spec_pts += 5
                result["issues"].append(f"File size {size_kb}KB exceeds recommended 512KB")

            # No duplicate URLs bonus (5 pts)
            urls = [u for _, u in links]
            if len(urls) == len(set(urls)):
                spec_pts += 5

            result["spec_score"] = min(spec_pts, 100)
    except httpx.HTTPError:
        pass

    report["checks"]["llms_txt"] = result


# ---------------------------------------------------------------------------
# Check: sitemap.xml (budget: 10 pts)
# ---------------------------------------------------------------------------

def _check_sitemap(http: httpx.Client, base: str, report: dict) -> None:
    """Check sitemap existence and quality."""
    result: dict[str, Any] = {
        "exists": False,
        "url_count": 0,
        "uses_https": True,
        "has_lastmod": False,
        "lastmod_ratio": 0.0,
        "is_index": False,
        "content_type_ok": True,
    }

    for path in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml"]:
        try:
            resp = http.get(f"{base}{path}")
            ct = resp.headers.get("content-type", "")
            if resp.status_code == 200 and ("<urlset" in resp.text or "<sitemapindex" in resp.text):
                text = resp.text
                result["exists"] = True
                result["is_index"] = "<sitemapindex" in text
                result["url_count"] = text.count("<loc>")
                result["content_type_ok"] = "xml" in ct or "text" in ct

                # lastmod analysis
                lastmod_count = text.count("<lastmod>")
                loc_count = max(text.count("<loc>"), 1)
                result["has_lastmod"] = lastmod_count > 0
                result["lastmod_ratio"] = round(lastmod_count / loc_count, 2)

                # HTTPS check
                http_urls = re.findall(r"<loc>(http://[^<]+)</loc>", text)
                if http_urls:
                    result["uses_https"] = False

                break
        except httpx.HTTPError:
            continue

    report["checks"]["sitemap"] = result


# ---------------------------------------------------------------------------
# Check: page quality (budget: 45 pts)
# ---------------------------------------------------------------------------

def _check_page(http: httpx.Client, url: str, report: dict) -> None:
    """Analyze page for Schema, meta tags, content, contact, indexability."""

    schema_result: dict[str, Any] = {
        "types_found": [],
        "has_organization": False,
        "has_product": False,
        "has_faqpage": False,
        "has_article": False,
        "has_breadcrumb": False,
        "has_website": False,
        "field_validation": {},   # per-type: {missing_required, missing_recommended}
        "schema_score": 0,        # 0-100 per-schema quality
        "raw_schemas": [],
    }

    meta_result: dict[str, Any] = {
        "has_title": False,
        "title": "",
        "title_length": 0,
        "has_description": False,
        "description": "",
        "desc_length": 0,
        "has_og_tags": False,
        "has_canonical": False,
        "has_hreflang": False,
        "has_viewport": False,
        "is_indexable": True,     # no noindex
        "robots_directives": [],
    }

    content_result: dict[str, Any] = {
        "word_count": 0,
        "heading_count": {"h1": 0, "h2": 0, "h3": 0},
        "has_faq_section": False,
        "has_author": False,
        "image_count": 0,
        "images_with_alt": 0,
        "alt_ratio": 0.0,
        "internal_links": 0,
        "external_links": 0,
        "response_time_ms": 0,
        "page_size_kb": 0,
        "is_js_rendered": False,
    }

    contact_result: dict[str, Any] = {
        "has_email": False,
        "has_phone": False,
        "has_address": False,
        "has_contact_form": False,
        "has_whatsapp": False,
        "has_social_links": False,
    }

    try:
        t0 = time.time()
        resp = http.get(url)
        elapsed_ms = int((time.time() - t0) * 1000)
        content_result["response_time_ms"] = elapsed_ms
        content_result["page_size_kb"] = round(len(resp.content) / 1024, 1)

        if resp.status_code != 200:
            report["checks"]["schema"] = schema_result
            report["checks"]["meta_tags"] = meta_result
            report["checks"]["content"] = content_result
            report["checks"]["contact"] = contact_result
            return

        html = resp.text
        parsed = urlparse(url)
        domain = parsed.netloc

        # --- Indexability (meta robots) ---
        robots_meta = re.findall(
            r'<meta[^>]*name=["\']robots["\'][^>]*content=["\']([^"\']*)["\']',
            html, re.IGNORECASE,
        )
        for rm in robots_meta:
            meta_result["robots_directives"].extend(
                d.strip().lower() for d in rm.split(",")
            )
        # X-Robots-Tag header
        xrt = resp.headers.get("X-Robots-Tag", "")
        if xrt:
            meta_result["robots_directives"].extend(
                d.strip().lower() for d in xrt.split(",")
            )
        meta_result["is_indexable"] = "noindex" not in meta_result["robots_directives"]

        # --- Schema / JSON-LD with field validation ---
        jsonld_blocks = re.findall(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE,
        )
        all_items = []
        for block in jsonld_blocks:
            try:
                data = json.loads(block.strip())
                # Handle @graph arrays
                if isinstance(data, dict) and "@graph" in data:
                    items = data["@graph"]
                elif isinstance(data, list):
                    items = data
                else:
                    items = [data]
                for item in items:
                    if isinstance(item, dict):
                        all_items.append(item)
            except (json.JSONDecodeError, AttributeError):
                pass

        total_schema_quality = 0
        schema_count = 0
        for item in all_items:
            t = item.get("@type", "")
            types = t if isinstance(t, list) else [t]
            schema_result["types_found"].extend(types)
            schema_result["raw_schemas"].append(item)

            # Validate fields per type
            for st in types:
                rules = SCHEMA_VALIDATION.get(st)
                if not rules:
                    continue
                missing_req = [f for f in rules["required"] if not item.get(f)]
                missing_rec = [f for f in rules["recommended"] if not item.get(f)]
                quality = 100
                quality -= len(missing_req) * 20
                quality -= len(missing_rec) * 5
                quality = max(quality, 0)
                schema_result["field_validation"][st] = {
                    "missing_required": missing_req,
                    "missing_recommended": missing_rec,
                    "quality": quality,
                }
                total_schema_quality += quality
                schema_count += 1

        if schema_count:
            schema_result["schema_score"] = round(total_schema_quality / schema_count)

        schema_result["types_found"] = list(set(schema_result["types_found"]))
        schema_result["has_organization"] = any(
            t in schema_result["types_found"]
            for t in ["Organization", "LocalBusiness", "Manufacturer"]
        )
        schema_result["has_product"] = "Product" in schema_result["types_found"]
        schema_result["has_faqpage"] = "FAQPage" in schema_result["types_found"]
        schema_result["has_article"] = any(
            t in schema_result["types_found"]
            for t in ["Article", "NewsArticle", "BlogPosting"]
        )
        schema_result["has_breadcrumb"] = "BreadcrumbList" in schema_result["types_found"]
        schema_result["has_website"] = "WebSite" in schema_result["types_found"]

        # --- Meta tags ---
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if title_match:
            title_text = title_match.group(1).strip()
            meta_result["has_title"] = True
            meta_result["title"] = title_text[:200]
            meta_result["title_length"] = len(title_text)

        desc_match = re.search(
            r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
            html, re.IGNORECASE,
        )
        if not desc_match:
            desc_match = re.search(
                r'<meta[^>]*content=["\']([^"\']*)["\'][^>]*name=["\']description["\']',
                html, re.IGNORECASE,
            )
        if desc_match:
            desc_text = desc_match.group(1).strip()
            meta_result["has_description"] = True
            meta_result["description"] = desc_text[:300]
            meta_result["desc_length"] = len(desc_text)

        meta_result["has_og_tags"] = bool(
            re.search(r'<meta[^>]*property=["\']og:', html, re.IGNORECASE)
        )
        meta_result["has_canonical"] = bool(
            re.search(r'<link[^>]*rel=["\']canonical["\']', html, re.IGNORECASE)
        )
        meta_result["has_hreflang"] = bool(
            re.search(r'<link[^>]*hreflang=', html, re.IGNORECASE)
        )
        meta_result["has_viewport"] = bool(
            re.search(r'<meta[^>]*name=["\']viewport["\']', html, re.IGNORECASE)
        )

        # --- Content analysis ---
        clean = re.sub(
            r"<(script|style|noscript)[^>]*>.*?</\1>", "",
            html, flags=re.DOTALL | re.IGNORECASE,
        )
        text_only = re.sub(r"<[^>]+>", " ", clean)
        text_only = re.sub(r"\s+", " ", text_only).strip()
        content_result["word_count"] = len(text_only.split())

        # JS-rendered detection (very little visible text = probably SPA)
        if content_result["word_count"] < 50 and len(html) > 5000:
            content_result["is_js_rendered"] = True

        for level in ["h1", "h2", "h3"]:
            content_result["heading_count"][level] = len(
                re.findall(rf"<{level}[\s>]", html, re.IGNORECASE)
            )

        content_result["has_faq_section"] = bool(
            re.search(r"(?i)(FAQ|frequently\s+asked|common\s+questions)", html)
        )
        content_result["has_author"] = bool(
            re.search(r'(?i)(author|written\s+by|posted\s+by|class=["\'][^"\']*author)', html)
        )

        # Images & alt text
        images = re.findall(r"<img\s[^>]*>", html, re.IGNORECASE)
        content_result["image_count"] = len(images)
        if images:
            with_alt = sum(1 for img in images if re.search(r'alt=["\'][^"\']+["\']', img))
            content_result["images_with_alt"] = with_alt
            content_result["alt_ratio"] = round(with_alt / len(images), 2)

        # Links
        links = re.findall(r'href=["\']([^"\'#]+)["\']', html, re.IGNORECASE)
        for link in links:
            if link.startswith(("http://", "https://")):
                if domain in link:
                    content_result["internal_links"] += 1
                else:
                    content_result["external_links"] += 1
            elif link.startswith("/"):
                content_result["internal_links"] += 1

        # --- Contact info ---
        contact_result["has_email"] = bool(
            re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", html)
        )
        contact_result["has_phone"] = bool(
            re.search(r"(?:\+?\d{1,4}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}", html)
        )
        contact_result["has_address"] = bool(
            re.search(r"(?i)(street|road|avenue|building|floor|suite|no\.\s*\d|address)", html)
        )
        contact_result["has_contact_form"] = bool(
            re.search(r"<form", html, re.IGNORECASE)
        )
        contact_result["has_whatsapp"] = bool(
            re.search(r"(?i)(whatsapp|wa\.me)", html)
        )
        # Social links
        contact_result["has_social_links"] = bool(
            re.search(r"(?i)(linkedin\.com|twitter\.com|x\.com|facebook\.com|youtube\.com)", html)
        )

    except httpx.HTTPError as e:
        logger.warning("Failed to fetch page %s: %s", url, e)

    report["checks"]["schema"] = schema_result
    report["checks"]["meta_tags"] = meta_result
    report["checks"]["content"] = content_result
    report["checks"]["contact"] = contact_result


# ---------------------------------------------------------------------------
# Check: compliance pages
# ---------------------------------------------------------------------------

def _check_compliance_pages(http: httpx.Client, base: str, report: dict) -> None:
    """Check for privacy policy, terms, cookie policy, imprint."""
    result: dict[str, Any] = {}

    for page_type, paths in COMPLIANCE_PAGES.items():
        found = False
        for path in paths:
            try:
                resp = http.head(f"{base}{path}", follow_redirects=True)
                if resp.status_code == 200:
                    found = True
                    break
            except httpx.HTTPError:
                continue
        result[page_type] = found

    # Fallback: check homepage HTML for compliance links
    try:
        resp = http.get(base)
        if resp.status_code == 200:
            html_lower = resp.text.lower()
            if not result.get("privacy_policy"):
                result["privacy_policy"] = "privacy" in html_lower and "policy" in html_lower
            if not result.get("terms"):
                result["terms"] = "terms" in html_lower and ("service" in html_lower or "condition" in html_lower)
            result["has_cookie_banner"] = any(
                kw in html_lower
                for kw in ["cookie-consent", "cookie-banner", "cookieconsent", "gdpr", "cookie_notice"]
            )
            result["is_https"] = base.startswith("https://")
        else:
            result["has_cookie_banner"] = False
            result["is_https"] = base.startswith("https://")
    except httpx.HTTPError:
        result["has_cookie_banner"] = False
        result["is_https"] = base.startswith("https://")

    report["checks"]["compliance"] = result


# ---------------------------------------------------------------------------
# Scoring: 30 + 15 + 10 + 45 = 100
# ---------------------------------------------------------------------------

def _calculate_scores(report: dict) -> None:
    """Calculate scores per dimension and overall, generate action items."""
    checks = report["checks"]
    scores: dict[str, dict[str, Any]] = {}
    actions: list[dict[str, Any]] = []

    # =======================================================================
    # 1. robots.txt (30 pts)
    # =======================================================================
    pts = 30  # Start full, deduct for issues
    robots = checks.get("robots_txt", {})

    if not robots.get("exists"):
        # No robots.txt — not necessarily bad (all allowed), but missing best practice
        pts -= 5
        actions.append({
            "priority": "P1", "category": "robots",
            "action": "Create robots.txt with explicit AI crawler Allow rules and Sitemap reference",
            "detail": "While missing robots.txt means crawlers are allowed, explicitly allowing them signals intent.",
        })
    else:
        # Apply priority-based penalties for blocked crawlers
        for crawler_info in AI_CRAWLERS:
            name = crawler_info["name"]
            crawler_entry = next(
                (c for c in robots.get("crawlers", []) if c["name"] == name), None
            )
            if crawler_entry and crawler_entry["status"] == "blocked":
                penalty = crawler_info["penalty"]
                pts -= penalty
            elif crawler_entry and crawler_entry["status"] == "partial":
                penalty = crawler_info["penalty"] // 2
                pts -= penalty

        blocked_critical = robots.get("blocked_critical", [])
        blocked_high = robots.get("blocked_high", [])
        blocked_medium = robots.get("blocked_medium", [])

        if blocked_critical:
            actions.append({
                "priority": "P0", "category": "robots",
                "action": f"CRITICAL: Unblock {', '.join(blocked_critical)} in robots.txt",
                "detail": "These are the most important AI crawlers. Blocking them severely limits your visibility in ChatGPT, Google AI Overviews, etc.",
            })
        if blocked_high:
            actions.append({
                "priority": "P0", "category": "robots",
                "action": f"Unblock high-priority AI crawlers: {', '.join(blocked_high)}",
                "detail": "These crawlers power Claude, Perplexity, and ChatGPT Search. Go to Cloudflare → Security → Bots to manage.",
            })
        if blocked_medium:
            actions.append({
                "priority": "P1", "category": "robots",
                "action": f"Consider unblocking: {', '.join(blocked_medium)}",
            })

    if not robots.get("has_sitemap_ref") and checks.get("sitemap", {}).get("exists"):
        pts -= 2
        actions.append({
            "priority": "P1", "category": "robots",
            "action": "Add Sitemap: directive in robots.txt",
        })

    scores["robots_txt"] = {"score": max(pts, 0), "max": 30}

    # =======================================================================
    # 2. llms.txt (15 pts)
    # =======================================================================
    llms = checks.get("llms_txt", {})

    if not llms.get("exists"):
        pts = 0
        actions.append({
            "priority": "P0", "category": "llms_txt",
            "action": "Create /llms.txt following llmstxt.org spec",
            "detail": "Include: # Company Name, > description, ## sections with markdown links to key pages. This is your brand's guide for AI engines.",
        })
    else:
        # Map spec_score (0-100) to 0-15 pts
        pts = round(llms["spec_score"] * 15 / 100)
        for issue in llms.get("issues", []):
            actions.append({
                "priority": "P1", "category": "llms_txt",
                "action": f"llms.txt: {issue}",
            })

    scores["llms_txt"] = {"score": min(pts, 15), "max": 15}

    # =======================================================================
    # 3. sitemap.xml (10 pts)
    # =======================================================================
    sitemap = checks.get("sitemap", {})

    if not sitemap.get("exists"):
        pts = 0
        actions.append({
            "priority": "P0", "category": "sitemap",
            "action": "Create and submit XML sitemap",
            "detail": "Include all important pages with <lastmod> dates. Submit to Google Search Console.",
        })
    else:
        pts = 5  # base for existing
        if sitemap.get("has_lastmod"):
            pts += 5
        else:
            actions.append({
                "priority": "P1", "category": "sitemap",
                "action": "Add <lastmod> dates to sitemap entries",
                "detail": "Helps AI crawlers prioritize fresh content.",
            })
        if not sitemap.get("uses_https"):
            pts -= 2
            actions.append({
                "priority": "P1", "category": "sitemap",
                "action": "Change sitemap URLs from HTTP to HTTPS",
            })

    scores["sitemap"] = {"score": max(min(pts, 10), 0), "max": 10}

    # =======================================================================
    # 4. Page Quality (45 pts)
    #    - Schema: 15 pts
    #    - Indexability + Meta: 10 pts
    #    - Content structure: 10 pts
    #    - Entity/Trust: 5 pts
    #    - Performance: 5 pts
    # =======================================================================
    schema = checks.get("schema", {})
    meta = checks.get("meta_tags", {})
    content = checks.get("content", {})
    contact = checks.get("contact", {})
    compliance = checks.get("compliance", {})

    # --- 4a. Schema (15 pts) ---
    pts_schema = 0
    if schema.get("types_found"):
        pts_schema += 3  # has any schema
        # Quality bonus based on field validation
        sq = schema.get("schema_score", 0)
        pts_schema += round(sq * 5 / 100)  # 0-5 pts from quality

        if schema.get("has_organization"):
            pts_schema += 3
        else:
            actions.append({
                "priority": "P0", "category": "schema",
                "action": "Add Organization Schema (name, url, logo, description, sameAs)",
            })

        if schema.get("has_faqpage"):
            pts_schema += 2
        if schema.get("has_product"):
            pts_schema += 1
        if schema.get("has_breadcrumb"):
            pts_schema += 1

        # Report missing required fields
        for stype, validation in schema.get("field_validation", {}).items():
            missing = validation.get("missing_required", [])
            if missing:
                actions.append({
                    "priority": "P1", "category": "schema",
                    "action": f"{stype} Schema missing required fields: {', '.join(missing)}",
                })
    else:
        actions.append({
            "priority": "P0", "category": "schema",
            "action": "Deploy JSON-LD Schema markup (none found)",
            "detail": "Add Organization, Product, FAQPage schemas. Critical for AI engines to understand your business entity.",
        })

    scores["page_schema"] = {"score": min(pts_schema, 15), "max": 15}

    # --- 4b. Indexability + Meta (10 pts) ---
    pts_meta = 0
    if meta.get("is_indexable"):
        pts_meta += 3
    else:
        actions.append({
            "priority": "P0", "category": "meta",
            "action": "Remove noindex directive — page is blocked from search engines and AI",
        })

    if meta.get("has_title"):
        pts_meta += 2
        tl = meta.get("title_length", 0)
        if tl > 70:
            actions.append({
                "priority": "P2", "category": "meta",
                "action": f"Title tag too long ({tl} chars, aim for ≤60)",
            })
    else:
        actions.append({"priority": "P0", "category": "meta", "action": "Add <title> tag"})

    if meta.get("has_description"):
        pts_meta += 2
        dl = meta.get("desc_length", 0)
        if dl < 50 or dl > 160:
            actions.append({
                "priority": "P2", "category": "meta",
                "action": f"Meta description length ({dl} chars, aim for 120-155)",
            })
    else:
        actions.append({
            "priority": "P1", "category": "meta",
            "action": "Add meta description (include brand + key product + certification)",
        })

    if meta.get("has_og_tags"):
        pts_meta += 1
    if meta.get("has_canonical"):
        pts_meta += 1
    if meta.get("has_viewport"):
        pts_meta += 1

    scores["page_meta"] = {"score": min(pts_meta, 10), "max": 10}

    # --- 4c. Content structure (10 pts) ---
    pts_content = 0
    wc = content.get("word_count", 0)
    if wc >= 1000:
        pts_content += 3
    elif wc >= 500:
        pts_content += 2
    elif wc >= 200:
        pts_content += 1
    else:
        if content.get("is_js_rendered"):
            actions.append({
                "priority": "P0", "category": "content",
                "action": "Page appears JS-rendered — AI crawlers may see blank content. Add server-side rendering (SSR).",
            })
        else:
            actions.append({
                "priority": "P1", "category": "content",
                "action": f"Page has only ~{wc} words. Aim for 500+ with rich descriptions",
            })

    h = content.get("heading_count", {})
    h1_count = h.get("h1", 0)
    if h1_count == 1:
        pts_content += 2
    elif h1_count > 1:
        pts_content += 1
        actions.append({
            "priority": "P2", "category": "content",
            "action": f"Multiple H1 headings found ({h1_count}). Use exactly one H1.",
        })
    else:
        actions.append({"priority": "P1", "category": "content", "action": "Add a clear H1 heading"})

    if h.get("h2", 0) >= 2:
        pts_content += 1

    if content.get("has_faq_section"):
        pts_content += 2
    else:
        actions.append({
            "priority": "P1", "category": "content",
            "action": "Add FAQ section (AI engines heavily favor Q&A content for citations)",
        })

    alt_ratio = content.get("alt_ratio", 0)
    if alt_ratio >= 0.8:
        pts_content += 1
    elif content.get("image_count", 0) > 0:
        actions.append({
            "priority": "P2", "category": "content",
            "action": f"Only {int(alt_ratio*100)}% of images have alt text. Aim for 100%.",
        })

    if content.get("has_author"):
        pts_content += 1

    scores["page_content"] = {"score": min(pts_content, 10), "max": 10}

    # --- 4d. Entity & Trust (5 pts) ---
    pts_trust = 0
    trust_signals = [
        contact.get("has_email"),
        contact.get("has_phone"),
        contact.get("has_address"),
        contact.get("has_contact_form"),
        contact.get("has_social_links"),
    ]
    pts_trust = sum(1 for s in trust_signals if s)

    if not contact.get("has_contact_form"):
        actions.append({
            "priority": "P1", "category": "entity",
            "action": "Add inquiry/contact form for B2B buyers",
        })
    if not contact.get("has_address"):
        actions.append({
            "priority": "P1", "category": "entity",
            "action": "Display company address prominently",
        })

    scores["page_trust"] = {"score": min(pts_trust, 5), "max": 5}

    # --- 4e. Performance & Compliance (5 pts) ---
    pts_perf = 0

    if compliance.get("is_https", True):
        pts_perf += 1
    else:
        actions.append({"priority": "P0", "category": "performance", "action": "Enable HTTPS"})

    resp_time = content.get("response_time_ms", 0)
    if resp_time > 0 and resp_time < 2000:
        pts_perf += 1
    elif resp_time >= 2000:
        actions.append({
            "priority": "P1", "category": "performance",
            "action": f"Slow page load ({resp_time}ms). Aim for <2000ms for crawlability.",
        })

    page_size = content.get("page_size_kb", 0)
    if 0 < page_size <= 500:
        pts_perf += 1
    elif page_size > 500:
        actions.append({
            "priority": "P2", "category": "performance",
            "action": f"Page size {page_size}KB. Aim for <500KB for fast AI crawler ingestion.",
        })

    if compliance.get("privacy_policy"):
        pts_perf += 1
    else:
        actions.append({
            "priority": "P0", "category": "compliance",
            "action": "Create Privacy Policy page (GDPR requirement for EU market)",
        })

    if compliance.get("has_cookie_banner"):
        pts_perf += 1
    elif compliance.get("terms"):
        pts_perf += 1
    else:
        actions.append({
            "priority": "P1", "category": "compliance",
            "action": "Add GDPR cookie consent banner or Terms of Service page",
        })

    scores["page_perf"] = {"score": min(pts_perf, 5), "max": 5}

    # =======================================================================
    # Overall
    # =======================================================================
    total = sum(s["score"] for s in scores.values())
    report["scores"] = scores
    report["overall_score"] = total
    report["grade"] = _grade(total)

    # Sort actions by priority
    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    actions.sort(key=lambda a: priority_order.get(a.get("priority", "P2"), 9))
    report["action_items"] = actions
