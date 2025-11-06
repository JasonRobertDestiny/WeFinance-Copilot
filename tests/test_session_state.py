"""Tests for session state helper utilities."""

from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace

import pytest

dummy_streamlit = SimpleNamespace(session_state={})
dummy_streamlit.rerun = lambda: None
sys.modules.setdefault("streamlit", dummy_streamlit)

from models.entities import Transaction  # noqa: E402
from utils import session as session_utils  # noqa: E402


@pytest.fixture(autouse=True)
def stub_streamlit(monkeypatch):
    dummy = SimpleNamespace(session_state={}, rerun=lambda: None)
    monkeypatch.setattr(session_utils, "st", dummy)
    session_utils.init_session_state()
    yield dummy.session_state
    dummy.session_state.clear()


def test_transactions_roundtrip():
    txn = Transaction(
        id="txn-1",
        date=date(2025, 11, 1),
        merchant="Test Merchant",
        category="餐饮",
        amount=88.0,
    )
    session_utils.set_transactions([txn])
    retrieved = session_utils.get_transactions()
    assert len(retrieved) == 1
    assert retrieved[0].merchant == "Test Merchant"


def test_anomaly_state_persistence():
    anomaly = {
        "transaction_id": "txn-999",
        "date": "2025-11-06",
        "merchant": "可疑商户",
        "amount": 9999.0,
        "reason": "异常高额消费",
    }
    session_utils.update_anomaly_state(
        active=[anomaly], message="spending.anomaly_no_detect"
    )
    active = session_utils.get_active_anomalies()
    assert len(active) == 1

    session_utils.record_anomaly_feedback(active[0], "confirmed")
    history = session_utils.get_anomaly_history()
    assert history[0]["status"] == "confirmed"


def test_trusted_merchant_management():
    session_utils.add_trusted_merchant("星巴克")
    session_utils.add_trusted_merchant("盒马鲜生")
    session_utils.add_trusted_merchant("星巴克")  # duplicate should be ignored

    whitelist = session_utils.get_trusted_merchants()
    assert "星巴克" in whitelist
    assert len(whitelist) == 2

    session_utils.remove_trusted_merchant("星巴克")
    whitelist = session_utils.get_trusted_merchants()
    assert "星巴克" not in whitelist
