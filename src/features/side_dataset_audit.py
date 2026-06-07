from __future__ import annotations

import pandas as pd


def build_side_dataset_audit(datasets: dict[str, pd.DataFrame], *, notes: dict[str, str] | None = None) -> pd.DataFrame:
    notes = notes or {}
    rows = []
    for dataset_type, df in datasets.items():
        label = df.get("target_site_model_label", pd.Series(dtype="object"))
        bomb_planted = df.get("bomb_planted", pd.Series(dtype="object")).map(normalize_bool) if "bomb_planted" in df.columns else pd.Series(dtype="bool")
        rows.append(
            {
                "dataset_type": dataset_type,
                "row_count": len(df),
                "rounds_with_label_A": int((label == "A").sum()),
                "rounds_with_label_B": int((label == "B").sum()),
                "rounds_without_label": int(label.isna().sum()),
                "rounds_with_bomb_planted": int(bomb_planted.sum()) if not bomb_planted.empty else 0,
                "rounds_without_bomb_planted": int((~bomb_planted).sum()) if not bomb_planted.empty else len(df),
                "unique_demos": int(df["parse_id"].nunique()) if "parse_id" in df.columns else 0,
                "unique_opponents": int(df["opponent"].nunique(dropna=True)) if "opponent" in df.columns else 0,
                "target_team_side_values": ",".join(sorted(df["target_team_side"].dropna().astype(str).unique())) if "target_team_side" in df.columns else "",
                "target_team_side_counts": value_counts_string(df, "target_team_side"),
                "target_site_model_label_counts": value_counts_string(df, "target_site_model_label"),
                "label_source_counts": value_counts_string(df, "label_source"),
                "bomb_planted_counts": value_counts_string(df, "bomb_planted"),
                "opponent_counts": value_counts_string(df, "opponent"),
                "series_id_counts": value_counts_string(df, "series_id"),
                "notes": notes.get(dataset_type),
            }
        )
    return pd.DataFrame(rows)


def normalize_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def value_counts_string(df: pd.DataFrame, column: str) -> str:
    if column not in df.columns or df.empty:
        return ""
    counts = df[column].value_counts(dropna=False)
    return "; ".join(f"{index}={value}" for index, value in counts.items())
