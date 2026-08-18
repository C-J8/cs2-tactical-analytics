from __future__ import annotations

import pandas as pd


PLACE_COLUMN_CANDIDATES = ["last_place_name", "place_name", "player_last_place_name", "place"]


def detect_place_column(columns_or_frame: list[str] | pd.DataFrame) -> str | None:
    columns = list(columns_or_frame.columns) if isinstance(columns_or_frame, pd.DataFrame) else list(columns_or_frame)
    for column in PLACE_COLUMN_CANDIDATES:
        if column in columns:
            return column
    return None
