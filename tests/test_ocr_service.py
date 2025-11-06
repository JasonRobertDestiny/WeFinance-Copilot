"""Tests for the Vision-based OCR service integration."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from services.ocr_service import OCRService
from services.vision_ocr_service import VisionOCRService


@pytest.fixture(autouse=True)
def set_fake_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://fake.endpoint/")


@pytest.mark.parametrize("file_name", ["test_bill.png", "receipt.jpg"])
@patch("services.vision_ocr_service.OpenAI")
def test_process_files_with_vision_success(mock_openai: MagicMock, file_name: str) -> None:
    """Vision OCR returns structured transactions and readable text."""

    mock_response = MagicMock()
    mock_response.choices[0].message.content = """
    [
      {"date": "2025-11-01", "merchant": "测试商户", "category": "餐饮", "amount": 45.0}
    ]
    """
    mock_openai.return_value.chat.completions.create.return_value = mock_response

    fake_file = BytesIO(b"fake-image-data")
    fake_file.name = file_name

    ocr_service = OCRService()
    results = ocr_service.process_files([fake_file])

    assert len(results) == 1
    record = results[0]
    assert record.filename == file_name
    assert record.transactions and record.transactions[0].merchant == "测试商户"
    assert "测试商户" in record.text


@patch("services.vision_ocr_service.OpenAI")
def test_process_files_handles_error(mock_openai: MagicMock) -> None:
    """Vision OCR failures are captured gracefully without crashing."""

    fake_file = BytesIO(b"fake-image-data")
    fake_file.name = "broken.png"

    ocr_service = OCRService()
    ocr_service._vision_ocr = MagicMock(spec=VisionOCRService)
    ocr_service._vision_ocr.extract_transactions_from_image.side_effect = RuntimeError("vision error")

    results = ocr_service.process_files([fake_file])

    assert len(results) == 1
    record = results[0]
    assert record.filename == "broken.png"
    assert record.transactions == []
    assert "识别失败" in record.text
