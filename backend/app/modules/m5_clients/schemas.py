"""M5 客户管理 Pydantic schemas。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BusinessInfo(BaseModel):
    description: str = ""
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    services: list[str] | None = None
    competitors: list[str] | None = None
    keywords: list[str] | None = None


class ClientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    industry: str = Field(..., min_length=1, max_length=100)
    region: str = Field(..., min_length=1, max_length=100)
    business_info: dict[str, Any] = Field(default_factory=dict)
    plan: str = "basic"
    status: str = "active"
    # 是否调 LLM 自动扩展 business_info.keywords (用品牌名/描述生成别名子品牌).
    # 关闭时只保留用户填写的 keywords, 外加品牌主名作为保底.
    auto_expand_keywords: bool = True


class ClientUpdate(BaseModel):
    name: str | None = None
    industry: str | None = None
    region: str | None = None
    business_info: dict[str, Any] | None = None
    plan: str | None = None
    status: str | None = None
    # None = 默认行为 (不触发重扩展, 直接用 business_info.keywords 原样);
    # True = 强制用 LLM 再扩展一次; False = 显式不扩展 (同默认).
    # 这样常规保存操作不会误调 LLM, 用户手动删的词也不会被 LLM 加回来.
    auto_expand_keywords: bool | None = None


class ClientOut(BaseModel):
    id: int
    name: str
    industry: str
    region: str
    business_info: dict[str, Any]
    plan: str
    status: str
    created_at: datetime
    updated_at: datetime
