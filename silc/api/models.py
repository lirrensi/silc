"""Pydantic models used by the SILC FastAPI surface."""

from __future__ import annotations

from pydantic import BaseModel


class InputRequest(BaseModel):
    text: str


class RunRequest(BaseModel):
    command: str
    timeout: int = 60


__all__ = ["InputRequest", "RunRequest"]
