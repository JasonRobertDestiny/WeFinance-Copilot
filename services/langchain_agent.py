"""LangChain-based conversational agent with finance-specific tools."""

from __future__ import annotations

import os
from typing import Iterable, List

import pandas as pd
from dotenv import load_dotenv
from langchain.agents import AgentExecutor, AgentType, Tool, initialize_agent
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI

from models.entities import Transaction
from modules.analysis import calculate_category_totals

load_dotenv()


class LangChainFinanceAgent:
    """Wraps LangChain AgentExecutor with finance-aware tools."""

    def __init__(
        self,
        transactions: Iterable[Transaction | dict],
        *,
        monthly_budget: float = 0.0,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.transactions = self._normalize_transactions(transactions)
        self.monthly_budget = monthly_budget
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")

        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured; LangChain agent unavailable."
            )

        self._setup_agent()

    @staticmethod
    def _normalize_transactions(
        transactions: Iterable[Transaction | dict],
    ) -> List[Transaction]:
        normalized: List[Transaction] = []
        for txn in transactions:
            if isinstance(txn, Transaction):
                normalized.append(txn)
            elif isinstance(txn, dict):
                normalized.append(Transaction(**txn))
        return normalized

    def _transactions_dataframe(self) -> pd.DataFrame:
        if not self.transactions:
            return pd.DataFrame(columns=["date", "category", "amount"])
        data = [
            {
                "date": pd.to_datetime(txn.date),
                "category": txn.category,
                "amount": float(txn.amount),
            }
            for txn in self.transactions
        ]
        df = pd.DataFrame(data)
        df.sort_values("date", inplace=True)
        return df

    def _tool_query_budget(self, _: str) -> str:
        df = self._transactions_dataframe()
        spent = 0.0
        if not df.empty:
            today = pd.Timestamp.today()
            mask = (df["date"].dt.month == today.month) & (
                df["date"].dt.year == today.year
            )
            spent = float(df.loc[mask, "amount"].sum())
        if self.monthly_budget <= 0:
            return "You haven't set a monthly budget yet. Please set one first."
        remaining = max(0.0, self.monthly_budget - spent)
        return (
            f"Monthly budget: ¥{self.monthly_budget:.2f}; spent: ¥{spent:.2f}; "
            f"remaining: ¥{remaining:.2f}."
        )

    def _tool_query_spending(self, _: str) -> str:
        totals = calculate_category_totals(self.transactions)
        if not totals:
            return "No spending data recorded yet."
        lines = [
            f"{category}: ¥{amount:.2f}"
            for category, amount in sorted(
                totals.items(), key=lambda item: item[1], reverse=True
            )
        ]
        return "Top category spending (up to 5):\n" + "\n".join(lines[:5])

    def _tool_query_category(self, category: str) -> str:
        category = category.strip()
        if not category:
            return "Please provide a category to query."
        totals = calculate_category_totals(self.transactions)
        amount = totals.get(category)
        if amount is None:
            return f"No spending records found for category '{category}'."
        return f"Estimated spending for '{category}' is ¥{amount:.2f}."

    def _setup_agent(self) -> None:
        llm = ChatOpenAI(
            model=self.model,
            temperature=0.3,
            api_key=self.api_key,
            base_url=self.base_url,
        )
        memory = ConversationBufferMemory(
            memory_key="chat_history", return_messages=True
        )
        tools = [
            Tool(
                name="query_budget",
                func=self._tool_query_budget,
                description="Query remaining budget for the current month.",
            ),
            Tool(
                name="query_spending",
                func=self._tool_query_spending,
                description="Summarise spending totals across categories.",
            ),
            Tool(
                name="query_category",
                func=self._tool_query_category,
                description="Return spending for a specific category name.",
            ),
        ]

        self.agent: AgentExecutor = initialize_agent(
            tools=tools,
            llm=llm,
            agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
            memory=memory,
            verbose=False,
        )

    def run(self, query: str) -> str:
        """Execute query through LangChain agent."""
        try:
            return self.agent.run(query)
        except Exception as exc:  # pylint: disable=broad-except
            raise RuntimeError(
                "LangChain agent failed to run. Please try again later."
            ) from exc
