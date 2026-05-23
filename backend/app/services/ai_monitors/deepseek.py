"""DeepSeek (chat.deepseek.com) AI 监测查询。

🟡 refresh_token-based, 看上去基本不过期 (账号级 token, 与 cookie 不同)。

.env / 设置中心:
    DEEPSEEK_REFRESH_TOKEN=...

实现要点 (基于 references/deepseek-free-api 逆向 + 实测验证):

1. 用 refresh_token 通过 `GET /api/v0/users/current` 拿到 access_token,
   有效期 1 小时, 缓存复用避免频繁刷新。
2. 调 `POST /api/v0/chat_session/create` 创建会话。
3. 调 `POST /api/v0/chat/create_pow_challenge` 拿 POW (Proof of Work) challenge,
   返回 {algorithm, challenge, salt, difficulty, expire_at, signature}。
4. 调 WASM 求解器 (deepseek_pow.wasm 是 DeepSeek 自家的 SHA-3/Keccak hashcash POW,
   实测 30-300ms 返回 answer; 纯 Python SHA-256 brute force ❌不工作❌, 因为算法
   是 hashcash 而不是 hash equality):
       wasm_solve(retptr, challenge_ptr, salt_expire_prefix_ptr, difficulty) → answer (f64)
5. 把解 base64 编码到 `X-Ds-Pow-Response` header。
6. 调 `POST /api/v0/chat/completion` 拿 SSE 流, 设置 search_enabled=True 让其联网。
7. 从 SSE 流中过滤 delta.type:
       - "thinking" → 推理内容 (跳过)
       - "search_result" → 累积搜索来源
       - 其它 (默认) → 累积正文 content
   遇到 finish_reason=="stop" 结束。

参考: references/deepseek-free-api/src/api/controllers/chat.ts
      references/deepseek-free-api/src/lib/challenge.ts
"""
from __future__ import annotations

import base64
import ctypes
import json
import logging
import struct
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from .base import BaseMonitor, MonitorError

logger = logging.getLogger("geo.ai_monitor.deepseek")

BASE_URL = "https://chat.deepseek.com"

# 与浏览器一致的伪装 headers (照搬 free-api 验证过的版本)
FAKE_HEADERS = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": BASE_URL,
    "Pragma": "no-cache",
    "Priority": "u=1, i",
    "Referer": f"{BASE_URL}/",
    "Sec-Ch-Ua": '"Chromium";v="133", "Google Chrome";v="133", "Not?A_Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    ),
    "X-App-Version": "20241129.1",
    "X-Client-Locale": "zh-CN",
    "X-Client-Platform": "web",
    "X-Client-Version": "1.0.0-always",
    "X-Client-Timezone-Offset": "28800",
}

ACCESS_TOKEN_TTL = 3600  # 1 小时

WASM_PATH = Path(__file__).parent / "deepseek_pow.wasm"


# ============================================================
# Token 缓存 (进程级, 跨实例共享)
# ============================================================

_token_lock = threading.Lock()
_token_cache: dict[str, tuple[str, float]] = {}  # refresh_token -> (access_token, expires_at)


# ============================================================
# WASM POW 求解器 (单例, 加锁串行 — wasmtime Store 不是线程安全的)
# ============================================================

_wasm_lock = threading.Lock()
_wasm_state: dict[str, Any] | None = None


def _load_wasm() -> dict[str, Any]:
    """惰性加载 WASM 模块, 全进程单例。返回 dict 包含 store/exports/memory 等。"""
    global _wasm_state
    if _wasm_state is not None:
        return _wasm_state
    try:
        import wasmtime  # type: ignore
    except ImportError as e:
        raise MonitorError(
            "DeepSeek POW 需要 wasmtime: pip install wasmtime"
        ) from e
    if not WASM_PATH.exists():
        raise MonitorError(f"DeepSeek POW WASM 文件缺失: {WASM_PATH}")

    engine = wasmtime.Engine()
    store = wasmtime.Store(engine)
    module = wasmtime.Module(engine, WASM_PATH.read_bytes())
    instance = wasmtime.Instance(store, module, [])
    exports = instance.exports(store)
    _wasm_state = {
        "store": store,
        "memory": exports["memory"],
        "wasm_solve": exports["wasm_solve"],
        "add_sp": exports["__wbindgen_add_to_stack_pointer"],
        "malloc": exports["__wbindgen_export_0"],
    }
    logger.info("DeepSeek POW WASM loaded: %s", WASM_PATH.name)
    return _wasm_state


def solve_pow(challenge: str, salt: str, expire_at: int, difficulty: int) -> int:
    """调 WASM 求解 DeepSeekHashV1 POW.

    实测算法是 SHA-3/Keccak hashcash, 纯 Python brute force 不可行 (会找不到答案)。
    使用 deepseek 自家的 sha3_wasm_bg.wasm 通过 wasmtime 调用。
    """
    with _wasm_lock:
        state = _load_wasm()
        store = state["store"]
        memory = state["memory"]
        wasm_solve_fn = state["wasm_solve"]
        add_sp = state["add_sp"]
        malloc = state["malloc"]

        prefix = f"{salt}_{expire_at}_"

        # 1. 在 WASM 栈上分配 16 字节 (i32 status + padding + f64 value)
        retptr = add_sp(store, -16)
        try:
            # 2. 写两个字符串到 WASM 线性内存
            base_addr = ctypes.addressof(memory.data_ptr(store).contents)

            def write_str(s: str) -> tuple[int, int]:
                b = s.encode("utf-8")
                ptr = malloc(store, len(b), 1)
                # 注意: malloc 后 memory 可能 grow, 需要重新读 base
                nonlocal base_addr
                base_addr = ctypes.addressof(memory.data_ptr(store).contents)
                ctypes.memmove(base_addr + ptr, b, len(b))
                return ptr, len(b)

            ptr0, len0 = write_str(challenge)
            ptr1, len1 = write_str(prefix)

            # 3. 调用 wasm_solve
            wasm_solve_fn(store, retptr, ptr0, len0, ptr1, len1, float(difficulty))

            # 4. 读取结果 — 先 refresh base (solve 内部可能也 grow 内存)
            base_addr = ctypes.addressof(memory.data_ptr(store).contents)
            raw = bytes((ctypes.c_ubyte * 16).from_address(base_addr + retptr))
            status = struct.unpack("<i", raw[0:4])[0]
            value = struct.unpack("<d", raw[8:16])[0]
        finally:
            add_sp(store, 16)

        if status == 0:
            raise MonitorError(
                f"DeepSeek POW WASM 返回失败: challenge={challenge[:12]}... "
                f"difficulty={difficulty} expire_at={expire_at}"
            )
        return int(value)


class DeepSeekMonitor(BaseMonitor):
    platform_id = "deepseek"
    timeout = 120.0  # SSE 流式可能 1-2 分钟

    def query(
        self, question: str, *, brand_keywords: list[str] | None = None
    ) -> dict[str, Any]:
        refresh_token = (self.settings.DEEPSEEK_REFRESH_TOKEN or "").strip()
        if not refresh_token:
            raise MonitorError(
                "DeepSeek refresh_token 未配置: 设置中心 → AI 监测平台 → DeepSeek Refresh Token"
            )

        access_token = self._acquire_access_token(refresh_token)
        session_id = self._create_session(access_token)
        challenge_payload = self._get_pow_challenge(access_token, "/api/v0/chat/completion")
        pow_response = self._build_pow_response(challenge_payload, "/api/v0/chat/completion")
        answer_text, search_results = self._stream_completion(
            access_token=access_token,
            session_id=session_id,
            prompt=question,
            pow_response=pow_response,
        )

        # answer_text 中保留 [citation:N] 占位符, 由前端配合 search_results 渲染为 [N] 角标。
        # 正文 + 搜索来源联合判定, 来源里命中品牌也算曝光 (避免"结果提到了但答案没复述"的漏判)
        analysis = self.analyze_mention_with_sources(
            answer_text, search_results, brand_keywords
        )
        screenshot = self.save_answer_text(answer_text)
        return {
            **analysis,
            "raw_answer": answer_text,
            "search_results": search_results,  # list[dict] 或 [] (本次未联网)
            "screenshot_path": str(screenshot),
        }

    # ------------------------------------------------------------
    # Step 1: refresh_token → access_token (cached)
    # ------------------------------------------------------------

    def _acquire_access_token(self, refresh_token: str) -> str:
        now = time.time()
        with _token_lock:
            cached = _token_cache.get(refresh_token)
            if cached and cached[1] > now + 60:
                return cached[0]

        # 缓存外发请求, 不持锁 (避免阻塞其它 refresh_token)
        try:
            resp = self.http.get(
                f"{BASE_URL}/api/v0/users/current",
                headers={
                    "Authorization": f"Bearer {refresh_token}",
                    **FAKE_HEADERS,
                },
            )
        except httpx.HTTPError as e:
            raise MonitorError(f"DeepSeek 刷新 token 网络错误: {e}") from e

        if resp.status_code >= 400:
            raise MonitorError(
                f"DeepSeek 刷新 token 失败 {resp.status_code}: {resp.text[:200]}"
            )
        body = resp.json()
        if body.get("code") != 0:
            raise MonitorError(
                f"DeepSeek refresh_token 校验失败: {body.get('msg') or body}"
            )
        token = (body.get("data") or {}).get("biz_data", {}).get("token") or body.get(
            "data", {}
        ).get("token")
        if not token:
            # 兼容 free-api 的解析路径: data.token
            token = body.get("token")
        if not token:
            raise MonitorError(f"DeepSeek 响应中未找到 access_token: {body}")

        with _token_lock:
            _token_cache[refresh_token] = (token, now + ACCESS_TOKEN_TTL)
        return token

    # ------------------------------------------------------------
    # Step 2: create chat session
    # ------------------------------------------------------------

    def _create_session(self, access_token: str) -> str:
        try:
            resp = self.http.post(
                f"{BASE_URL}/api/v0/chat_session/create",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    **FAKE_HEADERS,
                },
                json={"character_id": None},
            )
        except httpx.HTTPError as e:
            raise MonitorError(f"DeepSeek 创建会话网络错误: {e}") from e

        if resp.status_code >= 400:
            raise MonitorError(
                f"DeepSeek 创建会话 HTTP {resp.status_code}: {resp.text[:200]}"
            )
        body = resp.json()
        if body.get("code") != 0:
            raise MonitorError(f"DeepSeek 创建会话失败: {body.get('msg') or body}")
        biz_data = (body.get("data") or {}).get("biz_data") or body.get("biz_data")
        if not biz_data or not biz_data.get("id"):
            raise MonitorError(f"DeepSeek 会话响应缺 biz_data.id: {body}")
        return biz_data["id"]

    # ------------------------------------------------------------
    # Step 3: POW challenge → solve → base64
    # ------------------------------------------------------------

    def _get_pow_challenge(self, access_token: str, target_path: str) -> dict[str, Any]:
        try:
            resp = self.http.post(
                f"{BASE_URL}/api/v0/chat/create_pow_challenge",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    **FAKE_HEADERS,
                },
                json={"target_path": target_path},
            )
        except httpx.HTTPError as e:
            raise MonitorError(f"DeepSeek 拉 POW 网络错误: {e}") from e

        if resp.status_code >= 400:
            raise MonitorError(
                f"DeepSeek POW HTTP {resp.status_code}: {resp.text[:200]}"
            )
        body = resp.json()
        if body.get("code") != 0:
            raise MonitorError(f"DeepSeek POW 接口报错: {body.get('msg') or body}")
        biz_data = (body.get("data") or {}).get("biz_data") or body.get("biz_data")
        if not biz_data or "challenge" not in biz_data:
            raise MonitorError(f"DeepSeek POW 响应缺 biz_data.challenge: {body}")
        return biz_data["challenge"]

    def _build_pow_response(
        self, challenge: dict[str, Any], target_path: str
    ) -> str:
        algorithm = challenge.get("algorithm")
        if algorithm != "DeepSeekHashV1":
            raise MonitorError(f"未知 POW 算法: {algorithm}")

        salt = challenge["salt"]
        expire_at = int(challenge["expire_at"])
        difficulty = int(challenge["difficulty"])
        challenge_hash = challenge["challenge"]
        signature = challenge["signature"]

        t0 = time.time()
        answer = solve_pow(challenge_hash, salt, expire_at, difficulty)
        cost_ms = int((time.time() - t0) * 1000)
        logger.info(
            "DeepSeek POW solved: difficulty=%s answer=%s cost=%sms",
            difficulty,
            answer,
            cost_ms,
        )

        payload = {
            "algorithm": algorithm,
            "challenge": challenge_hash,
            "salt": salt,
            "answer": answer,
            "signature": signature,
            "target_path": target_path,
        }
        return base64.b64encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")

    # ------------------------------------------------------------
    # Step 4: SSE stream completion
    # ------------------------------------------------------------

    def _stream_completion(
        self,
        access_token: str,
        session_id: str,
        prompt: str,
        pow_response: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        """SSE 解析 (DeepSeek 实际格式, 与 free-api 文档不同)。

        实测 SSE 格式是 JSON-patch 风格:
            data: {"v": {"response": {...full initial state...}}}      # 首个事件: 初始状态
            data: {"p":"response/search_status","v":"SEARCHING"}         # 字段 SET
            data: {"p":"response/search_results","v":[{...},{...}]}      # 搜索结果 (可选)
            data: {"p":"response/content","o":"APPEND","v":"GEO"}        # 开始向 content 追加
            data: {"v":"**"}                                              # 继续追加到 content
            data: {"v":" is"}                                             # 继续追加
            ...
            data: {"p":"response/status","v":"FINISHED"}                 # 结束信号

        SSE event line ("event: ready" / "event: finish" / ...) 我们忽略,
        只看 data: 。

        返回:
            (answer_text_with_citation_markers, search_results_structured)

        answer_text 保留原始 [citation:N] 标记, 前端配合 search_results 渲染。
        search_results 每项结构:
            {cite_index: int, title: str, url: str, snippet: str, published_at: float | None,
             site_icon: str | None}
        """
        url = f"{BASE_URL}/api/v0/chat/completion"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Ds-Pow-Response": pow_response,
            **FAKE_HEADERS,
        }
        body = {
            "chat_session_id": session_id,
            "parent_message_id": None,
            "prompt": prompt,
            "ref_file_ids": [],
            "search_enabled": True,    # 关键: 联网搜索, 否则 GEO 监测意义不大
            "thinking_enabled": False,
        }

        content_parts: list[str] = []
        search_results: list[dict[str, Any]] = []
        active_append_path: str | None = None  # 当前 bare {"v":...} 应该 append 到哪个字段
        finished = False

        try:
            with self.http.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code >= 400:
                    raw = resp.read().decode("utf-8", errors="replace")[:300]
                    raise MonitorError(
                        f"DeepSeek 完成接口 HTTP {resp.status_code}: {raw}"
                    )
                ct = resp.headers.get("content-type", "")
                if "text/event-stream" not in ct:
                    raw = resp.read().decode("utf-8", errors="replace")[:300]
                    raise MonitorError(
                        f"DeepSeek 完成接口非 SSE (content-type={ct}): {raw}"
                    )

                for line in resp.iter_lines():
                    if not line:
                        continue
                    # SSE: 跳过 "event: xxx" 行 (只看 data:)
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload:
                        continue
                    try:
                        evt = json.loads(payload)
                    except json.JSONDecodeError:
                        logger.debug("DeepSeek SSE 非 JSON: %s", payload[:120])
                        continue

                    p = evt.get("p")  # 路径, 可能为 None (continuation)
                    v = evt.get("v")
                    op = evt.get("o")  # APPEND / SET / None

                    # --- 1. 带路径的事件 ---
                    if p:
                        if p == "response/content":
                            # 开始 / 重置正文 append 目标
                            if op == "APPEND":
                                active_append_path = "content"
                                if isinstance(v, str):
                                    content_parts.append(v)
                            elif isinstance(v, str):
                                # SET 完整内容 (罕见, 但保险起见处理)
                                content_parts = [v]
                                active_append_path = "content"
                        elif p == "response/search_results":
                            # 一次性给出全部搜索结果, 保留 cite_index 与正文 [citation:N] 对齐
                            if isinstance(v, list):
                                for item in v:
                                    if not isinstance(item, dict):
                                        continue
                                    search_results.append(
                                        {
                                            "cite_index": item.get("cite_index"),
                                            "title": item.get("title") or "",
                                            "url": item.get("url") or "",
                                            "snippet": item.get("snippet") or "",
                                            "published_at": item.get("published_at"),
                                            "site_icon": item.get("site_icon"),
                                        }
                                    )
                        elif p == "response/status":
                            if v in ("FINISHED", "ERROR", "STOPPED"):
                                finished = True
                        # 其它 p (search_status / accumulated_token_usage / ...) 忽略
                        continue

                    # --- 2. bare {"v": ...} (没有 p): continuation 或初始状态 ---
                    if isinstance(v, dict):
                        # 初始状态 dict, 形如 {"response": {...}}
                        # 我们目前不需要它的字段, 略过
                        continue
                    if isinstance(v, str) and active_append_path == "content":
                        content_parts.append(v)

                    if finished:
                        break
        except httpx.HTTPError as e:
            raise MonitorError(f"DeepSeek SSE 网络错误: {e}") from e

        # 保留 [citation:N] 占位符 (前端会替换为可点击的 [N] 角标)
        full = "".join(content_parts).strip()
        if not full:
            full = "(空回答)"
        return full, search_results
