"""Data models shared across modules."""

from __future__ import annotations

import datetime as dt
from typing import List, Optional

from pydantic import BaseModel, Field


class Transaction(BaseModel):
    """Normalized transaction record parsed from OCR or CSV."""

    id: str = Field(..., description="Deterministic identifier (uuid4 or hash).")
    date: dt.date = Field(..., description="Transaction posting date.")
    merchant: str = Field(..., description="Merchant or counterparty name.")
    category: str = Field(..., description="Spending category label.")
    amount: float = Field(..., description="Positive numbers represent expenses.")
    currency: str = Field(
        default="CNY", description="Currency code in ISO-4217 format."
    )
    payment_method: Optional[str] = Field(
        default=None, description="Payment instrument such as 微信支付."
    )
    raw_text: Optional[str] = Field(
        default=None, description="Original OCR text snippet for explainability."
    )


class SpendingInsight(BaseModel):
    """High-level summary of spending behaviour for the dashboard."""

    title: str
    detail: str
    delta: Optional[float] = Field(
        default=None, description="Month-over-month delta expressed as a percentage."
    )


class Recommendation(BaseModel):
    """Financial product or budgeting recommendation."""

    title: str
    summary: str
    rationale_steps: List[str] = Field(
        default_factory=list, description="Explainable reasoning chain."
    )
    risk_level: Optional[str] = Field(
        default=None, description="Optional qualitative risk label."
    )


class OCRParseResult(BaseModel):
    """Full OCR pipeline outcome for a single uploaded file."""

    filename: str
    text: str
    transactions: List[Transaction] = Field(default_factory=list)
