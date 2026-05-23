"""M5 客户管理服务层 — 标准 CRUD。

`business_info` 在 DB 内是 JSON 字符串,在 API 输出时反序列化为 dict。

创建/更新客户时会调 LLM 动态扩展 `business_info.keywords` —
根据品牌名 + 描述 + 行业自动生成别名/英文名/子品牌/常见误写, 供
M4 监测做来源和正文的关键词匹配。使用与 M2 生成文章相同的
LLM_PROVIDER 配置, mock 模式下只返回品牌名自身。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ...models import Client
from ...services.llm_client import get_llm_client
from .schemas import ClientCreate, ClientUpdate, ClientOut

logger = logging.getLogger("geo.clients")


class ClientNotFoundError(Exception):
    pass


class ClientConflictError(Exception):
    pass


# ============================================================
# LLM 自动扩展品牌关键词 (M4 监测用)
# ============================================================

_KEYWORD_PROMPT = """你是品牌关键词词库构建助手。我在做 GEO (生成式引擎优化) 监测, 需要在 AI 回答与搜索结果中判断某品牌是否被提及。现在请根据以下客户资料, 生成一组"品牌识别关键词"列表, 用于后续做字符串子串匹配。

客户资料:
- 品牌名: {name}
- 所在行业: {industry}
- 所在区域: {region}
- 品牌描述: {description}
- 用户已提供的关键词 (若有): {existing}

要求:
1. 必须包含品牌主名本身 (原样)
2. 若是中文品牌, 补充常见英文名/音译名/拼音缩写 (例: "鄂尔多斯" → "ERDOS", "Erdos")
3. 若是英文品牌, 补充常见中文译名 (例: "Nike" → "耐克")
4. 补充集团旗下知名子品牌/系列名 (例: 鄂尔多斯集团 → "1436", "BLUE ERDOS", "鄂尔多斯1980")
5. 补充常见的错别字/口语化写法 (例: "小米" → "mi", "MI", "Xiaomi")
6. 排除太宽泛的词 (例: "羊绒衫"、"手机" 这类品类词不是品牌词, 不要加)
7. 总数控制在 5-15 个, 重要的排前面
8. 每个关键词必须能在文本中作为子串直接匹配 (不用正则)

严格按以下 JSON 数组格式输出, 不要加 markdown 代码块, 不要加任何额外说明文字:
["关键词1", "关键词2", "关键词3", ...]
"""

_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")


def _parse_keyword_list(text: str) -> list[str] | None:
    """宽容解析 LLM 返回的 JSON 数组。"""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    # 1) 直接解析
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        # 2) 在文本里找第一个 [...]
        m = _JSON_ARRAY_RE.search(text)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, list):
        return None
    out: list[str] = []
    for item in data:
        if isinstance(item, str):
            s = item.strip()
            if s:
                out.append(s)
    return out or None


def _dedup_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        k = x.lower()
        if k and k not in seen:
            seen.add(k)
            out.append(x)
    return out


def expand_brand_keywords(
    *,
    name: str,
    industry: str,
    region: str,
    description: str,
    existing: list[str] | None = None,
) -> list[str]:
    """调 LLM 给品牌生成识别关键词列表。

    永不抛异常 — 失败时 fallback 到 [name] + existing.
    GEO_USE_MOCK 模式下直接走 fallback, 不产生 LLM 调用。
    """
    existing = existing or []
    fallback = _dedup_keep_order([name.strip()] + [e for e in existing if e.strip()])

    llm = get_llm_client()
    # mock client 的 generate_sync 只做模板填充, 对词库任务没意义
    if type(llm).__name__ == "MockLLMClient":
        return fallback

    prompt = _KEYWORD_PROMPT.format(
        name=name,
        industry=industry or "(未填)",
        region=region or "(未填)",
        description=description or "(未填)",
        existing=", ".join(existing) if existing else "(无)",
    )
    try:
        raw = llm.generate_sync(prompt, max_tokens=400)
    except Exception as e:  # noqa: BLE001
        logger.warning("expand_brand_keywords: LLM 调用失败, 用 fallback: %s", e)
        return fallback

    parsed = _parse_keyword_list(raw or "")
    if not parsed:
        logger.warning(
            "expand_brand_keywords: LLM 返回无法解析, 用 fallback. raw=%s",
            (raw or "")[:200],
        )
        return fallback

    merged = _dedup_keep_order([name.strip()] + existing + parsed)
    logger.info(
        "expand_brand_keywords: brand=%s → %d keywords: %s",
        name,
        len(merged),
        merged,
    )
    return merged


def _to_out(c: Client) -> ClientOut:
    try:
        bi = json.loads(c.business_info) if c.business_info else {}
        if not isinstance(bi, dict):
            bi = {}
    except json.JSONDecodeError:
        bi = {}
    return ClientOut(
        id=c.id,
        name=c.name,
        industry=c.industry,
        region=c.region,
        business_info=bi,
        plan=c.plan,
        status=c.status,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def list_clients(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> tuple[list[ClientOut], int]:
    stmt = select(Client)
    count_stmt = select(func.count()).select_from(Client)
    if status:
        stmt = stmt.where(Client.status == status)
        count_stmt = count_stmt.where(Client.status == status)
    total = db.execute(count_stmt).scalar_one()
    stmt = stmt.order_by(Client.id.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(stmt).scalars().all()
    return [_to_out(r) for r in rows], int(total)


def get_client(db: Session, client_id: int) -> ClientOut:
    c = db.get(Client, client_id)
    if not c:
        raise ClientNotFoundError(f"client {client_id} not found")
    return _to_out(c)


def get_client_or_raise(db: Session, client_id: int) -> Client:
    c = db.get(Client, client_id)
    if not c:
        raise ClientNotFoundError(f"client {client_id} not found")
    return c


def _normalize_keywords_list(
    bi: dict[str, Any], name: str
) -> list[str]:
    """清洗 business_info.keywords → 去空去重保序, 保证品牌主名一定在里面."""
    raw = bi.get("keywords") or []
    if not isinstance(raw, list):
        raw = []
    cleaned = [str(k).strip() for k in raw if str(k).strip()]
    return _dedup_keep_order([name.strip()] + cleaned)


def _apply_keywords(
    body_bi: dict[str, Any],
    *,
    name: str,
    industry: str,
    region: str,
    auto_expand: bool,
) -> dict[str, Any]:
    """根据 auto_expand 决定是否调 LLM 扩展关键词.

    - auto_expand=True: 以用户提供的 keywords + 品牌名为种子, 调 LLM 扩展, 合并去重
    - auto_expand=False: 只清洗用户提供的 keywords (去空去重, 补上品牌名保底),
      不调 LLM. 用户手动删掉的关键词不会被 LLM 加回来.
    """
    bi = dict(body_bi or {})
    user_keywords = _normalize_keywords_list(bi, name)

    if auto_expand:
        merged = expand_brand_keywords(
            name=name,
            industry=industry,
            region=region,
            description=str(bi.get("description") or ""),
            existing=user_keywords,
        )
        bi["keywords"] = merged
    else:
        bi["keywords"] = user_keywords
    return bi


def create_client(db: Session, body: ClientCreate) -> ClientOut:
    # 唯一性: name+region
    existing = db.execute(
        select(Client).where(Client.name == body.name, Client.region == body.region)
    ).scalar_one_or_none()
    if existing:
        raise ClientConflictError(
            f"client with name={body.name} region={body.region} already exists"
        )

    # 新建客户: 默认自动扩展 (auto_expand_keywords 默认 True)
    bi = _apply_keywords(
        body.business_info or {},
        name=body.name,
        industry=body.industry,
        region=body.region,
        auto_expand=body.auto_expand_keywords,
    )

    c = Client(
        name=body.name,
        industry=body.industry,
        region=body.region,
        business_info=json.dumps(bi, ensure_ascii=False),
        plan=body.plan or "basic",
        status=body.status or "active",
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _to_out(c)


def update_client(db: Session, client_id: int, body: ClientUpdate) -> ClientOut:
    c = get_client_or_raise(db, client_id)
    data = body.model_dump(exclude_unset=True)
    # 默认: 更新时不触发 LLM 扩展, 严格按用户提交的 keywords 保存.
    # 用户想重跑时, 要么显式传 auto_expand_keywords=True, 要么调
    # POST /clients/{id}/regenerate-keywords.
    want_expand = bool(data.pop("auto_expand_keywords", None))

    if "business_info" in data and data["business_info"] is not None:
        new_bi = _apply_keywords(
            data.pop("business_info") or {},
            name=data.get("name") or c.name,
            industry=data.get("industry") or c.industry,
            region=data.get("region") or c.region,
            auto_expand=want_expand,
        )
        c.business_info = json.dumps(new_bi, ensure_ascii=False)
    for k, v in data.items():
        if v is not None:
            setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return _to_out(c)


def regenerate_keywords(db: Session, client_id: int) -> ClientOut:
    """强制重跑 LLM 扩展客户的 business_info.keywords (忽略当前已有列表)。

    用于: 修改了描述后想刷新词库, 或已有客户首次接入 LLM 扩展逻辑。
    """
    c = get_client_or_raise(db, client_id)
    try:
        bi = json.loads(c.business_info) if c.business_info else {}
        if not isinstance(bi, dict):
            bi = {}
    except json.JSONDecodeError:
        bi = {}
    merged = expand_brand_keywords(
        name=c.name,
        industry=c.industry,
        region=c.region,
        description=str(bi.get("description") or ""),
        existing=[],  # 忽略已有, 让 LLM 全新生成
    )
    bi["keywords"] = merged
    c.business_info = json.dumps(bi, ensure_ascii=False)
    db.commit()
    db.refresh(c)
    return _to_out(c)


def delete_client(db: Session, client_id: int) -> dict[str, Any]:
    c = get_client_or_raise(db, client_id)
    db.delete(c)
    db.commit()
    return {"deleted": True, "id": client_id}
