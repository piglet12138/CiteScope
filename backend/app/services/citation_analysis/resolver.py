"""异步 URL redirect 解析。

主要用于 Gemini 的 `vertexaisearch.cloud.google.com/grounding-api-redirect/*`
这种平台 wrapper 必须 follow 才能拿到真实落地域名。其他 URL 走也无害 ——
顺便清掉 utm_*。

设计:
- 单进程 asyncio + Semaphore 限并发 (默认 20)
- 每个 URL 5 跳上限,10s 超时
- 输入去重 (同一批里多次出现同一 raw_url 只调一次)
- HEAD 不可靠所以直接 GET,但只读 first response (httpx 自动 follow)
- 失败不抛异常,返回 error message 给调用方决定怎么标 resolve_status

不持久化缓存:解析结果直接落到 monitor_citations.resolved_url,自然就是
"持久化缓存"。短期重复在同一批 backfill 里去重就够。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Iterable

import httpx

from .normalizer import clean_url

logger = logging.getLogger("geo.citation.resolver")


async def _resolve_one(
    client: httpx.AsyncClient, raw_url: str
) -> tuple[str | None, str | None]:
    """Returns (resolved_url, error_str)。失败时 resolved_url=None。"""
    if not raw_url:
        return None, "empty url"
    try:
        # GET (httpx 默认会 follow_redirects 如果 client 配置了),只读 final URL
        resp = await client.get(raw_url)
        final = str(resp.url)
        # 清掉 utm_* / fbclid 等 tracking 参数
        return clean_url(final), None
    except httpx.TimeoutException:
        return None, "timeout"
    except httpx.TooManyRedirects:
        return None, "too_many_redirects"
    except httpx.HTTPError as e:
        return None, f"http_error:{type(e).__name__}"
    except Exception as e:  # noqa: BLE001
        return None, f"unknown:{type(e).__name__}:{str(e)[:120]}"


async def resolve_batch(
    raw_urls: Iterable[str],
    *,
    concurrency: int = 20,
    timeout: float = 10.0,
    max_redirects: int = 5,
    user_agent: str = "Mozilla/5.0 (compatible; CiteScope-Citation-Resolver/1.0)",
) -> dict[str, tuple[str | None, str | None]]:
    """批量解析。返回 {raw_url: (resolved_url, error)}。

    同一批内自动去重。一些站点对 HEAD 不友好,这里直接 GET。
    """
    unique = list({u for u in raw_urls if u})
    if not unique:
        return {}

    sem = asyncio.Semaphore(concurrency)
    results: dict[str, tuple[str | None, str | None]] = {}

    headers = {"User-Agent": user_agent}
    limits = httpx.Limits(max_connections=concurrency * 2)

    async with httpx.AsyncClient(
        follow_redirects=True,
        max_redirects=max_redirects,
        timeout=timeout,
        headers=headers,
        limits=limits,
        verify=False,  # 允许自签证书,某些 vendor 站点凭证不齐
    ) as client:
        async def _job(url: str):
            async with sem:
                results[url] = await _resolve_one(client, url)

        await asyncio.gather(*[_job(u) for u in unique], return_exceptions=False)

    return results


def resolve_batch_sync(
    raw_urls: Iterable[str],
    *,
    concurrency: int = 20,
    timeout: float = 10.0,
) -> dict[str, tuple[str | None, str | None]]:
    """Sync 封装,从普通函数(如 apscheduler job)里直接调。"""
    return asyncio.run(
        resolve_batch(raw_urls, concurrency=concurrency, timeout=timeout)
    )
