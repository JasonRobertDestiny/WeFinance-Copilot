"""Unit tests for the GPT-driven structuring service."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services import structuring_service
from services.structuring_service import StructuringService


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    """Ensure API key is present for service initialisation."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://mock.endpoint/v1")


def _build_completion(payload: dict | str | None):
    """Helper returning a completion object respecting the OpenAI schema."""
    message = SimpleNamespace(
        content=json.dumps(payload) if isinstance(payload, dict) else payload
    )
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def test_parse_transactions_success(monkeypatch):
    """The service should return Transaction instances for valid JSON."""
    mock_client = Mock()
    payload = {
        "transactions": [
            {
                "id": "txn-1",
                "date": "2025-11-01",
                "merchant": "星巴克",
                "category": "餐饮",
                "amount": 45.0,
                "currency": "CNY",
            }
        ]
    }
    mock_client.chat.completions.create.return_value = _build_completion(payload)
    monkeypatch.setattr(structuring_service, "OpenAI", Mock(return_value=mock_client))

    service = StructuringService()
    transactions = service.parse_transactions("示例OCR文本")

    assert len(transactions) == 1
    assert transactions[0].merchant == "星巴克"
    mock_client.chat.completions.create.assert_called_once()


def test_parse_transactions_ignores_bad_rows(monkeypatch):
    """Non-dict entries should be skipped without breaking the workflow."""
    mock_client = Mock()
    payload = {
        "transactions": [
            "invalid-entry",
            {
                "id": "ok",
                "date": "2025-11-02",
                "merchant": "麦当劳",
                "category": "餐饮",
                "amount": 28.8,
            },
        ]
    }
    mock_client.chat.completions.create.return_value = _build_completion(payload)
    monkeypatch.setattr(structuring_service, "OpenAI", Mock(return_value=mock_client))

    service = StructuringService()
    transactions = service.parse_transactions("含有异常行的文本")

    assert len(transactions) == 1
    assert transactions[0].merchant == "麦当劳"


def test_parse_transactions_invalid_json(monkeypatch):
    """Invalid JSON returned by the model should raise RuntimeError."""
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = _build_completion("{not-json}")
    monkeypatch.setattr(structuring_service, "OpenAI", Mock(return_value=mock_client))

    service = StructuringService()
    with pytest.raises(RuntimeError):
        service.parse_transactions("bad payload")


def test_parse_transactions_empty_text(monkeypatch):
    """Blank OCR text bypasses the LLM call."""
    mock_client = Mock()
    monkeypatch.setattr(structuring_service, "OpenAI", Mock(return_value=mock_client))

    service = StructuringService()
    assert service.parse_transactions("   ") == []
    mock_client.chat.completions.create.assert_not_called()
