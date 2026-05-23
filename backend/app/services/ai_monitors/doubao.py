"""豆包 AI 监测 — 火山方舟 Ark Responses API + 内置 web_search 工具。

历史:
- 早期走 www.doubao.com 网页 cookie + mssdk 反爬 → 海外 IP 被区域拦,改 mock
- 2026-05 重写:改走火山方舟官方 Responses API,web_search 是平台 builtin tool,
  单轮即可拿到带 url_citation annotations 的最终答案

Config (在 [系统配置] 页填):
- ARK_API_KEY     — 火山方舟控制台创建,Bearer 直接用
- DOUBAO_MODEL    — endpoint id,默认 doubao-seed-1-6-250615
- ARK_API_BASE    — 默认 https://ark.cn-beijing.volces.com/api/v3

调用:POST {base}/responses, body {model, input, tools:[{type:"web_search"}], stream:false}
返回:`output[]` 数组,找 type=="message" 的元素,content[].annotations[] 即 citation。

Mock 实现保留在 doubao_browser.py / 历史 git。新版本不再降级到 mock,
没配 ARK_API_KEY 直接抛 MonitorError。
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import BaseMonitor, MonitorError

logger = logging.getLogger("geo.ai_monitor.doubao")


class DoubaoMonitor(BaseMonitor):
    platform_id = "doubao"
    timeout = 90.0  # web_search 多轮爬可能比较慢

    def query(
        self, question: str, *, brand_keywords: list[str] | None = None
    ) -> dict[str, Any]:
        api_key = (self.settings.ARK_API_KEY or "").strip()
        if not api_key:
            raise MonitorError(
                "ARK_API_KEY not configured (火山方舟 API key,在控制台 → 方舟 → API Key 管理 创建)"
            )

        base = (self.settings.ARK_API_BASE or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
        model = self.settings.DOUBAO_MODEL or "doubao-seed-1-6-250615"

        body: dict[str, Any] = {
            "model": model,
            "input": [
                {"role": "user", "content": question},
            ],
            "tools": [{"type": "web_search"}],
            "stream": False,
        }

        try:
            resp = self.http.post(
                f"{base}/responses",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise MonitorError(f"Doubao Ark network error: {e}") from e

        if resp.status_code >= 400:
            raise MonitorError(
                f"Doubao Ark API {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()

        # ---------- 解析 output[] 数组 ----------
        # 结构 (Responses API):
        #   output: [
        #     { type:"web_search_call", ... },     # 执行记录,不含正文
        #     { type:"message", content:[
        #         { type:"output_text", text:"...", annotations:[
        #             { type:"url_citation", url, title, start_index, end_index }
        #         ] }
        #     ] }
        #   ]
        answer_parts: list[str] = []
        annotations_all: list[dict[str, Any]] = []
        for item in data.get("output", []) or []:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content_part in item.get("content", []) or []:
                if not isinstance(content_part, dict):
                    continue
                text = content_part.get("text") or ""
                if text:
                    answer_parts.append(text)
                for a in content_part.get("annotations", []) or []:
                    if isinstance(a, dict) and a.get("type") == "url_citation":
                        annotations_all.append(a)

        answer = "".join(answer_parts).strip() or "(empty response)"

        # 把 [citation:N] 标记插回正文,让 span_attribution 能跑
        search_results: list[dict[str, Any]] | None = None
        if annotations_all:
            # 按出现顺序分配 1-based cite_index
            search_results = []
            for idx, a in enumerate(annotations_all, 1):
                search_results.append(
                    {
                        "cite_index": idx,
                        "title": a.get("title", "") or "",
                        "url": a.get("url", "") or "",
                        "snippet": a.get("snippet", "") or "",
                    }
                )

            # 插标记:按 end_index 倒序插,后插的不会移位前面的索引
            marker_inserts = [
                (a.get("end_index"), idx)
                for idx, a in enumerate(annotations_all, 1)
                if isinstance(a.get("end_index"), int)
            ]
            marker_inserts.sort(key=lambda x: x[0], reverse=True)
            for pos, idx in marker_inserts:
                if pos is None or pos < 0 or pos > len(answer):
                    continue
                answer = answer[:pos] + f"[citation:{idx}]" + answer[pos:]

        # ---------- mention 判定 ----------
        if search_results:
            analysis = self.analyze_mention_with_sources(answer, search_results, brand_keywords)
        else:
            analysis = self.analyze_mention(answer, brand_keywords)

        screenshot = self.save_answer_text(answer)

        # ---------- usage(Responses API 字段名是 input_tokens/output_tokens)----------
        usage = data.get("usage") or {}
        return {
            **analysis,
            "raw_answer": answer,
            "search_results": search_results,
            "screenshot_path": str(screenshot),
            "usage": {
                "model": model,
                "prompt_tokens": int(
                    usage.get("input_tokens") or usage.get("prompt_tokens") or 0
                ),
                "completion_tokens": int(
                    usage.get("output_tokens") or usage.get("completion_tokens") or 0
                ),
            },
        }
