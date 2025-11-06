"""Unit tests for ChatManager heuristics and fallbacks."""

from __future__ import annotations

import datetime as dt
from typing import List

import pytest
from openai import OpenAIError
from unittest.mock import Mock

from models.entities import Transaction
from modules.chat_manager import ChatManager


@pytest.fixture
def sample_transactions() -> List[Transaction]:
    return [
        Transaction(
            id="txn-1",
            date=dt.date(2025, 11, 1),
            merchant="星巴克",
            category="餐饮",
            amount=58.0,
        ),
        Transaction(
            id="txn-2",
            date=dt.date(2025, 11, 2),
            merchant="地铁出行",
            category="交通",
            amount=6.0,
        ),
    ]


def _disable_llm(manager: ChatManager) -> None:
    def _raise():
        raise RuntimeError("LLM disabled")

    manager._ensure_client = _raise  # type: ignore[attr-defined]
    manager._maybe_run_langchain_agent = lambda *_: None  # type: ignore[attr-defined]


def test_budget_heuristic_chinese(sample_transactions):
    manager = ChatManager(
        transactions=sample_transactions, monthly_budget=500.0, locale="zh_CN"
    )
    _disable_llm(manager)
    reply = manager.generate_response("我这个月还能花多少？")
    assert "剩余" in reply


def test_top_category_heuristic_english(sample_transactions):
    manager = ChatManager(
        transactions=sample_transactions, monthly_budget=0.0, locale="en_US"
    )
    _disable_llm(manager)
    reply = manager.generate_response("Where am I spending the most recently?")
    assert "Dining" in reply or "餐饮" in reply


def test_rule_based_fallback_summary(sample_transactions):
    manager = ChatManager(
        transactions=sample_transactions, monthly_budget=300.0, locale="en_US"
    )

    dummy_client = Mock()
    dummy_client.chat.completions.create.side_effect = OpenAIError("offline")  # type: ignore[attr-defined]
    manager._ensure_client = lambda: dummy_client  # type: ignore[attr-defined]
    manager._maybe_run_langchain_agent = lambda *_: None  # type: ignore[attr-defined]

    reply = manager.generate_response("Give me detailed advice.")
    assert "LLM is unavailable" in reply
    assert "Dining" in reply or "餐饮" in reply
