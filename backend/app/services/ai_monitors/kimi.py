"""Kimi (Moonshot AI) 查询。

🟡 cookie-based, JWT Bearer ~30 天过期。

.env 配置 (优先级从高到低):
    KIMI_API_KEY   — Moonshot 官方付费 API
    KIMI_BEARER    — www.kimi.com 抓包 authorization 头 (推荐, 单独这一项够了)
    KIMI_COOKIE    — 整段 Cookie, 程序会从 kimi-auth 里抠 JWT

实现说明:
    走 www.kimi.com 的 Connect-RPC 接口 (gRPC-Web 风格, content-type
    application/connect+json). 帧格式: [1 byte flag][4 bytes BE length][JSON].
    JWT payload 里带 device_id/ssid/sub, 自动解析作 x-msh-* / x-traffic-id 头.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import struct
from datetime import datetime
from typing import Any, Iterator

import httpx

from .base import BaseMonitor, MonitorError

logger = logging.getLogger("geo.ai_monitor.kimi")


# Connect-RPC framing helpers ------------------------------------------------

def _encode_frame(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return b"\x00" + struct.pack(">I", len(body)) + body


def _iter_frames(raw: bytes) -> Iterator[tuple[int, dict[str, Any] | bytes]]:
    i = 0
    while i + 5 <= len(raw):
        flag = raw[i]
        ln = struct.unpack(">I", raw[i + 1 : i + 5])[0]
        body = raw[i + 5 : i + 5 + ln]
        i += 5 + ln
        try:
            yield flag, json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            yield flag, body


def _decode_jwt_payload(jwt: str) -> dict[str, Any]:
    """解 JWT 第二段 (payload), 无需签名校验。"""
    try:
        part = jwt.split(".")[1]
        # base64url + padding
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part).decode("utf-8"))
    except Exception as e:
        raise MonitorError(f"Kimi JWT 解析失败: {e}") from e


def _iso_to_epoch(s: str | None) -> float | None:
    if not s:
        return None
    try:
        # Kimi 用 RFC3339 / ISO8601, 末尾 Z
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


# Kimi 正文里引用角标形如 [^3^][^5^], 转成统一的 [citation:N] 让前端复用渲染
KIMI_CITE_RE = re.compile(r"\[\^(\d+)\^\]")


def _normalize_citations(text: str) -> str:
    return KIMI_CITE_RE.sub(lambda m: f"[citation:{m.group(1)}]", text)


def _extract_bearer_from_cookie(cookie: str) -> str:
    """从整段 Cookie 字符串里抠 kimi-auth 值。"""
    for kv in cookie.split(";"):
        k, _, v = kv.strip().partition("=")
        if k == "kimi-auth":
            return v.strip()
    return ""


# Monitor --------------------------------------------------------------------


class KimiMonitor(BaseMonitor):
    platform_id = "kimi"

    CHAT_URL = "https://www.kimi.com/apiv2/kimi.gateway.chat.v1.ChatService/Chat"

    def query(
        self, question: str, *, brand_keywords: list[str] | None = None
    ) -> dict[str, Any]:
        # 1. 官方 API 最优
        api_key = self.settings.KIMI_API_KEY or ""
        if api_key:
            return self._query_api(api_key, question, brand_keywords)
        # 2. Web 抓包接口
        return self._query_web(question, brand_keywords)

    # ---------------- 官方 API ----------------

    def _query_api(
        self, api_key: str, question: str, brand_keywords: list[str] | None
    ) -> dict[str, Any]:
        try:
            resp = self.http.post(
                "https://api.moonshot.cn/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "moonshot-v1-8k",
                    "messages": [{"role": "user", "content": question}],
                    "temperature": 0.3,
                },
            )
        except httpx.HTTPError as e:
            raise MonitorError(f"Kimi API 网络错误: {e}") from e

        if resp.status_code >= 400:
            raise MonitorError(f"Kimi API {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        answer = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        ) or "(空回答)"
        analysis = self.analyze_mention(answer, brand_keywords)
        screenshot = self.save_answer_text(answer)
        return {
            **analysis,
            "raw_answer": answer,
            "screenshot_path": str(screenshot),
        }

    # ---------------- Web 抓包接口 ----------------

    def _resolve_bearer(self) -> str:
        bearer = (self.settings.KIMI_BEARER or "").strip()
        if bearer:
            return bearer
        cookie = (self.settings.KIMI_COOKIE or "").strip()
        if cookie:
            token = _extract_bearer_from_cookie(cookie)
            if token:
                return token
        raise MonitorError(
            "Kimi 未配置凭证: 请在 .env 中设置 KIMI_BEARER (推荐) 或 KIMI_COOKIE"
        )

    def _build_headers(self) -> dict[str, str]:
        bearer = self._resolve_bearer()
        claims = _decode_jwt_payload(bearer)
        device_id = str(claims.get("device_id", ""))
        ssid = str(claims.get("ssid", ""))
        traffic_id = str(claims.get("sub", ""))
        if not (device_id and ssid and traffic_id):
            raise MonitorError("Kimi JWT 缺 device_id/ssid/sub 字段, bearer 无效")
        return {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "authorization": f"Bearer {bearer}",
            "cache-control": "no-cache",
            "connect-protocol-version": "1",
            "content-type": "application/connect+json",
            "origin": "https://www.kimi.com",
            "pragma": "no-cache",
            "r-timezone": "Asia/Shanghai",
            "referer": "https://www.kimi.com/",
            "x-language": "zh-CN",
            "x-msh-device-id": device_id,
            "x-msh-platform": "web",
            "x-msh-session-id": ssid,
            "x-msh-version": "1.0.0",
            "x-traffic-id": traffic_id,
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36"
            ),
        }

    def _query_web(
        self, question: str, brand_keywords: list[str] | None
    ) -> dict[str, Any]:
        headers = self._build_headers()
        payload = {
            "scenario": "SCENARIO_K2D5",
            "tools": [{"type": "TOOL_TYPE_SEARCH", "search": {}}],
            "message": {
                "role": "user",
                "blocks": [{"message_id": "", "text": {"content": question}}],
                "scenario": "SCENARIO_K2D5",
            },
            "options": {"thinking": False},
        }

        try:
            resp = self.http.post(
                self.CHAT_URL, headers=headers, content=_encode_frame(payload)
            )
        except httpx.HTTPError as e:
            raise MonitorError(f"Kimi 网络错误: {e}") from e

        if resp.status_code >= 400:
            raise MonitorError(
                f"Kimi 请求失败 {resp.status_code} (bearer 可能过期): "
                f"{resp.text[:200]}"
            )

        chunks: list[str] = []
        err: str | None = None
        # 联网搜索结果: 同一 id 可能在 tool.contents 和 message.refs 里都出现一次,
        # 用 dict 按 id 去重并以 refs 为准 (refs 是模型最终用上的)。
        search_pool: dict[str, dict[str, Any]] = {}
        used_ids: list[str] = []  # message.refs.usedSearchChunks 顺序 = 引用编号顺序

        for flag, msg in _iter_frames(resp.content):
            if not isinstance(msg, dict):
                continue
            # 尾帧 flag=2: Connect-RPC end-stream marker; 里面可能带 error
            if flag & 0x02:
                if "error" in msg:
                    err = json.dumps(msg["error"], ensure_ascii=False)
                continue

            # --- 1. 正文 token ---
            block = msg.get("block") or {}
            text_block = block.get("text") or {}
            if text_block.get("content"):
                chunks.append(text_block["content"])

            # --- 2. tool 调用产出的搜索条目 (tool.contents 列表) ---
            tool = block.get("tool") or {}
            for item in (tool.get("contents") or []):
                sr = (item or {}).get("searchResult") or {}
                sid = str(sr.get("id") or "")
                base = sr.get("base") or {}
                if sid:
                    search_pool.setdefault(sid, base)

            # --- 3. message.refs: 召回 + 实际使用的 chunk ---
            message = msg.get("message") or {}
            refs = message.get("refs") or {}
            for chunk in (refs.get("searchChunks") or []):
                cid = str(chunk.get("id") or "")
                base = chunk.get("base") or {}
                if cid:
                    search_pool.setdefault(cid, base)
            used = refs.get("usedSearchChunks")
            if used is not None:
                used_ids = [str(c.get("id") or "") for c in used if c.get("id")]
                for chunk in used:
                    cid = str(chunk.get("id") or "")
                    base = chunk.get("base") or {}
                    if cid:
                        # 已用的优先覆盖 (字段更全)
                        search_pool[cid] = base

        if err:
            raise MonitorError(f"Kimi 返回错误: {err}")

        answer_raw = "".join(chunks).strip() or "(空回答)"
        # 把 [^N^] 角标统一为 [citation:N] (前端复用 DeepSeek 的渲染)
        answer = _normalize_citations(answer_raw)

        # 构造结构化 search_results, cite_index 与正文 [citation:N] 对齐
        # Kimi 的 used_ids 列表顺序就是模型给出的引用编号 (从 1 开始)
        ordered_ids = used_ids or sorted(search_pool.keys(), key=lambda x: int(x) if x.isdigit() else 0)
        search_results: list[dict[str, Any]] = []
        for idx, sid in enumerate(ordered_ids, start=1):
            base = search_pool.get(sid) or {}
            search_results.append(
                {
                    # Kimi 的 chunk id 本身就是 1-based 序号, 与 [^N^] 一致
                    "cite_index": int(sid) if sid.isdigit() else idx,
                    "title": base.get("title") or "",
                    "url": base.get("url") or "",
                    "snippet": base.get("snippet") or "",
                    "published_at": _iso_to_epoch(base.get("publishTime")),
                    "site_icon": base.get("iconUrl"),
                }
            )

        # 正文 + 搜索来源联合判定品牌提及 (联网平台搜索里命中也算曝光)
        analysis = self.analyze_mention_with_sources(
            answer, search_results, brand_keywords
        )

        screenshot = self.save_answer_text(answer)
        return {
            **analysis,
            "raw_answer": answer,
            "search_results": search_results,
            "screenshot_path": str(screenshot),
        }
