"""Chat manager coordinating conversational interactions with the LLM."""

from __future__ import annotations

import logging
import os
import time
from typing import Iterable, List, Optional

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from models.entities import Transaction
from modules.analysis import calculate_category_totals
from utils.i18n import I18n

try:  # Optional LangChain integration
    from services.langchain_agent import LangChainFinanceAgent
except Exception:  # pragma: no cover - optional dependency
    LangChainFinanceAgent = None  # type: ignore[assignment]

load_dotenv()

logger = logging.getLogger(__name__)


class ChatManager:
    """Manage chat history, budgeting context, and LLM responses."""

    def __init__(
        self,
        *,
        history: Optional[List[dict]] = None,
        transactions: Optional[Iterable[Transaction | dict]] = None,
        monthly_budget: float | None = None,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
        locale: str | None = None,
    ) -> None:
        self.history: List[dict] = history if history is not None else []
        self.transactions: List[Transaction] = self._normalize_transactions(
            transactions
        )
        self.monthly_budget = monthly_budget if monthly_budget is not None else 0.0
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.locale = locale or "zh_CN"
        self.i18n = I18n(self.locale)
        self.system_prompt_template = self.i18n.t("chat.system_prompt")

        self._client: Optional[OpenAI] = None
        self._lc_agent: Optional[LangChainFinanceAgent] = None

    @staticmethod
    def _normalize_transactions(
        transactions: Optional[Iterable[Transaction | dict]],
    ) -> List[Transaction]:
        if not transactions:
            return []
        normalized: List[Transaction] = []
        for txn in transactions:
            if isinstance(txn, Transaction):
                normalized.append(txn)
            elif isinstance(txn, dict):
                normalized.append(Transaction(**txn))
        return normalized

    def update_transactions(self, transactions: Iterable[Transaction | dict]) -> None:
        """Replace stored transactions, keeping conversions consistent."""
        self.transactions = self._normalize_transactions(transactions)
        self._lc_agent = None

    def set_monthly_budget(self, amount: float) -> None:
        """Persist current monthly budget."""
        self.monthly_budget = max(0.0, float(amount))
        self._lc_agent = None

    def add_message(self, role: str, content: str) -> None:
        """Append a message to the conversation history."""
        self.history.append({"role": role, "content": content})

    def get_context(self, limit: int = 10) -> List[dict]:
        """Return the last N messages to maintain conversational context."""
        return self.history[-limit:]

    # ------------------------------------------------------------------ #
    # Data-driven helpers
    # ------------------------------------------------------------------ #
    def _transactions_dataframe(self) -> pd.DataFrame:
        if not self.transactions:
            return pd.DataFrame(columns=["date", "category", "amount"])

        records = [
            {
                "date": pd.to_datetime(txn.date),
                "category": txn.category,
                "amount": float(txn.amount),
            }
            for txn in self.transactions
        ]
        df = pd.DataFrame(records)
        df.sort_values("date", inplace=True)
        return df

    def _current_month_spent(self) -> float:
        df = self._transactions_dataframe()
        if df.empty:
            return 0.0

        today = pd.Timestamp.today()
        mask = (df["date"].dt.month == today.month) & (df["date"].dt.year == today.year)
        return float(df.loc[mask, "amount"].sum())

    def _transactions_summary_text(self) -> str:
        if not self.transactions:
            return self.i18n.t("common.no_data")

        totals = calculate_category_totals(self.transactions)
        top_categories = sorted(totals.items(), key=lambda item: item[1], reverse=True)[
            :3
        ]
        summary_lines = [
            f"- {category}: ¥{amount:.2f}" for category, amount in top_categories
        ]
        return (
            "\n".join(summary_lines) if summary_lines else self.i18n.t("common.no_data")
        )

    def _summary_fallback(self) -> str:
        """Compose a rule-based summary when LLM is unavailable."""
        totals = calculate_category_totals(self.transactions)
        if totals:
            top_category = max(totals, key=totals.get)
            top_amount = totals[top_category]
        else:
            top_category = self.i18n.t("common.no_data")
            top_amount = 0.0

        spent = self._current_month_spent()
        remaining = (
            max(0.0, self.monthly_budget - spent) if self.monthly_budget else 0.0
        )
        return self.i18n.t(
            "chat.fallback_summary",
            spent=spent,
            remaining=remaining,
            category=top_category,
            amount=top_amount,
        )

    # ------------------------------------------------------------------ #
    # Query helpers
    # ------------------------------------------------------------------ #
    def query_transactions(self, question: str) -> Optional[str]:
        """
        Attempt to answer finance questions without hitting the LLM.

        Handles budget remaining and top-spending category scenarios.
        """
        normalized = question.strip()
        if not normalized:
            return None

        lowered = normalized.lower()
        chinese_budget_keywords = ("还能花", "剩多少", "剩余", "预算")
        english_budget = (
            "budget" in lowered and ("left" in lowered or "remaining" in lowered)
        ) or ("how much" in lowered and "spend" in lowered and "month" in lowered)
        has_budget_hint = (
            any(keyword in normalized for keyword in chinese_budget_keywords)
            or english_budget
        )
        has_spend_max_hint = (
            ("花钱最多" in normalized)
            or ("消费最多" in normalized)
            or ("spend" in lowered and "most" in lowered)
            or ("spending" in lowered and "most" in lowered)
        )

        if has_budget_hint:
            spent = self._current_month_spent()
            if self.monthly_budget <= 0:
                return self.i18n.t("chat.heuristic_no_budget")
            remaining = self.monthly_budget - spent
            remaining = max(0.0, remaining)
            return self.i18n.t(
                "chat.heuristic_budget", remaining=remaining, spent=spent
            )

        if has_spend_max_hint:
            totals = calculate_category_totals(self.transactions)
            if not totals:
                return self.i18n.t("chat.heuristic_no_transactions")
            top_category = max(totals, key=totals.get)
            return self.i18n.t(
                "chat.heuristic_top_category",
                category=top_category,
                amount=totals[top_category],
            )

        if (
            "平均" in normalized
            and any(token in normalized for token in ("近", "最近"))
        ) or ("average" in lowered and ("recent" in lowered or "last" in lowered)):
            df = self._transactions_dataframe()
            if df.empty:
                return self.i18n.t("chat.heuristic_no_transactions")
            window_start = df["date"].max() - pd.Timedelta(days=2)
            recent = df[df["date"] >= window_start]
            if recent.empty:
                return self.i18n.t("chat.heuristic_recent_empty")
            avg = recent["amount"].mean()
            return self.i18n.t("chat.heuristic_recent_avg", average=avg)

        if "etf" in lowered:
            return self.i18n.t("chat.heuristic_etf")

        return None

    # ------------------------------------------------------------------ #
    # LLM interactions
    # ------------------------------------------------------------------ #
    def _ensure_client(self) -> OpenAI:
        if self._client is None:
            if not self.api_key:
                raise RuntimeError(
                    self.i18n.t("errors.llm_fail", error="API key missing")
                )
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def generate_response(self, user_prompt: str) -> str:
        """
        Generate assistant response. Uses heuristics first, then falls back to GPT.
        """
        heuristic_answer = self.query_transactions(user_prompt)
        if heuristic_answer:
            self.add_message("assistant", heuristic_answer)
            return heuristic_answer

        agent_answer = self._maybe_run_langchain_agent(user_prompt)
        if agent_answer:
            self.add_message("assistant", agent_answer)
            return agent_answer

        spent = self._current_month_spent()
        remaining = (
            max(0.0, self.monthly_budget - spent) if self.monthly_budget else 0.0
        )
        system_prompt = self.system_prompt_template.format(
            transactions_summary=self._transactions_summary_text(),
            monthly_budget=f"{self.monthly_budget:.2f}",
            spent=f"{spent:.2f}",
            remaining=f"{remaining:.2f}",
        )

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.get_context())
        messages.append({"role": "user", "content": user_prompt})

        client = self._ensure_client()
        errors: List[str] = []
        for attempt in range(3):
            try:
                completion = client.chat.completions.create(
                    model=self.model,
                    temperature=0.2,
                    messages=messages,
                )
                content = completion.choices[0].message.content
                if not content:
                    raise RuntimeError("empty_response")
                self.add_message("assistant", content)
                return content
            except (OpenAIError, RuntimeError) as exc:
                errors.append(str(exc))
                logger.warning("LLM调用失败（第%s次）: %s", attempt + 1, exc)
                time_wait = 0.5 * (attempt + 1)
                time.sleep(time_wait)

        summary = self._summary_fallback()
        if errors:
            fallback = (
                self.i18n.t("chat.fallback_error_detail", error=errors[-1])
                + "\n"
                + summary
            )
        else:
            fallback = self.i18n.t("chat.fallback_error") + "\n" + summary
        self.add_message("assistant", fallback)
        return fallback

    # ------------------------------------------------------------------ #
    # LangChain agent helper
    # ------------------------------------------------------------------ #
    def _maybe_run_langchain_agent(self, query: str) -> Optional[str]:
        if LangChainFinanceAgent is None:
            return None

        try:
            agent = self._ensure_langchain_agent()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("初始化LangChain Agent失败：%s", exc)
            self._lc_agent = None
            return None

        if agent is None:
            return None

        try:
            return agent.run(query)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("LangChain Agent运行失败：%s", exc)
            self._lc_agent = None
            return None

    def _ensure_langchain_agent(self) -> Optional[LangChainFinanceAgent]:
        if LangChainFinanceAgent is None:
            return None

        if self._lc_agent is None:
            self._lc_agent = LangChainFinanceAgent(
                self.transactions,
                monthly_budget=self.monthly_budget,
                model=self.model,
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._lc_agent
