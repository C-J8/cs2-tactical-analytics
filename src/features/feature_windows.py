from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.config.schemas import FeatureWindowsConfig


@dataclass(frozen=True)
class FeatureWindow:
    start: int
    end: int
    window_type: str

    @property
    def suffix(self) -> str:
        return f"{self.start}_{self.end}"


def configured_feature_windows(config: FeatureWindowsConfig) -> list[FeatureWindow]:
    return [
        *[FeatureWindow(start, end, "interval") for start, end in config.interval_windows],
        *[FeatureWindow(start, end, "cumulative") for start, end in config.cumulative_windows],
    ]


def interval_feature_windows(config: FeatureWindowsConfig) -> list[FeatureWindow]:
    return [FeatureWindow(start, end, "interval") for start, end in config.interval_windows]


def max_window_end(windows: list[FeatureWindow]) -> int:
    return max((window.end for window in windows), default=0)


def filter_to_round_time(df: pd.DataFrame, *, tick_column: str, anchor_column: str = "anchor_tick", end_column: str = "round_end_tick", tickrate: float = 64.0) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    result = df.copy()
    result["seconds_from_freeze_end"] = (result[tick_column] - result[anchor_column]) / tickrate
    result = result[result["seconds_from_freeze_end"] >= 0].copy()
    if end_column in result.columns:
        result = result[result[tick_column] <= result[end_column]].copy()
    return result


def empty_windowed_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=["window_type", "window_start", "window_end", *columns])
