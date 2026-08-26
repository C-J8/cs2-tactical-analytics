from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_divide(numerator: object, denominator: object) -> float | None:
    try:
        if denominator is None or pd.isna(denominator) or float(denominator) == 0:
            return None
        if numerator is None or pd.isna(numerator):
            return None
        return float(numerator) / float(denominator)
    except (TypeError, ValueError):
        return None


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int | None = 20) -> str:
    if frame.empty:
        return "_No rows._"
    existing = [column for column in columns if column in frame.columns]
    if not existing:
        return "_No requested columns available._"
    view = frame[existing]
    if top_n is not None:
        view = view.head(top_n)
    return view.fillna("").to_markdown(index=False)
