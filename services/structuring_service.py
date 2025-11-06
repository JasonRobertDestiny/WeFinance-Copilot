"""LLM-powered structuring service that converts OCR text into transactions."""

from __future__ import annotations

import json
import logging
import os
from typing import List

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from models.entities import Transaction

load_dotenv()

logger = logging.getLogger(__name__)


def _t(key: str, fallback: str) -> str:
    """Translate error messages when i18n is available."""
    try:
        from utils.session import get_i18n  # Imported lazily

        return get_i18n().t(key)
    except Exception:  # pylint: disable=broad-except
        return fallback


class StructuringService:
    """Calls OpenAI GPT-4o (or compatible) to extract transaction data in JSON."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.1,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        if not self.api_key:
            raise RuntimeError(
                _t(
                    "errors.api_key_missing",
                    "OPENAI_API_KEY is not configured. Please set it in .env.",
                )
            )

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def parse_transactions(self, text: str) -> List[Transaction]:
        """Convert OCR text into normalized transactions via GPT JSON mode."""
        if not text.strip():
            return []

        prompt = (
            "根据以下账单OCR文本，提取所有交易信息并返回JSON对象。"
            "遵循字段：transactions -> 列表，每个包含 date (YYYY-MM-DD)、merchant、"
            "category、amount (数字，支出为正值)、payment_method（可选）、raw_text。"
            "若无法识别交易，请返回空列表。保持中文分类。"
        )

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert financial data analyst who outputs valid JSON.",
                    },
                    {"role": "user", "content": f"{prompt}\n\n文本：\n{text}"},
                ],
            )
        except OpenAIError as exc:  # pragma: no cover - network dependency
            logger.error("调用GPT结构化接口失败：%s", exc)
            raise RuntimeError(
                _t(
                    "errors.structuring_fail",
                    "Structuring model request failed. Please retry later.",
                )
            ) from exc
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("结构化模型未知错误：%s", exc)
            raise RuntimeError(
                _t(
                    "errors.structuring_fail",
                    "An unexpected structuring error occurred.",
                )
            ) from exc

        content = completion.choices[0].message.content
        if content is None:
            return []

        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                _t("errors.structuring_fail", "Model response was not valid JSON.")
            ) from exc

        transactions_payload = payload.get("transactions", [])
        if not isinstance(transactions_payload, list):
            raise RuntimeError(
                _t(
                    "errors.structuring_fail",
                    "Model response missing 'transactions' array.",
                )
            )

        transactions: List[Transaction] = []
        for entry in transactions_payload:
            if not isinstance(entry, dict):
                logger.warning("忽略非字典交易条目：%s", entry)
                continue
            try:
                transactions.append(Transaction(**entry))
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("交易解析失败：%s，错误：%s", entry, exc)
                continue
        return transactions
