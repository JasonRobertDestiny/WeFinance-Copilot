"""Vision LLM-based OCR service for accurate bill recognition."""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import List, Optional

from openai import OpenAI

from models.entities import Transaction
from utils.error_handling import safe_call

logger = logging.getLogger(__name__)


def _t(key: str, fallback: str) -> str:
    """Best-effort translation helper for environments without Streamlit."""
    try:
        from utils.session import get_i18n  # Imported lazily to avoid heavy deps

        return get_i18n().t(key)
    except Exception:  # pylint: disable=broad-except
        return fallback


class VisionOCRService:
    """使用视觉大模型进行OCR识别，比传统OCR精度更高."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        """
        初始化视觉OCR服务

        Args:
            model: 视觉模型名称，默认使用 gpt-4o（推荐），也支持 qwen3-vl-plus, gemini-2.5-pro
            api_key: OpenAI兼容API密钥
            base_url: API基础URL
        """
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")

        if not self.api_key:
            raise ValueError(
                _t(
                    "errors.api_key_missing",
                    "OPENAI_API_KEY environment variable not set",
                )
            )

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        logger.info(f"初始化视觉OCR服务，使用模型：{self.model}")

    @safe_call(timeout=30, error_message="账单识别失败")
    def extract_transactions_from_image(self, image_bytes: bytes) -> List[Transaction]:
        """
        从图片中提取交易记录

        Args:
            image_bytes: 图片字节数据

        Returns:
            Transaction对象列表
        """
        try:
            # 将图片编码为base64
            base64_image = base64.b64encode(image_bytes).decode("utf-8")

            # 构造提示词
            prompt = """你是一个专业的财务账单识别助手。请仔细分析这张账单图片，提取所有交易记录。

要求：
1. 识别账单中的每一笔交易
2. 提取以下字段：日期(date)、商户名称(merchant)、分类(category)、金额(amount)
3. 日期格式：YYYY-MM-DD
4. 金额为数字，不带货币符号
5. 分类从以下选择：餐饮、交通、购物、娱乐、医疗、教育、其他

返回格式（纯JSON数组，不要markdown代码块）：
[
  {
    "date": "2025-11-01",
    "merchant": "星巴克",
    "category": "餐饮",
    "amount": 45.0
  }
]

如果无法识别到交易记录，返回空数组：[]"""

            # 调用视觉模型
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ],
                max_tokens=2000,
                temperature=0.0,  # 确定性输出
            )

            # 解析响应
            content = response.choices[0].message.content
            logger.debug(f"视觉模型原始响应: {content}")

            # 清理响应（移除可能的markdown代码块）
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # 解析JSON
            transactions_data = json.loads(content)

            # 转换为Transaction对象
            transactions = []
            for idx, item in enumerate(transactions_data):
                try:
                    txn = Transaction(
                        id=str(idx + 1),
                        date=item["date"],
                        merchant=item["merchant"],
                        category=item["category"],
                        amount=float(item["amount"]),
                    )
                    transactions.append(txn)
                except (KeyError, ValueError) as e:
                    logger.warning(f"跳过无效交易记录: {item}, 错误: {e}")
                    continue

            logger.info(f"成功从图片中提取 {len(transactions)} 条交易记录")
            return transactions

        except json.JSONDecodeError as exc:
            logger.error("JSON解析失败: %s, 原始响应: %s", exc, content)
            raise
        except Exception as exc:
            logger.error("视觉OCR识别失败: %s", exc)
            raise
