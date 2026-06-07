from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd


def build_feature_audit(
    *,
    feature_eligible: pd.DataFrame,
    round_features: pd.DataFrame,
    utility_events: pd.DataFrame,
    region_presence: pd.DataFrame,
    diagnostics: dict[str, str],
    warnings: list[str],
) -> pd.DataFrame:
    feature_columns = [column for column in round_features.columns if column not in {"round_feature_id", "parse_id", "dem_file_id", "series_id", "round_id"}]
    fully_null = [column for column in round_features.columns if round_features[column].isna().all()]
    partially_null = [column for column in round_features.columns if round_features[column].isna().any() and column not in fully_null]
    rounds_with_label = int(round_features["target_site_model_label"].isin(["A", "B"]).sum()) if "target_site_model_label" in round_features.columns else 0
    rounds_without_plant = int(round_features["target_site_model_label"].isna().sum()) if "target_site_model_label" in round_features.columns else 0
    notes = [
        "target_team player identity is not available in silver ticks; early-round features use T-side players as attacking-side proxy",
        "tickrate assumed at 64 ticks per second",
        f"grenades.parquet detected as {diagnostics.get('grenades_granularity', 'unknown')}",
        *warnings,
    ]
    return pd.DataFrame(
        [
            {
                "audit_id": "feature_engineering_mvp",
                "demos_used": len(feature_eligible),
                "rounds_generated": len(round_features),
                "rounds_with_target_site": rounds_with_label,
                "rounds_without_plant": rounds_without_plant,
                "features_generated": len(feature_columns),
                "fully_null_columns_count": len(fully_null),
                "partially_null_columns_count": len(partially_null),
                "fully_null_columns": ",".join(fully_null),
                "partially_null_columns": ",".join(partially_null),
                "warnings_count": len(warnings),
                "utility_parsing_status": "grenades_skipped_trajectory_level" if diagnostics.get("grenades_granularity") == "trajectory_level" else "ok",
                "region_mapping_status": "place_name_mapping",
                "grenades_granularity": diagnostics.get("grenades_granularity", "unknown"),
                "utility_events_rows": len(utility_events),
                "region_presence_rows": len(region_presence),
                "notes": "; ".join(notes),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )
