"""Services responsible for OCR extraction and structuring."""

from __future__ import annotations

import logging
from typing import BinaryIO, Iterable, List, Optional

from models.entities import OCRParseResult, Transaction
from services.vision_ocr_service import VisionOCRService

logger = logging.getLogger(__name__)


def _t(key: str, fallback: str) -> str:
    """Translate error messages when session/i18n is available."""
    try:
        from utils.session import get_i18n  # Imported lazily to avoid hard dependency

        return get_i18n().t(key)
    except Exception:  # pylint: disable=broad-except
        return fallback


class OCRService:
    """使用Vision LLM进行高精度OCR识别和结构化（替代PaddleOCR）."""

    def __init__(
        self,
        use_angle_class: bool = True,
        lang: str = "ch",
        structuring_service: Optional = None,
    ) -> None:
        """
        初始化OCR服务

        Args:
            use_angle_class: 保留参数用于向后兼容，但不再使用
            lang: 保留参数用于向后兼容，但不再使用
            structuring_service: 不再需要，Vision LLM直接输出结构化数据
        """
        # 使用Vision LLM服务（默认gpt-4o）
        self._vision_ocr = VisionOCRService(model="gpt-4o")
        logger.info("OCR服务初始化完成，使用Vision LLM (gpt-4o)")

    def extract_text(self, image_bytes: bytes) -> str:
        """
        运行OCR识别（仅用于兼容性，实际使用Vision LLM直接提取交易）

        Args:
            image_bytes: 图片字节数据

        Returns:
            OCR识别的文本（简化版本，主要用于日志）
        """
        try:
            # 使用Vision LLM提取交易
            transactions = self._vision_ocr.extract_transactions_from_image(image_bytes)

            # 生成简单的文本表示用于日志
            lines = []
            for txn in transactions:
                lines.append(
                    f"{txn.date} | {txn.merchant} | {txn.category} | ¥{txn.amount}"
                )

            return (
                "\n".join(lines)
                if lines
                else _t(
                    "bill_upload.vision_structured_placeholder",
                    "Vision OCR returned structured transactions directly.",
                )
            )

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("OCR识别失败：%s", exc)
            raise RuntimeError(
                _t("errors.ocr_run_fail", "OCR failed. Please check image quality.")
            ) from exc

    def structure_transactions(self, ocr_text: str) -> List[Transaction]:
        """
        结构化交易数据（已弃用，Vision LLM直接输出结构化数据）

        Args:
            ocr_text: OCR文本（不再使用）

        Returns:
            空列表（实际数据在process_files中直接获取）
        """
        logger.warning("structure_transactions已弃用，请直接使用Vision LLM提取交易")
        return []

    def process_files(self, files: Iterable[BinaryIO]) -> List[OCRParseResult]:
        """
        处理上传的文件，使用Vision LLM提取交易记录

        Args:
            files: 上传的文件对象

        Returns:
            OCRParseResult列表
        """
        outcomes: List[OCRParseResult] = []
        for file_obj in files:
            filename = getattr(
                file_obj,
                "name",
                _t("common.unnamed_file", "Uploaded file"),
            )
            file_obj.seek(0)
            raw_bytes = file_obj.read()
            if not raw_bytes:
                logger.warning("文件%s为空，已跳过。", filename)
                continue

            try:
                # 使用Vision LLM直接提取交易记录
                transactions = self._vision_ocr.extract_transactions_from_image(
                    raw_bytes
                )

                # 生成简单的OCR文本用于显示
                raw_text = "\n".join(
                    f"{txn.date} | {txn.merchant} | {txn.category} | ¥{txn.amount}"
                    for txn in transactions
                )

                outcomes.append(
                    OCRParseResult(
                        filename=filename, text=raw_text, transactions=transactions
                    )
                )
                logger.info(f"文件 {filename} 识别到 {len(transactions)} 条交易记录")

            except Exception as exc:  # pylint: disable=broad-except
                logger.error(f"处理文件 {filename} 失败: {exc}")
                # 返回空结果而不是抛出异常，让用户可以继续处理其他文件
                failure_text = _t("errors.ocr_run_fail", "OCR failed.")
                outcomes.append(
                    OCRParseResult(
                        filename=filename,
                        text=f"{failure_text}: {str(exc)}",
                        transactions=[],
                    )
                )

        return outcomes
