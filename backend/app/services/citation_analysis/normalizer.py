"""URL → 标准化域名。

注意 tldextract 5.x 里 `registered_domain` 已经 deprecated,统一用
`top_domain_under_public_suffix`(没有这个属性的旧版回退到 registered_domain)。

已知 redirect / 包装 URL 的特殊处理:
- `vertexaisearch.cloud.google.com/grounding-api-redirect/*` (Gemini)
  这种必须 follow_redirects 才能拿到真实落地域名,本模块只做识别,
  实际解析由 resolver.py 异步完成。
- `google.com/maps/search/<query>?utm_source=openai` (ChatGPT web search 占位)
  本质上是 ChatGPT 给的"搜索意图"占位 URL,而不是真正引用了 google maps,
  本模块识别后归为 platform-internal 域,不计入聚合。
"""
from __future__ import annotations

from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import tldextract

# tldextract Extract 实例:禁用 suffix 列表更新,避免运行时联网
_extractor = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


_TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "ref_url",
}

# 这些 host 是 AI 自己的 wrapper / 重定向,而不是真实引用
PLATFORM_INTERNAL_HOSTS = {
    "vertexaisearch.cloud.google.com",  # Gemini grounding redirect
    "www.google.com/maps",  # ChatGPT 给的搜索占位
    "google.com/maps",
}

# 这些是 redirect 包装,resolver 需要 follow
REDIRECT_WRAPPER_HOSTS = {
    "vertexaisearch.cloud.google.com",
}


def is_redirect_wrapper(url: str) -> bool:
    """判断 URL 是否是已知的 platform redirect wrapper(需要 follow)。"""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return False
    return host in REDIRECT_WRAPPER_HOSTS


def is_platform_internal(url: str) -> bool:
    """判断 URL 是否是 platform 自己的占位/wrapper,不计入域名聚合。

    注意:redirect wrapper 在 resolved 之前是 platform_internal,resolved
    之后会拿到真实 host 就不是了。本判定基于 *已知的* AI 自包装 host。
    """
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return False
    host = parsed.netloc.lower()
    if host in PLATFORM_INTERNAL_HOSTS:
        return True
    # google.com/maps/search 形式
    if host in {"www.google.com", "google.com"} and parsed.path.startswith("/maps"):
        return True
    return False


def clean_url(url: str) -> str:
    """去掉 utm_*/fbclid/gclid 等跟踪参数,保留其他 query。

    用于 resolved_url 入库前的最后一步清洗,避免相同页面因 utm 不同被
    当作两条 citation。
    """
    if not url:
        return url
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return url
    if not parsed.query:
        return url
    kept = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_QUERY_KEYS
    ]
    new_query = urlencode(kept)
    return urlunparse(parsed._replace(query=new_query))


def extract_domain(url: str) -> str | None:
    """抽 registered_domain (含 ccTLD,如 ynet.co.il / bbc.co.uk),小写。

    PLATFORM_INTERNAL_HOSTS 返回 None,让上游知道不要计入聚合。
    """
    if not url:
        return None
    if is_platform_internal(url):
        return None
    try:
        ext = _extractor(url)
    except Exception:  # noqa: BLE001
        return None
    # 5.x 推荐属性
    dom = getattr(ext, "top_domain_under_public_suffix", None) or ext.registered_domain
    if not dom:
        return None
    return dom.lower()
