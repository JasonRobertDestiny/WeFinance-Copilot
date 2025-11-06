"""Service layer for generating explainable financial recommendations."""

from __future__ import annotations

import math
import re
from typing import Dict, Iterable, Tuple

from models.entities import Recommendation, Transaction
from utils.i18n import I18n


class RecommendationService:
    """Generate risk-aware allocation plans with explainable rationale."""

    ALLOCATION_RULES: Dict[str, Dict[str, float]] = {
        "conservative": {"债券基金": 0.7, "混合理财": 0.3},
        "balanced": {"债券基金": 0.5, "股票基金": 0.3, "货币基金": 0.2},
        "aggressive": {"股票基金": 0.6, "成长基金": 0.3, "货币基金": 0.1},
    }

    EXPECTED_RETURN = {"conservative": 4.5, "balanced": 6.8, "aggressive": 9.5}
    MAX_DRAWDOWN = {"conservative": 5.0, "balanced": 12.0, "aggressive": 20.0}

    def conduct_risk_assessment(self, responses: Dict[str, int]) -> str:
        """Map questionnaire responses to a risk profile key."""
        score = sum(responses.values())
        if score <= 4:
            return "conservative"
        if score <= 7:
            return "balanced"
        return "aggressive"

    def generate_allocation(self, risk_profile: str) -> Dict[str, float]:
        """Return asset allocation percentages based on risk appetite."""
        return self.ALLOCATION_RULES.get(
            risk_profile, self.ALLOCATION_RULES["balanced"]
        )

    @staticmethod
    def _parse_goal(goal_text: str) -> Tuple[str, float | None, int | None]:
        """
        Extract core goal, target amount (RMB), and horizon (months) from freeform text.
        """
        normalized = goal_text.strip()
        if not normalized:
            return "未指定", None, None

        amount_match = re.search(r"(\d+(?:\.\d+)?)\s*(万|千|元|块)?", normalized)
        amount_value = None
        if amount_match:
            value = float(amount_match.group(1))
            unit = amount_match.group(2) or ""
            multiplier = 1.0
            if unit in {"万", "万元"}:
                multiplier = 10_000.0
            elif unit in {"千", "千元"}:
                multiplier = 1_000.0
            amount_value = value * multiplier

        horizon_match = re.search(r"(\d+)\s*(年|个月|月)", normalized)
        horizon_months = None
        if horizon_match:
            value = int(horizon_match.group(1))
            unit = horizon_match.group(2)
            horizon_months = value * 12 if unit == "年" else value

        return normalized, amount_value, horizon_months

    def _estimate_metrics(self, risk_profile: str) -> Dict[str, float]:
        return {
            "expected_return": self.EXPECTED_RETURN[risk_profile],
            "max_drawdown": self.MAX_DRAWDOWN[risk_profile],
        }

    def _format_allocation_desc(
        self, allocation: Dict[str, float], i18n: I18n
    ) -> Tuple[str, str]:
        allocation_desc = ", ".join(
            f"{i18n.t('recommendation.assets.' + asset)} {percentage*100:.0f}%"
            for asset, percentage in allocation.items()
        )
        allocation_rationale = "\n".join(
            f"- {i18n.t('recommendation.assets.' + asset)}: {percentage*100:.0f}%"
            for asset, percentage in allocation.items()
        )
        return allocation_desc, allocation_rationale

    def create_plan(
        self,
        responses: Dict[str, int],
        investment_goal: str,
        transactions: Iterable[Transaction],
        locale: str,
    ) -> Tuple[Recommendation, str, Dict[str, float], Dict[str, float], str]:
        """High-level orchestrator returning recommendation, explanation and metrics."""
        i18n = I18n(locale)
        risk_key = self.conduct_risk_assessment(responses)
        risk_name = i18n.t(f"recommendation.risk_name.{risk_key}")

        allocation = self.generate_allocation(risk_key)
        allocation_desc, allocation_rationale = self._format_allocation_desc(
            allocation, i18n
        )

        metrics = self._estimate_metrics(risk_key)
        goal_name, goal_amount, goal_horizon = self._parse_goal(investment_goal)
        summary = i18n.t(
            "recommendation.summary_template",
            risk_name=risk_name,
            allocation_desc=allocation_desc,
            goal_name=goal_name,
        )
        if goal_amount and goal_horizon and goal_horizon > 0:
            monthly = math.ceil(goal_amount / goal_horizon)
            summary += " " + i18n.t("recommendation.savings_tip", monthly=monthly)

        rationale_steps = [
            i18n.t("recommendation.step_risk", risk_name=risk_name),
            i18n.t("recommendation.step_allocation", allocation_desc=allocation_desc),
            i18n.t(
                "recommendation.step_metrics",
                expected=metrics["expected_return"],
                drawdown=metrics["max_drawdown"],
            ),
        ]

        explanation = i18n.t(
            "recommendation.explanation_template",
            risk_name=risk_name,
            goal_name=goal_name,
            rationale_1=i18n.t(f"recommendation.rationale_profile.{risk_key}"),
            rationale_2=i18n.t("recommendation.rationale_goal"),
            expected_return=metrics["expected_return"],
            max_drawdown=metrics["max_drawdown"],
            allocation_rationale=allocation_rationale,
        )

        recommendation = Recommendation(
            title=i18n.t("recommendation.title"),
            summary=summary,
            rationale_steps=rationale_steps,
            risk_level=risk_name,
        )

        return recommendation, explanation, metrics, allocation, risk_name

    def generate(
        self,
        transactions: Iterable[Transaction],
        responses: Dict[str, int],
        investment_goal: str,
        *,
        locale: str = "zh_CN",
    ) -> Dict[str, object]:
        """Public API returning recommendation payload for UI consumption."""
        recommendation, explanation, metrics, allocation, risk_name = self.create_plan(
            responses=responses,
            investment_goal=investment_goal,
            transactions=transactions,
            locale=locale,
        )
        return {
            "recommendation": recommendation,
            "explanation": explanation,
            "metrics": metrics,
            "allocation": allocation,
            "risk_level": risk_name,
            "locale": locale,
        }
