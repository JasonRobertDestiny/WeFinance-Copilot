"""Financial analysis helpers turning transactions into insights."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Sequence, Set

import numpy as np
import pandas as pd

from models.entities import SpendingInsight, Transaction


def _to_dataframe(transactions: Sequence[Transaction]) -> pd.DataFrame:
    """Convert transactions into a pandas DataFrame for numerical work."""
    if not transactions:
        return pd.DataFrame(columns=["date", "category", "amount"])

    data = [
        {
            "date": pd.to_datetime(txn.date),
            "category": txn.category,
            "amount": float(txn.amount),
            "merchant": txn.merchant,
            "id": txn.id,
        }
        for txn in transactions
    ]
    df = pd.DataFrame(data)
    df.sort_values("date", inplace=True)
    return df


def calculate_category_totals(transactions: Iterable[Transaction]) -> Dict[str, float]:
    """Aggregate spending totals per category."""
    totals: Dict[str, float] = defaultdict(float)
    for txn in transactions:
        totals[txn.category] += float(txn.amount)
    return dict(totals)


def calculate_spending_trend(
    transactions: Iterable[Transaction],
    frequency: str = "M",
) -> pd.DataFrame:
    """
    Calculate spending trend at a given frequency (D=日, W=周, M=月).

    Returns a DataFrame with columns ['period', 'amount'].
    """
    transactions = list(transactions)
    df = _to_dataframe(transactions)
    if df.empty:
        return pd.DataFrame(columns=["period", "amount"])

    df.set_index("date", inplace=True)
    resampled = df["amount"].resample(frequency).sum().reset_index()
    resampled.rename(columns={"date": "period", "amount": "amount"}, inplace=True)
    return resampled


def _compute_zscore_anomalies(
    transactions: Sequence[Transaction],
    threshold: float,
) -> List[dict]:
    """Internal helper computing z-score anomalies for a given threshold."""
    df = _to_dataframe(transactions)
    if df.empty:
        return []

    amounts = df["amount"]
    mean = amounts.mean()
    std = amounts.std(ddof=0)
    if std == 0:
        return []

    df["z_score"] = (amounts - mean) / std
    anomalies = df[np.abs(df["z_score"]) >= threshold]
    results: List[dict] = []
    for _, row in anomalies.iterrows():
        z_val = float(row["z_score"])
        results.append(
            {
                "transaction_id": row["id"],
                "date": row["date"].date(),
                "category": row["category"],
                "merchant": row["merchant"],
                "amount": float(row["amount"]),
                "z_score": z_val,
                "reason": f"高于平均值 {abs(z_val):.1f}σ",
                "status": "new",
            }
        )
    return results


def compute_anomaly_report(
    transactions: Iterable[Transaction],
    *,
    base_threshold: float = 2.5,
    whitelist_merchants: Iterable[str] | None = None,
) -> Dict[str, object]:
    """
    Generate anomaly detection results along with contextual metadata.

    Returns a dictionary containing:
    - items: List[dict] 异常记录
    - threshold_used: float 实际使用的阈值
    - adaptive: bool 是否动态调整过阈值
    - sample_size: int 用于检测的交易数
    - sensitivity: str 检测灵敏度（normal / reduced）
    - message: Optional[str] 提示文案
    """
    transactions = list(transactions)
    merchant_whitelist: Set[str] = {
        m.strip() for m in whitelist_merchants or [] if m.strip()
    }
    filtered = [txn for txn in transactions if txn.merchant not in merchant_whitelist]
    sample_size = len(filtered)

    report: Dict[str, object] = {
        "items": [],
        "threshold_used": base_threshold,
        "adaptive": False,
        "sample_size": sample_size,
        "sensitivity": "normal",
    }

    if sample_size < 3:
        report["message"] = "spending.message_insufficient_data"
        return report

    applied_threshold = base_threshold
    if sample_size < 10:
        applied_threshold = max(base_threshold, 3.0)
        report["sensitivity"] = "reduced"
        report["message"] = "spending.message_reduced_sensitivity"

    anomalies = _compute_zscore_anomalies(filtered, applied_threshold)

    if not anomalies and sample_size >= 10:
        for candidate in (2.0, 1.5):
            if candidate >= applied_threshold:
                continue
            candidate_anomalies = _compute_zscore_anomalies(filtered, candidate)
            if candidate_anomalies:
                anomalies = candidate_anomalies
                applied_threshold = candidate
                report["adaptive"] = True
                break

    if anomalies:
        for item in anomalies:
            item["threshold_used"] = applied_threshold
        report["items"] = anomalies
        report["threshold_used"] = applied_threshold
    else:
        report.setdefault("message", "spending.anomaly_no_detect")

    return report


def detect_anomalies(
    transactions: Iterable[Transaction],
    *,
    threshold: float = 2.5,
    whitelist_merchants: Iterable[str] | None = None,
) -> List[dict]:
    """Backward compatible wrapper returning仅异常列表."""
    report = compute_anomaly_report(
        transactions,
        base_threshold=threshold,
        whitelist_merchants=whitelist_merchants,
    )
    return list(report["items"])


def _month_over_month_insight(df: pd.DataFrame) -> SpendingInsight | None:
    """Compose insight comparing latest month to previous."""
    if df.empty:
        return None

    monthly = df.copy()
    monthly["year_month"] = monthly["date"].dt.to_period("M")
    month_totals = (
        monthly.groupby(["year_month", "category"])["amount"].sum().reset_index()
    )
    if month_totals["year_month"].nunique() < 2:
        return None

    month_totals.sort_values("year_month", inplace=True)
    latest_period = month_totals["year_month"].iloc[-1]
    previous_period = month_totals["year_month"].iloc[-2]

    latest = month_totals[month_totals["year_month"] == latest_period]
    prev = month_totals[month_totals["year_month"] == previous_period]

    merged = latest.merge(
        prev,
        on="category",
        how="left",
        suffixes=("_latest", "_prev"),
    )
    merged.fillna(0, inplace=True)
    if merged.empty:
        return None

    merged["delta_pct"] = np.where(
        merged["amount_prev"] == 0,
        np.inf,
        (merged["amount_latest"] - merged["amount_prev"]) / merged["amount_prev"] * 100,
    )
    top = merged.loc[merged["delta_pct"].idxmax()]
    if not np.isfinite(top["delta_pct"]):
        return None

    category = top["category"]
    delta_pct = top["delta_pct"]
    return SpendingInsight(
        title="分类支出变化",
        detail=f"您本月在「{category}」上的支出比上月增加了约 {delta_pct:.1f}%。",
    )


def _recent_average_insight(df: pd.DataFrame, days: int = 3) -> SpendingInsight | None:
    """Generate insight on recent rolling average spending."""
    if df.empty:
        return None

    latest_date = df["date"].max()
    window_start = latest_date - pd.Timedelta(days=days - 1)

    recent = df[df["date"] >= window_start]
    if recent.empty:
        return None

    avg = recent["amount"].mean()
    return SpendingInsight(
        title="近期开销趋势",
        detail=f"最近 {days} 天的平均日消费约为 ¥{avg:.2f}。",
    )


def generate_insights(transactions: Iterable[Transaction]) -> List[SpendingInsight]:
    """Produce high-level talking points for the dashboard."""
    transactions = list(transactions)
    if not transactions:
        return []

    df = _to_dataframe(transactions)
    if df.empty:
        return []

    insights: List[SpendingInsight] = []

    totals = calculate_category_totals(transactions)
    if totals:
        top_category = max(totals, key=totals.get)
        insights.append(
            SpendingInsight(
                title="消费集中度提示",
                detail=f"目前「{top_category}」类别的支出最高，约为 ¥{totals[top_category]:.2f}。",
            )
        )

    mom_insight = _month_over_month_insight(df)
    if mom_insight:
        insights.append(mom_insight)

    recent_insight = _recent_average_insight(df)
    if recent_insight:
        insights.append(recent_insight)

    return insights
