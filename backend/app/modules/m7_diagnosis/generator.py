"""GEO Asset Generators — auto-generate Schema JSON-LD and llms.txt for client websites.

Based on geo-auditor's generate_schema.py and generate_llms_txt.py logic.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("geo.generator")


# ---------------------------------------------------------------------------
# Schema JSON-LD Generator
# ---------------------------------------------------------------------------

# Business type detection keywords
_BUSINESS_SIGNALS = {
    "SoftwareApplication": [
        "saas", "software", "platform", "app", "dashboard", "api",
        "sign up", "free trial", "pricing", "get started", "demo",
    ],
    "ProfessionalService": [
        "law firm", "lawyer", "consultant", "advisor", "accounting",
        "dentist", "doctor", "clinic", "therapy", "agency",
    ],
    "LocalBusiness": [
        "visit us", "our office", "office hours", "directions",
        "location", "walk-in", "appointment",
    ],
    "Manufacturer": [
        "factory", "manufacturer", "manufacturing", "OEM", "ODM",
        "production line", "ISO", "CE certified", "quality control",
        "export", "MOQ", "bulk order",
    ],
}


def generate_schema(url: str) -> dict[str, Any]:
    """Fetch a URL, extract info, and generate recommended Schema JSON-LD.

    Returns:
        {
            "url": str,
            "detected_type": str,
            "schemas": [...],          # list of schema objects
            "embed_code": str,         # ready-to-paste <script> tag
            "extracted": {...},        # what we found on the page
        }
    """
    if not url.startswith("http"):
        url = "https://" + url
    url = url.rstrip("/")
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    http = httpx.Client(
        timeout=30.0, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; GEO-Generator/1.0)"},
    )

    try:
        resp = http.get(url)
        html = resp.text if resp.status_code == 200 else ""
    except httpx.HTTPError:
        html = ""
    finally:
        http.close()

    extracted = _extract_page_info(html, url, base)
    detected_type = _detect_business_type(html)
    schemas = _build_schemas(extracted, detected_type, url, base)

    graph = {"@context": "https://schema.org", "@graph": schemas}
    embed = (
        '<script type="application/ld+json">\n'
        + json.dumps(graph, indent=2, ensure_ascii=False)
        + "\n</script>"
    )

    return {
        "url": url,
        "detected_type": detected_type,
        "schemas": schemas,
        "embed_code": embed,
        "extracted": extracted,
    }


def _extract_page_info(html: str, url: str, base: str) -> dict[str, Any]:
    """Extract structured info from page HTML."""
    info: dict[str, Any] = {}

    # Title
    og_title = re.search(
        r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']*)["\']',
        html, re.IGNORECASE,
    )
    title_tag = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    h1_tag = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)

    info["name"] = (
        (og_title and og_title.group(1).strip())
        or (title_tag and re.sub(r"<[^>]+>", "", title_tag.group(1)).strip())
        or (h1_tag and re.sub(r"<[^>]+>", "", h1_tag.group(1)).strip())
        or urlparse(url).netloc
    )

    # Description
    og_desc = re.search(
        r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\']([^"\']*)["\']',
        html, re.IGNORECASE,
    )
    meta_desc = re.search(
        r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
        html, re.IGNORECASE,
    )
    info["description"] = (
        (og_desc and og_desc.group(1).strip())
        or (meta_desc and meta_desc.group(1).strip())
        or ""
    )

    # Logo / image
    og_image = re.search(
        r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']*)["\']',
        html, re.IGNORECASE,
    )
    logo_img = re.search(
        r'<img[^>]*alt=["\'][^"\']*logo[^"\']*["\'][^>]*src=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    info["logo"] = (
        (og_image and og_image.group(1).strip())
        or (logo_img and logo_img.group(1).strip())
        or ""
    )
    # Make absolute
    if info["logo"] and not info["logo"].startswith("http"):
        info["logo"] = base.rstrip("/") + "/" + info["logo"].lstrip("/")

    # Language
    lang_match = re.search(r'<html[^>]*lang=["\']([^"\']+)["\']', html, re.IGNORECASE)
    info["language"] = lang_match.group(1) if lang_match else "en"

    # Social links
    socials = []
    social_patterns = [
        r'href=["\']([^"\']*linkedin\.com[^"\']*)["\']',
        r'href=["\']([^"\']*twitter\.com[^"\']*)["\']',
        r'href=["\']([^"\']*x\.com[^"\']*)["\']',
        r'href=["\']([^"\']*facebook\.com[^"\']*)["\']',
        r'href=["\']([^"\']*youtube\.com[^"\']*)["\']',
        r'href=["\']([^"\']*instagram\.com[^"\']*)["\']',
        r'href=["\']([^"\']*github\.com[^"\']*)["\']',
    ]
    for pat in social_patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            socials.append(m.group(1))
    info["sameAs"] = socials

    # Contact
    email_match = re.search(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", html)
    info["email"] = email_match.group(1) if email_match else ""

    phone_match = re.search(
        r'href=["\']tel:([^"\']+)["\']', html, re.IGNORECASE,
    )
    if not phone_match:
        phone_match = re.search(
            r"(\+\d{1,4}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4})", html,
        )
    info["telephone"] = phone_match.group(1).strip() if phone_match else ""

    # FAQs — look for existing FAQ schema or HTML patterns
    faqs = []
    # Try dt/dd pattern
    dt_matches = re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", html, re.DOTALL | re.IGNORECASE)
    for q, a in dt_matches[:10]:
        q_clean = re.sub(r"<[^>]+>", "", q).strip()
        a_clean = re.sub(r"<[^>]+>", "", a).strip()
        if q_clean and a_clean:
            faqs.append({"question": q_clean, "answer": a_clean})
    info["faqs"] = faqs

    return info


def _detect_business_type(html: str) -> str:
    """Auto-detect the most likely business type from page content."""
    html_lower = html.lower()
    best_type = "Organization"
    best_count = 0

    for btype, keywords in _BUSINESS_SIGNALS.items():
        count = sum(1 for kw in keywords if kw.lower() in html_lower)
        threshold = 3 if btype == "SoftwareApplication" else 2
        if count >= threshold and count > best_count:
            best_type = btype
            best_count = count

    return best_type


def _build_schemas(
    extracted: dict[str, Any],
    detected_type: str,
    url: str,
    base: str,
) -> list[dict[str, Any]]:
    """Build Schema JSON-LD objects from extracted info."""
    schemas = []

    # Primary entity
    entity: dict[str, Any] = {
        "@type": detected_type,
        "name": extracted["name"],
        "url": base,
    }
    if extracted.get("description"):
        entity["description"] = extracted["description"]
    if extracted.get("logo"):
        entity["logo"] = extracted["logo"]
    if extracted.get("email"):
        entity["email"] = extracted["email"]
    if extracted.get("telephone"):
        entity["telephone"] = extracted["telephone"]
    if extracted.get("sameAs"):
        entity["sameAs"] = extracted["sameAs"]

    schemas.append(entity)

    # WebSite
    schemas.append({
        "@type": "WebSite",
        "name": extracted["name"],
        "url": base,
        "inLanguage": extracted.get("language", "en"),
        "potentialAction": {
            "@type": "SearchAction",
            "target": f"{base}/search?q={{search_term_string}}",
            "query-input": "required name=search_term_string",
        },
    })

    # FAQPage if FAQs found
    if extracted.get("faqs"):
        faq_schema: dict[str, Any] = {
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": faq["question"],
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": faq["answer"],
                    },
                }
                for faq in extracted["faqs"][:10]
            ],
        }
        schemas.append(faq_schema)

    return schemas


# ---------------------------------------------------------------------------
# llms.txt Generator
# ---------------------------------------------------------------------------

def generate_llms_txt(
    url: str,
    company_name: str = "",
    description: str = "",
    services: list[str] | None = None,
) -> dict[str, Any]:
    """Generate llms.txt content for a website.

    If company_name/description/services not provided, extracts from the page.

    Returns:
        {
            "url": str,
            "content": str,           # the llms.txt content
            "word_count": int,
            "link_count": int,
            "pages_found": {...},      # categorized URLs
        }
    """
    if not url.startswith("http"):
        url = "https://" + url
    url = url.rstrip("/")
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    http = httpx.Client(
        timeout=30.0, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; GEO-Generator/1.0)"},
    )

    try:
        resp = http.get(url)
        html = resp.text if resp.status_code == 200 else ""
    except httpx.HTTPError:
        html = ""

    # Try to get sitemap for URL discovery
    sitemap_urls: list[str] = []
    try:
        sr = http.get(f"{base}/sitemap.xml")
        if sr.status_code == 200:
            sitemap_urls = re.findall(r"<loc>(.*?)</loc>", sr.text)
    except httpx.HTTPError:
        pass
    finally:
        http.close()

    # Extract info if not provided
    if not company_name or not description:
        extracted = _extract_page_info(html, url, base)
        if not company_name:
            company_name = extracted.get("name", parsed.netloc)
        if not description:
            description = extracted.get("description", "")

    # Categorize URLs
    pages = _categorize_urls(sitemap_urls, base, html)

    # Build llms.txt
    content = _build_llms_txt(
        company_name=company_name,
        description=description,
        services=services or [],
        pages=pages,
        base=base,
    )

    return {
        "url": url,
        "content": content,
        "word_count": len(content.split()),
        "link_count": content.count("](http"),
        "pages_found": {k: len(v) for k, v in pages.items()},
    }


def _categorize_urls(
    sitemap_urls: list[str],
    base: str,
    html: str,
) -> dict[str, list[dict[str, str]]]:
    """Categorize URLs into main/products/blog/docs/other."""
    categories: dict[str, list[dict[str, str]]] = {
        "main": [],
        "products": [],
        "blog": [],
        "docs": [],
        "other": [],
    }

    # Combine sitemap + page links
    page_links = re.findall(r'href=["\']([^"\'#]+)["\']', html, re.IGNORECASE)
    all_urls = set(sitemap_urls)
    domain = urlparse(base).netloc
    for link in page_links:
        if link.startswith("/"):
            all_urls.add(base + link)
        elif link.startswith("http") and domain in link:
            all_urls.add(link)

    # Filter to same domain
    for u in sorted(all_urls):
        if domain not in u:
            continue
        path = urlparse(u).path.lower()
        # Derive a title from the path
        slug = path.rstrip("/").split("/")[-1] if path.rstrip("/") else "Home"
        title = slug.replace("-", " ").replace("_", " ").title()

        entry = {"title": title, "url": u}

        if any(kw in path for kw in ["/about", "/contact", "/team", "/company"]):
            categories["main"].append(entry)
        elif path in ("/", ""):
            categories["main"].insert(0, {"title": "Homepage", "url": u})
        elif any(kw in path for kw in ["/product", "/service", "/solution", "/pricing", "/feature", "/catalog"]):
            categories["products"].append(entry)
        elif any(kw in path for kw in ["/blog", "/article", "/post", "/news", "/insight"]):
            categories["blog"].append(entry)
        elif any(kw in path for kw in ["/doc", "/guide", "/help", "/faq", "/support", "/how-to"]):
            categories["docs"].append(entry)
        else:
            categories["other"].append(entry)

    # Trim to reasonable limits
    limits = {"main": 10, "products": 20, "blog": 30, "docs": 20, "other": 10}
    for cat, limit in limits.items():
        categories[cat] = categories[cat][:limit]

    return categories


def _build_llms_txt(
    company_name: str,
    description: str,
    services: list[str],
    pages: dict[str, list[dict[str, str]]],
    base: str,
) -> str:
    """Build llms.txt content following llmstxt.org spec."""
    lines = []

    # H1 title
    lines.append(f"# {company_name}")
    lines.append("")

    # Blockquote description
    if description:
        lines.append(f"> {description}")
        lines.append("")

    # Services
    if services:
        lines.append("## Services and Products")
        lines.append("")
        for s in services:
            lines.append(f"- {s}")
        lines.append("")

    # Main pages
    if pages.get("main"):
        lines.append("## About")
        lines.append("")
        for p in pages["main"]:
            lines.append(f"- [{p['title']}]({p['url']})")
        lines.append("")

    # Products
    if pages.get("products"):
        lines.append("## Products & Services")
        lines.append("")
        for p in pages["products"]:
            lines.append(f"- [{p['title']}]({p['url']})")
        lines.append("")

    # Blog
    if pages.get("blog"):
        lines.append("## Articles & Insights")
        lines.append("")
        for p in pages["blog"]:
            lines.append(f"- [{p['title']}]({p['url']})")
        lines.append("")

    # Docs
    if pages.get("docs"):
        lines.append("## Documentation & Guides")
        lines.append("")
        for p in pages["docs"]:
            lines.append(f"- [{p['title']}]({p['url']})")
        lines.append("")

    # Contact
    lines.append("## Contact")
    lines.append("")
    lines.append(f"- Website: {base}")
    lines.append("")

    return "\n".join(lines)
