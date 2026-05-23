"""M7 Diagnosis Pydantic schemas."""
from __future__ import annotations

from pydantic import BaseModel


class DiagnosisRequest(BaseModel):
    url: str
    client_id: int | None = None  # optional: link result to a client


class GenerateSchemaRequest(BaseModel):
    url: str


class GenerateLlmsTxtRequest(BaseModel):
    url: str
    company_name: str = ""
    description: str = ""
    services: list[str] = []
