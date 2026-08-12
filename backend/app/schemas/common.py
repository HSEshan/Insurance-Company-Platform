"""Shared response envelope and pagination schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Meta(BaseModel):
    page: int
    per_page: int
    total: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class Envelope[DataT](BaseModel):
    success: bool = True
    data: DataT | None = None
    meta: Meta | None = None
    error: ErrorDetail | None = None


def ok(data: Any = None, meta: Meta | None = None) -> dict[str, Any]:
    return {"success": True, "data": data, "meta": meta, "error": None}
