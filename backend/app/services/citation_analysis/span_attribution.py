"""判定哪些 citation 真正"支撑"了品牌提及那一段话。

思路:raw_answer 里有形如 `[citation:N]` 的标记,N 对应 search_results 里的
cite_index。如果一个 citation 的 marker 出现在和某个品牌关键词同一个**句子**里
(以 . ! ? 。!? 切分),就视为该 citation 支撑了那次品牌提及。

为什么用句子而不是固定字符窗口:AI 回答常常是"品牌 X 在 ... [citation:1]"
紧贴一个句子,跨句的 marker 往往是支撑相邻论点的,不应误判。同时句子边界在
中英文混排里比固定 char window 鲁棒。
"""
from __future__ import annotations

import re

# 句子分隔符:
#  - 英文标点 .!? 后跟空白 → split
#  - 英文标点 .!? 后紧贴一个 CJK 字符(中英混排,无空格)→ split
#  - 中文标点 。!? 后零宽 split (中文句子之间通常无空格)
#  - 换行 → split
_SENT_SPLIT = re.compile(
    r"(?<=[.!?])(?:\s+|(?=[一-鿿]))|(?<=[。!?])|\n+"
)
_CITATION_MARKER = re.compile(r"\[citation:(\d+)\]")


def _iter_sentence_spans(text: str):
    """yield (start, end, sentence_text) 三元组,覆盖整段 text。"""
    if not text:
        return
    cursor = 0
    for m in _SENT_SPLIT.finditer(text):
        end = m.start()
        yield cursor, end, text[cursor:end]
        cursor = m.end()
    if cursor < len(text):
        yield cursor, len(text), text[cursor:]


def compute_supports_brand_mention(
    raw_answer: str,
    brand_keywords: list[str],
    cite_indices: list[int],
) -> dict[int, bool]:
    """对每个 cite_index 判断是否支撑了品牌提及。

    Args:
        raw_answer: AI 的完整回答(含 `[citation:N]` 标记)
        brand_keywords: 品牌名 + 别名列表,大小写不敏感匹配
        cite_indices: 当前 MonitorResult 的所有 cite_index 集合(去重)

    Returns:
        {cite_index: True/False}。如果 raw_answer 为空或没有任何品牌词
        命中,所有 cite_index 都返回 False。如果 cite_indices 里某个 N
        在 raw_answer 中找不到 `[citation:N]` 标记,也返回 False
        (说明 AI 给了 search_results 但没在文里引用它)。
    """
    if not raw_answer or not brand_keywords or not cite_indices:
        return {n: False for n in cite_indices}

    # 1) 找所有品牌关键词出现的 char 区间 (大小写不敏感)
    brand_spans: list[tuple[int, int]] = []
    lower = raw_answer.lower()
    for kw in brand_keywords:
        k = (kw or "").strip().lower()
        if not k:
            continue
        start = 0
        while True:
            idx = lower.find(k, start)
            if idx < 0:
                break
            brand_spans.append((idx, idx + len(k)))
            start = idx + len(k)

    if not brand_spans:
        return {n: False for n in cite_indices}

    # 2) 找所有 [citation:N] marker 的位置,按 N 分组
    markers_by_n: dict[int, list[tuple[int, int]]] = {}
    for m in _CITATION_MARKER.finditer(raw_answer):
        try:
            n = int(m.group(1))
        except (ValueError, TypeError):
            continue
        markers_by_n.setdefault(n, []).append((m.start(), m.end()))

    # 3) 按句子切分,每个句子查:既包含某个 brand_span 又包含某个 marker → 该 N = True
    supported: set[int] = set()
    for s, e, _ in _iter_sentence_spans(raw_answer):
        has_brand = any(bs < e and be > s for bs, be in brand_spans)
        if not has_brand:
            continue
        for n, ms in markers_by_n.items():
            if any(ms_s < e and ms_e > s for ms_s, ms_e in ms):
                supported.add(n)

    return {n: (n in supported) for n in cite_indices}
