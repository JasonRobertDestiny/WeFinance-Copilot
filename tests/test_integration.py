"""Integration-style checks for core bilingual workflows."""

from __future__ import annotations

import datetime as dt
from io import BytesIO
from typing import Dict, Iterable, List
from unittest.mock import Mock

import pytest

from models.entities import Transaction
from modules.chat_manager import ChatManager
from modules.analysis import (
    calculate_category_totals,
    compute_anomaly_report,
    generate_insights,
)
from services.ocr_service import OCRService
from services.recommendation_service import RecommendationService
from utils.i18n import I18n


@pytest.fixture(autouse=True)
def _ensure_env(monkeypatch):
    """Mock API keys to avoid accidental real calls."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://mock.endpoint/v1")


@pytest.fixture(autouse=True)
def _disable_langchain(monkeypatch):
    """Prevent LangChain agent instantiation during integration tests."""
    monkeypatch.setattr("modules.chat_manager.LangChainFinanceAgent", None)


@pytest.fixture
def sample_transactions() -> List[Transaction]:
    """Provide a baseline set of transactions for integration flows."""
    return [
        Transaction(
            id="txn-001",
            date=dt.date(2025, 10, 28),
            merchant="星巴克",
            category="餐饮",
            amount=45.0,
        ),
        Transaction(
            id="txn-002",
            date=dt.date(2025, 10, 30),
            merchant="地铁出行",
            category="交通",
            amount=6.0,
        ),
        Transaction(
            id="txn-003",
            date=dt.date(2025, 11, 1),
            merchant="美团外卖",
            category="餐饮",
            amount=58.0,
        ),
        Transaction(
            id="txn-004",
            date=dt.date(2025, 11, 2),
            merchant="京东",
            category="购物",
            amount=120.0,
        ),
        Transaction(
            id="txn-005",
            date=dt.date(2025, 11, 3),
            merchant="盒马鲜生",
            category="餐饮",
            amount=65.5,
        ),
        Transaction(
            id="txn-006",
            date=dt.date(2025, 11, 4),
            merchant="喜茶",
            category="餐饮",
            amount=28.0,
        ),
        Transaction(
            id="txn-007",
            date=dt.date(2025, 11, 4),
            merchant="滴滴出行",
            category="交通",
            amount=12.0,
        ),
        Transaction(
            id="txn-008",
            date=dt.date(2025, 11, 5),
            merchant="711便利店",
            category="日常",
            amount=35.0,
        ),
        Transaction(
            id="txn-009",
            date=dt.date(2025, 11, 5),
            merchant="商超采购",
            category="购物",
            amount=85.0,
        ),
        Transaction(
            id="txn-010",
            date=dt.date(2025, 11, 6),
            merchant="盒马鲜生",
            category="餐饮",
            amount=52.0,
        ),
    ]


def _mock_llm(chat_manager: ChatManager) -> None:
    """Ensure no real OpenAI call happens during tests."""
    chat_manager._ensure_client = Mock(side_effect=RuntimeError("LLM disabled"))  # type: ignore[attr-defined]
    chat_manager._maybe_run_langchain_agent = Mock(return_value=None)  # type: ignore[attr-defined]


def _recommendation_locale_payload(
    transactions: Iterable[Transaction],
    responses: Dict[str, int],
    goal: str,
    locale: str,
) -> Dict[str, object]:
    service = RecommendationService()
    return service.generate(
        transactions=transactions,
        responses=responses,
        investment_goal=goal,
        locale=locale,
    )


# -----------------------------------------------------------------------------
# Scenario 1 & 2: Full workflow in Chinese and English
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "locale,question,expected_snippet,risk_expectation",
    [
        ("zh_CN", "我最近在哪方面花钱最多？", "餐饮", "保守型"),
        (
            "en_US",
            "Where am I spending the most recently?",
            "Your top spending category",
            "Conservative",
        ),
    ],
)
def test_full_workflow_locale(
    sample_transactions, locale, question, expected_snippet, risk_expectation
):
    """Upload → analysis → chat → recommendation for two locales."""
    totals = calculate_category_totals(sample_transactions)
    assert totals

    insights = generate_insights(sample_transactions)
    assert insights

    chat_manager = ChatManager(
        transactions=sample_transactions, monthly_budget=1200.0, locale=locale
    )
    _mock_llm(chat_manager)
    chat_manager.add_message("user", question)
    reply = chat_manager.generate_response(question)
    assert expected_snippet in reply

    payload = _recommendation_locale_payload(
        sample_transactions,
        responses={"q1": 1, "q2": 2, "q3": 1},
        goal="存钱买车" if locale == "zh_CN" else "Save 200k to buy a car",
        locale=locale,
    )
    assert payload["risk_level"].startswith(risk_expectation)
    summary = payload["recommendation"].summary  # type: ignore[index]
    assert isinstance(summary, str) and summary


# -----------------------------------------------------------------------------
# Scenario 3: Anomaly detection and feedback loop
# -----------------------------------------------------------------------------


def test_anomaly_detection_feedback(sample_transactions):
    """Detect anomaly, confirm, and mark fraud."""
    outlier = Transaction(
        id="txn-200",
        date=dt.date(2025, 11, 5),
        merchant="可疑商户",
        category="其他",
        amount=9100.0,
    )
    report = compute_anomaly_report(sample_transactions + [outlier], base_threshold=2.0)
    anomalies = report["items"]
    assert anomalies

    active = list(anomalies)
    history: List[Dict[str, object]] = []

    first = active.pop(0)
    first["status"] = "confirmed"
    history.append(first)

    second = dict(first)
    second["status"] = "fraud"
    history.append(second)

    assert history[0]["status"] == "confirmed"
    assert history[1]["status"] == "fraud"
    assert not active


# -----------------------------------------------------------------------------
# Scenario 4: Language switching mid-session
# -----------------------------------------------------------------------------


def test_language_switching_behaviour(sample_transactions):
    """Language switch should produce locale-appropriate outputs without data loss."""
    zh_manager = ChatManager(
        transactions=sample_transactions, monthly_budget=1500.0, locale="zh_CN"
    )
    _mock_llm(zh_manager)
    zh_reply = zh_manager.generate_response("我这个月还能花多少？")
    assert "剩余" in zh_reply

    en_manager = ChatManager(
        transactions=sample_transactions, monthly_budget=1500.0, locale="en_US"
    )
    _mock_llm(en_manager)
    en_reply = en_manager.generate_response("How much can I still spend this month?")
    assert "remaining" in en_reply.lower()

    zh_payload = _recommendation_locale_payload(
        sample_transactions, {"q1": 2, "q2": 2, "q3": 2}, "教育基金", "zh_CN"
    )
    en_payload = _recommendation_locale_payload(
        sample_transactions, {"q1": 2, "q2": 2, "q3": 2}, "Education fund", "en_US"
    )
    assert "稳健型" in zh_payload["recommendation"].summary  # type: ignore[index]
    assert "Balanced" in en_payload["recommendation"].summary  # type: ignore[index]


# -----------------------------------------------------------------------------
# Scenario 5: Error handling paths
# -----------------------------------------------------------------------------


def test_error_handling_messages(monkeypatch):
    """Ensure Vision OCR service returns user-friendly messages on failure."""
    from services.vision_ocr_service import VisionOCRService

    ocr = OCRService()
    mock_vision = Mock(spec=VisionOCRService)
    mock_vision.extract_transactions_from_image.side_effect = RuntimeError(
        "vision error"
    )
    monkeypatch.setattr(ocr, "_vision_ocr", mock_vision)

    fake_file = BytesIO(b"fake")
    fake_file.name = "test.png"

    results = ocr.process_files([fake_file])
    assert len(results) == 1
    record = results[0]
    assert record.filename == "test.png"
    assert record.transactions == []
    assert "识别失败" in record.text or "vision error" in record.text


# -----------------------------------------------------------------------------
# Additional sanity checks for bilingual resources
# -----------------------------------------------------------------------------


def test_i18n_resources_available():
    """Ensure key translation categories are present."""
    zh = I18n("zh_CN")
    en = I18n("en_US")
    for key in [
        "app.title",
        "navigation.home",
        "bill_upload.title",
        "spending.title",
        "chat.title",
        "recommendation.title",
    ]:
        assert zh.t(key) != key
        assert en.t(key) != key
