from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.config.schemas import load_project_config
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging


OUTPUT_NAMES = [
    "feature_contract",
    "feature_contract_summary",
    "feature_contract_map_readiness",
    "feature_contract_modeling_readiness",
    "feature_contract_dashboard_readiness",
    "feature_contract_unknowns",
    "feature_contract_audit",
]

DEFAULT_CONTRACT_VERSION = "v1"
DEFAULT_HORIZONS = [15, 25, 35, 45, 55, 65]
ROUND_DATASETS = {
    "round_features_mvp": "round_features/round_features_mvp.parquet",
    "round_features_t_side_all": "round_features/round_features_t_side_all.parquet",
    "round_features_t_side_planted": "round_features/round_features_t_side_planted.parquet",
}
OPTIONAL_INPUTS = {
    "baseline_feature_sets": "modeling/t_side_ab_baseline/ab_model_feature_sets.parquet",
    "baseline_importance": "modeling/t_side_ab_baseline/ab_model_feature_importance.parquet",
    "stability": "modeling/t_side_ab_error_analysis/ab_feature_importance_stability.parquet",
    "refined_feature_sets": "modeling/t_side_ab_refined_experiment/ab_refined_feature_sets.parquet",
    "candidate_feature_set": "modeling/t_side_ab_candidate/candidate_model_feature_set.parquet",
    "candidate_importance": "modeling/t_side_ab_candidate/candidate_model_feature_importance.parquet",
}
IDENTIFIER_COLUMNS = {
    "round_feature_id",
    "round_id",
    "parse_id",
    "dem_file_id",
    "series_id",
    "local_archive_id",
    "hltv_match_id",
    "source_parse_id",
    "dataset_type",
}
LEAKAGE_TOKENS = [
    "target_site",
    "label",
    "winner",
    "outcome",
    "round_failure",
    "bomb_planted",
    "bombsite",
    "plant",
    "post",
    "quality",
    "audit",
]
REGION_TOKENS = {
    "mid_control": ["mid_control", "mid"],
    "a_pressure": ["a_pressure"],
    "b_pressure": ["b_pressure"],
    "ct_space": ["ct_space"],
    "site_a": ["site_a", "a_site"],
    "site_b": ["site_b", "b_site"],
    "rotation": ["rotation"],
    "connector": ["connector"],
}
MIRAGE_SPECIFIC_TERMS = {
    "palace",
    "apartments",
    "connector",
    "underpass",
    "window",
    "catwalk",
    "short",
    "ramp",
}


def run_feature_contract(
    config_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    target_map: str | None = None,
    contract_version: str = DEFAULT_CONTRACT_VERSION,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    target_map = target_map or project.target_maps[0]
    project_root = config_path.resolve().parent.parent
    gold_dir = project.parsed_silver_dir.parent.parent / "gold"
    inputs, missing_optional = load_inputs(gold_dir)
    feature_catalog = inputs["feature_catalog"]
    datasets = inputs["round_datasets"]
    if feature_catalog.empty:
        raise FileNotFoundError("Required input missing: t_side_feature_catalog")
    if not datasets:
        raise FileNotFoundError("At least one round feature dataset is required for the feature contract.")

    contract = build_contract(
        feature_catalog,
        datasets,
        inputs,
        contract_version=contract_version,
        target_map=target_map,
    )
    frames = {
        "feature_contract": contract,
        "feature_contract_summary": build_summary(contract),
        "feature_contract_map_readiness": build_map_readiness(contract),
        "feature_contract_modeling_readiness": build_modeling_readiness(contract, inputs["candidate_importance"]),
        "feature_contract_dashboard_readiness": build_dashboard_readiness(contract),
        "feature_contract_unknowns": build_unknowns(contract),
    }
    frames["feature_contract_audit"] = build_audit(
        contract,
        frames["feature_contract_unknowns"],
        missing_optional=missing_optional,
        contract_version=contract_version,
    )

    outputs: dict[str, Path] = {}
    if not dry_run:
        output_dir = gold_dir / "features" / "feature_contract"
        outputs.update(write_outputs(frames, output_dir, force=force))
        outputs["config_yaml"] = write_text(
            yaml.safe_dump(build_config_yaml(contract, contract_version), sort_keys=False, allow_unicode=False),
            project_root / "configs" / "features" / "feature_contract.yaml",
            force=force,
        )
        outputs["report"] = write_text(
            build_markdown_report(frames),
            project_root / "docs" / "feature_contract.md",
            force=force,
        )
        outputs["notebook"] = write_text(
            build_notebook_json(),
            project_root / "notebooks" / "14_feature_contract.ipynb",
            force=force,
        )

    summary = {
        "total_features": len(contract),
        "modeling_allowed_features": int(contract["modeling_allowed"].sum()),
        "dashboard_allowed_features": int(contract["dashboard_allowed"].sum()),
        "unknown_rows": len(frames["feature_contract_unknowns"]),
        "map_abstract_features": int(contract["map_scope"].eq("map_abstract").sum()),
        "mirage_specific_features": int(contract["mirage_specific"].sum()),
        "output_tables": len(frames),
    }
    return frames, outputs, summary


def load_inputs(gold_dir: Path) -> tuple[dict[str, Any], list[str]]:
    feature_catalog_path = gold_dir / "analysis" / "t_side_tactical_eda" / "t_side_feature_catalog.parquet"
    feature_catalog = read_catalog(feature_catalog_path) if feature_catalog_path.exists() else pd.DataFrame()
    datasets: dict[str, pd.DataFrame] = {}
    for name, relative in ROUND_DATASETS.items():
        path = gold_dir / relative
        if path.exists():
            datasets[name] = read_catalog(path)

    missing_optional: list[str] = []
    optional_frames: dict[str, pd.DataFrame] = {}
    for name, relative in OPTIONAL_INPUTS.items():
        path = gold_dir / relative
        if path.exists():
            optional_frames[name] = read_catalog(path)
        else:
            optional_frames[name] = pd.DataFrame()
            missing_optional.append(name)
    return {"feature_catalog": feature_catalog, "round_datasets": datasets, **optional_frames}, missing_optional


def build_contract(
    feature_catalog: pd.DataFrame,
    datasets: dict[str, pd.DataFrame],
    inputs: dict[str, Any],
    *,
    contract_version: str,
    target_map: str,
) -> pd.DataFrame:
    catalog = catalog_lookup(feature_catalog)
    source_tables = collect_source_tables(feature_catalog, datasets)
    data_types = collect_data_types(datasets)
    baseline_features = collect_feature_set_names(inputs["baseline_feature_sets"]) | collect_feature_set_names(
        inputs["refined_feature_sets"]
    )
    candidate_features = collect_candidate_feature_names(inputs["candidate_feature_set"]) | set(
        inputs["candidate_importance"].get("feature_name", pd.Series(dtype=str)).dropna().astype(str)
    )
    importance_features = (
        set(inputs["baseline_importance"].get("feature_name", pd.Series(dtype=str)).dropna().astype(str))
        | set(inputs["candidate_importance"].get("feature_name", pd.Series(dtype=str)).dropna().astype(str))
    )
    features = sorted(set(source_tables) | set(catalog) | baseline_features | candidate_features | importance_features)
    rows = []
    for feature_name in features:
        info = catalog.get(feature_name, {})
        family = normalize_family(feature_name, info.get("inferred_feature_group"))
        window_start, window_end, window_type = infer_window(feature_name, info)
        leakage_risk = classify_leakage(feature_name, family, info)
        modeling_allowed = is_modeling_allowed(feature_name, family, leakage_risk, info)
        dashboard_allowed = is_dashboard_allowed(feature_name, family, leakage_risk)
        region_dependency, region_semantic = infer_region(feature_name, family)
        mirage_specific = is_mirage_specific(feature_name, family)
        map_scope = classify_map_scope(region_dependency, mirage_specific, feature_name)
        lifecycle_phase = classify_lifecycle(feature_name, family, leakage_risk, window_end)
        minimum_horizon = minimum_prediction_horizon(window_end, lifecycle_phase, modeling_allowed)
        status = feature_status(modeling_allowed, dashboard_allowed, leakage_risk, map_scope, family)
        rows.append(
            {
                "feature_contract_version": contract_version,
                "feature_name": feature_name,
                "feature_family": family,
                "semantic_role": semantic_role(feature_name, family, region_semantic),
                "description": describe_feature(feature_name, family, region_semantic, window_start, window_end, window_type),
                "source_tables": "|".join(source_tables.get(feature_name, [])),
                "data_type": data_types.get(feature_name, "unknown"),
                "side_scope": side_scope(source_tables.get(feature_name, [])),
                "lifecycle_phase": lifecycle_phase,
                "temporal": pd.notna(window_end),
                "window_start": window_start,
                "window_end": window_end,
                "window_type": window_type,
                "map_scope": map_scope,
                "region_dependency": region_dependency,
                "region_semantic": region_semantic,
                "mirage_specific": mirage_specific,
                "modeling_allowed": modeling_allowed,
                "dashboard_allowed": dashboard_allowed,
                "leakage_risk": leakage_risk,
                "minimum_prediction_horizon": minimum_horizon,
                **horizon_flags(window_end, modeling_allowed, minimum_horizon),
                "feature_status": status,
                "used_in_stage6_baseline": feature_name in baseline_features,
                "used_in_stage6_candidate": feature_name in candidate_features,
                "importance_available": feature_name in importance_features,
                "notes": notes_for_feature(feature_name, target_map, map_scope, leakage_risk, region_dependency, info),
            }
        )
    return pd.DataFrame(rows).sort_values("feature_name").reset_index(drop=True)


def catalog_lookup(feature_catalog: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if feature_catalog.empty or "column_name" not in feature_catalog.columns:
        return {}
    return feature_catalog.drop_duplicates("column_name").set_index("column_name").to_dict("index")


def collect_source_tables(feature_catalog: pd.DataFrame, datasets: dict[str, pd.DataFrame]) -> dict[str, list[str]]:
    sources: dict[str, set[str]] = {}
    if "column_name" in feature_catalog.columns:
        for feature_name in feature_catalog["column_name"].dropna().astype(str):
            sources.setdefault(feature_name, set()).add("t_side_feature_catalog")
    for table_name, frame in datasets.items():
        for column in frame.columns:
            sources.setdefault(str(column), set()).add(table_name)
    return {feature_name: sorted(values) for feature_name, values in sources.items()}


def collect_data_types(datasets: dict[str, pd.DataFrame]) -> dict[str, str]:
    result: dict[str, str] = {}
    for frame in datasets.values():
        for column in frame.columns:
            result.setdefault(str(column), str(frame[column].dtype))
    return result


def collect_feature_set_names(frame: pd.DataFrame) -> set[str]:
    if frame.empty or "selected_feature_names" not in frame.columns:
        return set()
    features: set[str] = set()
    for value in frame["selected_feature_names"].dropna().astype(str):
        features.update(item for item in value.split("|") if item and not item.startswith("__"))
    return features


def collect_candidate_feature_names(frame: pd.DataFrame) -> set[str]:
    if frame.empty or "feature_name" not in frame.columns:
        return set()
    return {name for name in frame["feature_name"].dropna().astype(str) if not name.startswith("__")}


def normalize_family(feature_name: str, catalog_group: Any) -> str:
    group = str(catalog_group or "").casefold()
    name = feature_name.casefold()
    if group == "region_position":
        return "region_position"
    if group == "utility":
        return "utility"
    if group == "bomb":
        return "bomb"
    if group == "death":
        return "death"
    if group == "label":
        return "label"
    if group == "outcome":
        return "outcome"
    if group == "audit":
        return "quality"
    if feature_name in IDENTIFIER_COLUMNS or any(token in name for token in ["id", "parse", "series"]):
        return "identity"
    if any(token in name for token in ["money", "armor", "helmet", "defuser", "equipment"]):
        return "economy"
    if any(token in name for token in ["inventory", "smokes_start", "flashes_start", "molotovs_start", "he_start"]):
        return "inventory"
    if any(token in name for token in ["kill", "damage", "assist", "combat"]):
        return "combat"
    if any(token in name for token in ["progression", "signature"]):
        return "progression"
    if any(token in name for token in ["target_team", "opponent", "team_", "side"]):
        return "team_context"
    if any(token in name for token in ["round_num", "half", "score", "map_name"]):
        return "round_context"
    return "other"


def infer_window(feature_name: str, info: dict[str, Any]) -> tuple[int | None, int | None, str | None]:
    start = value_to_int(info.get("window_start"))
    end = value_to_int(info.get("window_end"))
    window_type = none_if_nan(info.get("window_type"))
    if end is not None:
        return start or 0, end, str(window_type or ("cumulative" if (start or 0) == 0 else "interval"))
    match = re.search(r"_(\d+)_(\d+)$", feature_name)
    if match:
        parsed_start, parsed_end = int(match[1]), int(match[2])
        return parsed_start, parsed_end, "cumulative" if parsed_start == 0 else "interval"
    point = re.search(r"_(\d+)s$", feature_name)
    if point:
        return 0, int(point[1]), "point"
    return None, None, None


def none_if_nan(value: Any) -> Any:
    return None if value is None or pd.isna(value) else value


def value_to_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)


def classify_leakage(feature_name: str, family: str, info: dict[str, Any]) -> str:
    name = feature_name.casefold()
    if feature_name in IDENTIFIER_COLUMNS or family == "identity":
        return "identifier"
    if family == "label" or "label" in name or "target_site" in name:
        return "label"
    if any(token in name for token in ["winner", "outcome", "round_end_reason", "round_failure"]):
        return "post_outcome"
    if "plant" in name or "bombsite" in name:
        return "known"
    if family == "quality" or any(token in name for token in ["quality", "audit", "notes"]):
        return "possible"
    if none_if_nan(info.get("usable_for_future_model")) is False:
        return "possible"
    return "none"


def is_modeling_allowed(feature_name: str, family: str, leakage_risk: str, info: dict[str, Any]) -> bool:
    if feature_name in IDENTIFIER_COLUMNS:
        return False
    if leakage_risk != "none":
        return False
    if family in {"identity", "label", "outcome", "quality"}:
        return False
    catalog_usable = none_if_nan(info.get("usable_for_future_model"))
    if catalog_usable is not None and not bool(catalog_usable):
        return False
    return True


def is_dashboard_allowed(feature_name: str, family: str, leakage_risk: str) -> bool:
    if feature_name in IDENTIFIER_COLUMNS or leakage_risk == "identifier":
        return False
    if family == "quality":
        return False
    return True


def infer_region(feature_name: str, family: str) -> tuple[bool, str | None]:
    name = feature_name.casefold()
    for semantic, tokens in REGION_TOKENS.items():
        if any(token in name for token in tokens):
            return True, semantic
    for term in MIRAGE_SPECIFIC_TERMS:
        if term in name and family in {"region_position", "bomb", "death", "progression", "utility"}:
            return True, f"mirage_{term}"
    if family == "region_position" and any(token in name for token in ["region", "pressure", "control", "space"]):
        return True, "unknown"
    return False, None


def is_mirage_specific(feature_name: str, family: str) -> bool:
    name = feature_name.casefold()
    return family in {"region_position", "bomb", "death", "progression", "utility"} and any(
        term in name for term in MIRAGE_SPECIFIC_TERMS
    )


def classify_map_scope(region_dependency: bool, mirage_specific: bool, feature_name: str) -> str:
    if mirage_specific:
        return "map_specific"
    if region_dependency:
        return "map_abstract"
    if feature_name:
        return "global"
    return "unknown"


def classify_lifecycle(feature_name: str, family: str, leakage_risk: str, window_end: int | None) -> str:
    name = feature_name.casefold()
    if family in {"identity", "quality"}:
        return "metadata"
    if leakage_risk in {"label", "post_outcome"} or family in {"label", "outcome"}:
        return "post_round"
    if "post" in name:
        return "post_plant"
    if window_end is not None:
        return "in_round"
    if any(token in name for token in ["_start", "round_num", "half", "score_diff_before_round", "is_pistol"]):
        return "pre_round"
    return "unknown"


def minimum_prediction_horizon(window_end: int | None, lifecycle_phase: str, modeling_allowed: bool) -> int | None:
    if not modeling_allowed:
        return None
    if window_end is not None:
        return window_end
    if lifecycle_phase == "pre_round":
        return 0
    return None


def horizon_flags(window_end: int | None, modeling_allowed: bool, minimum_horizon: int | None) -> dict[str, bool]:
    return {
        f"horizon_{horizon}_allowed": bool(modeling_allowed and minimum_horizon is not None and minimum_horizon <= horizon)
        for horizon in DEFAULT_HORIZONS
    }


def feature_status(
    modeling_allowed: bool,
    dashboard_allowed: bool,
    leakage_risk: str,
    map_scope: str,
    family: str,
) -> str:
    if leakage_risk in {"identifier", "label", "post_outcome", "known"}:
        return "blocked"
    if family in {"identity", "quality"}:
        return "internal"
    if modeling_allowed and map_scope in {"global", "map_abstract"}:
        return "frozen"
    if dashboard_allowed:
        return "exploratory"
    return "blocked"


def semantic_role(feature_name: str, family: str, region_semantic: str | None) -> str:
    name = feature_name.casefold()
    if family == "region_position":
        if region_semantic in {"a_pressure", "b_pressure", "site_a", "site_b"}:
            return "site_pressure"
        return "spatial_control"
    if family == "utility":
        return "utility_inventory" if name.endswith("_start") else "utility_usage"
    if family == "bomb":
        return "bomb_progression"
    if family in {"combat", "death"}:
        return "combat_state"
    if family in {"round_context", "team_context"}:
        return "round_context"
    if family == "identity":
        return "identity"
    if family == "label":
        return "target_label"
    if family == "outcome":
        return "post_round_outcome"
    return "other"


def describe_feature(
    feature_name: str,
    family: str,
    region_semantic: str | None,
    window_start: int | None,
    window_end: int | None,
    window_type: str | None,
) -> str:
    region_text = f" for {region_semantic}" if region_semantic else ""
    window_text = f" during {window_start}-{window_end}s ({window_type})" if window_end is not None else ""
    return f"{feature_name} is a {family} feature{region_text}{window_text}."


def side_scope(source_tables: list[str]) -> str:
    if source_tables and all("t_side" in table for table in source_tables if table.startswith("round_features")):
        return "t_side"
    if any(table == "round_features_t_side_planted" for table in source_tables):
        return "t_side"
    return "all_sides"


def notes_for_feature(
    feature_name: str,
    target_map: str,
    map_scope: str,
    leakage_risk: str,
    region_dependency: bool,
    info: dict[str, Any],
) -> str:
    notes = []
    if region_dependency:
        notes.append("Requires active map region semantics.")
    if map_scope == "map_specific":
        notes.append(f"Conservatively treated as {target_map}-specific until Stage 8.1 registry defines portability.")
    if leakage_risk != "none":
        notes.append(f"Blocked or reviewed for leakage risk: {leakage_risk}.")
    catalog_notes = none_if_nan(info.get("notes"))
    if catalog_notes:
        notes.append(str(catalog_notes))
    if not notes:
        notes.append("Classified automatically from current MVP feature inventory.")
    return " ".join(notes)


def build_summary(contract: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for group_type in ["feature_family", "map_scope", "feature_status", "modeling_allowed", "dashboard_allowed"]:
        for group_value, group in contract.groupby(group_type, dropna=False):
            rows.append(summary_row(group_type, group_value, group))
    return pd.DataFrame(rows)


def summary_row(group_type: str, group_value: Any, group: pd.DataFrame) -> dict[str, Any]:
    return {
        "group_type": group_type,
        "group_value": str(group_value),
        "feature_count": len(group),
        "temporal_features": int(group["temporal"].sum()),
        "modeling_features": int(group["modeling_allowed"].sum()),
        "dashboard_features": int(group["dashboard_allowed"].sum()),
        "mirage_specific_features": int(group["mirage_specific"].sum()),
        "unknown_features": int(group["map_scope"].eq("unknown").sum() + group["region_semantic"].eq("unknown").sum()),
    }


def build_map_readiness(contract: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in contract.iterrows():
        requires_registry = bool(row["map_scope"] == "map_abstract" or row["region_dependency"])
        ready = bool(row["map_scope"] == "global")
        if row["map_scope"] == "map_abstract":
            reason = "requires_map_registry"
            action = "Define equivalent semantic region per map in Stage 8.1."
        elif row["map_scope"] == "map_specific":
            reason = "map_specific_region_or_term"
            action = "Create explicit portability decision or map-specific equivalent."
        elif row["map_scope"] == "unknown":
            reason = "unknown_map_scope"
            action = "Manually classify before map expansion."
        else:
            reason = "none"
            action = "Ready for reuse across maps."
        rows.append(
            {
                "feature_name": row["feature_name"],
                "map_scope": row["map_scope"],
                "region_dependency": row["region_dependency"],
                "region_semantic": row["region_semantic"],
                "mirage_specific": row["mirage_specific"],
                "requires_map_registry": requires_registry,
                "ready_for_new_map": ready,
                "blocking_reason": reason,
                "recommended_action": action,
            }
        )
    return pd.DataFrame(rows)


def build_modeling_readiness(contract: pd.DataFrame, candidate_importance: pd.DataFrame) -> pd.DataFrame:
    importance = candidate_importance_lookup(candidate_importance)
    rows = []
    for _, row in contract.iterrows():
        feature_name = row["feature_name"]
        imp = importance.get(feature_name, {})
        rows.append(
            {
                "feature_name": feature_name,
                "modeling_allowed": row["modeling_allowed"],
                "leakage_risk": row["leakage_risk"],
                "minimum_prediction_horizon": row["minimum_prediction_horizon"],
                "used_in_stage6_baseline": row["used_in_stage6_baseline"],
                "used_in_stage6_candidate": row["used_in_stage6_candidate"],
                "candidate_importance_rank": imp.get("importance_rank"),
                "candidate_importance_value": imp.get("importance_value"),
                "modeling_status": modeling_status(row),
                "notes": row["notes"],
            }
        )
    return pd.DataFrame(rows)


def candidate_importance_lookup(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if frame.empty or "feature_name" not in frame.columns:
        return {}
    return frame.drop_duplicates("feature_name").set_index("feature_name").to_dict("index")


def modeling_status(row: pd.Series) -> str:
    if row["leakage_risk"] == "identifier":
        return "blocked_identifier"
    if row["leakage_risk"] != "none":
        return "blocked_leakage"
    if bool(row["modeling_allowed"]):
        return "approved" if bool(row["used_in_stage6_candidate"] or row["used_in_stage6_baseline"]) else "unused"
    if row["feature_status"] == "exploratory":
        return "exploratory"
    return "unknown"


def build_dashboard_readiness(contract: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in contract.iterrows():
        rows.append(
            {
                "feature_name": row["feature_name"],
                "feature_family": row["feature_family"],
                "semantic_role": row["semantic_role"],
                "dashboard_allowed": row["dashboard_allowed"],
                "map_scope": row["map_scope"],
                "temporal": row["temporal"],
                "recommended_visualization_role": visualization_role(row),
                "recommended_filter_role": filter_role(row),
                "dashboard_status": "approved" if row["dashboard_allowed"] else "not_recommended",
            }
        )
    return pd.DataFrame(rows)


def visualization_role(row: pd.Series) -> str:
    if not bool(row["dashboard_allowed"]):
        return "not_recommended"
    if bool(row["temporal"]):
        return "timeseries"
    if row["importance_available"]:
        return "feature_importance"
    if row["feature_family"] in {"label", "outcome", "round_context", "team_context"}:
        return "comparison"
    return "metric"


def filter_role(row: pd.Series) -> str:
    if row["feature_family"] in {"round_context", "team_context"}:
        return "filter"
    if row["region_dependency"]:
        return "map_region_filter"
    return "none"


def build_unknowns(contract: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in contract.iterrows():
        if row["feature_family"] == "other":
            rows.append(unknown_row(row["feature_name"], "feature_family", "other", "No confident family classification.", "Classify manually before expansion.", "medium"))
        if row["map_scope"] == "unknown":
            rows.append(unknown_row(row["feature_name"], "map_scope", "unknown", "Map portability is unclear.", "Decide global/map_abstract/map_specific.", "high"))
        if row["region_semantic"] == "unknown":
            rows.append(unknown_row(row["feature_name"], "region_semantic", "unknown", "Region dependency found but semantic region is unclear.", "Map feature to known region semantic.", "medium"))
        if row["lifecycle_phase"] == "unknown":
            rows.append(unknown_row(row["feature_name"], "lifecycle_phase", "unknown", "Lifecycle phase could not be inferred.", "Set pre_round/in_round/post_* manually.", "low"))
    return pd.DataFrame(rows, columns=["feature_name", "unknown_field", "current_value", "reason", "recommended_manual_action", "severity"])


def unknown_row(
    feature_name: str,
    unknown_field: str,
    current_value: str,
    reason: str,
    recommended_manual_action: str,
    severity: str,
) -> dict[str, str]:
    return {
        "feature_name": feature_name,
        "unknown_field": unknown_field,
        "current_value": current_value,
        "reason": reason,
        "recommended_manual_action": recommended_manual_action,
        "severity": severity,
    }


def build_audit(
    contract: pd.DataFrame,
    unknowns: pd.DataFrame,
    *,
    missing_optional: list[str],
    contract_version: str,
) -> pd.DataFrame:
    status = "warning" if missing_optional or not unknowns.empty else "ok"
    return pd.DataFrame(
        [
            {
                "audit_id": "feature_contract_freeze",
                "feature_contract_version": contract_version,
                "total_features": len(contract),
                "frozen_features": int(contract["feature_status"].eq("frozen").sum()),
                "exploratory_features": int(contract["feature_status"].eq("exploratory").sum()),
                "deprecated_features": int(contract["feature_status"].eq("deprecated").sum()),
                "internal_features": int(contract["feature_status"].eq("internal").sum()),
                "blocked_features": int(contract["feature_status"].eq("blocked").sum()),
                "global_features": int(contract["map_scope"].eq("global").sum()),
                "map_abstract_features": int(contract["map_scope"].eq("map_abstract").sum()),
                "map_specific_features": int(contract["map_scope"].eq("map_specific").sum()),
                "unknown_map_scope": int(contract["map_scope"].eq("unknown").sum()),
                "modeling_allowed_features": int(contract["modeling_allowed"].sum()),
                "dashboard_allowed_features": int(contract["dashboard_allowed"].sum()),
                "temporal_features": int(contract["temporal"].sum()),
                "mirage_specific_features": int(contract["mirage_specific"].sum()),
                "features_requiring_map_registry": int(contract["region_dependency"].sum()),
                "unknown_classification_rows": len(unknowns),
                "missing_optional_inputs": "|".join(missing_optional) if missing_optional else "none",
                "config_written": True,
                "report_written": True,
                "status": status,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )


def build_config_yaml(contract: pd.DataFrame, contract_version: str) -> dict[str, Any]:
    columns = [
        "feature_name",
        "feature_family",
        "semantic_role",
        "side_scope",
        "lifecycle_phase",
        "temporal",
        "window_start",
        "window_end",
        "window_type",
        "map_scope",
        "region_dependency",
        "region_semantic",
        "modeling_allowed",
        "dashboard_allowed",
        "leakage_risk",
        "feature_status",
    ]
    features = []
    for row in contract[columns].to_dict("records"):
        features.append({key: clean_yaml_value(value) for key, value in row.items() if clean_yaml_value(value) is not None})
    return {
        "feature_contract_version": contract_version,
        "default_feature_policy": {
            "modeling_allowed": False,
            "dashboard_allowed": True,
            "status": "exploratory",
        },
        "features": features,
    }


def clean_yaml_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def build_markdown_report(frames: dict[str, pd.DataFrame]) -> str:
    contract = frames["feature_contract"]
    summary = frames["feature_contract_summary"]
    map_readiness = frames["feature_contract_map_readiness"]
    modeling = frames["feature_contract_modeling_readiness"]
    dashboard = frames["feature_contract_dashboard_readiness"]
    unknowns = frames["feature_contract_unknowns"]
    audit = frames["feature_contract_audit"]
    return "\n".join(
        [
            "# Feature Contract -- CS2 Tactical Analytics",
            "",
            "## Purpose",
            "Freeze the current MVP feature inventory as metadata without changing existing feature values.",
            "",
            "## Why the feature contract exists",
            "The contract separates modeling safety, dashboard usefulness, map portability, and leakage policy before map expansion.",
            "",
            "## Current feature inventory",
            markdown_table(audit, list(audit.columns)),
            "",
            "## Feature families",
            markdown_table(summary[summary["group_type"].eq("feature_family")], list(summary.columns), top_n=30),
            "",
            "## Temporal features",
            markdown_table(contract[contract["temporal"]], ["feature_name", "feature_family", "window_start", "window_end", "window_type", "minimum_prediction_horizon"], top_n=30),
            "",
            "## Leakage policy",
            "Labels, identifiers, post-round outcomes, plant result fields, quality/audit metadata, and known leakage fields are blocked from modeling.",
            "",
            "## Modeling-safe features",
            markdown_table(modeling[modeling["modeling_allowed"]], ["feature_name", "minimum_prediction_horizon", "used_in_stage6_candidate", "modeling_status"], top_n=30),
            "",
            "## Dashboard-safe features",
            markdown_table(dashboard[dashboard["dashboard_allowed"]], ["feature_name", "semantic_role", "recommended_visualization_role", "recommended_filter_role"], top_n=30),
            "",
            "## Map portability",
            markdown_table(summary[summary["group_type"].eq("map_scope")], list(summary.columns)),
            "",
            "## Global features",
            markdown_table(contract[contract["map_scope"].eq("global")], ["feature_name", "feature_family", "modeling_allowed", "dashboard_allowed"], top_n=25),
            "",
            "## Map-abstract features",
            markdown_table(contract[contract["map_scope"].eq("map_abstract")], ["feature_name", "region_semantic", "modeling_allowed", "requires_map_registry" if "requires_map_registry" in contract.columns else "notes"], top_n=25),
            "",
            "## Mirage-specific features",
            markdown_table(contract[contract["mirage_specific"]], ["feature_name", "region_semantic", "feature_status", "notes"], top_n=25),
            "",
            "## Features requiring map registry",
            markdown_table(map_readiness[map_readiness["requires_map_registry"]], ["feature_name", "map_scope", "region_semantic", "recommended_action"], top_n=30),
            "",
            "## Unknown / review queue",
            markdown_table(unknowns, list(unknowns.columns), top_n=30),
            "",
            "## Frozen contract",
            "`configs/features/feature_contract.yaml` stores the frozen contract subset for future stages.",
            "",
            "## Next stage",
            "Next: Stage 8.1 -- Map Geometry & Region Registry",
            "",
        ]
    )


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int = 20) -> str:
    if frame.empty:
        return "_No rows available._"
    available = [column for column in columns if column in frame.columns]
    return frame[available].head(top_n).to_markdown(index=False)


def build_notebook_json() -> str:
    cells = [
        markdown_cell("# Stage 8.0 -- Feature Contract & Freeze\n\nInspect the frozen feature contract."),
        code_cell(
            "from pathlib import Path\n\n"
            "import matplotlib.pyplot as plt\n"
            "import pandas as pd\n\n"
            "BASE = Path('../data/gold/features/feature_contract')\n\n"
            "def load_table(name):\n"
            "    return pd.read_parquet(BASE / f'{name}.parquet')\n\n"
            "contract = load_table('feature_contract')\n"
            "summary = load_table('feature_contract_summary')\n"
            "map_readiness = load_table('feature_contract_map_readiness')\n"
            "modeling = load_table('feature_contract_modeling_readiness')\n"
            "dashboard = load_table('feature_contract_dashboard_readiness')\n"
            "unknowns = load_table('feature_contract_unknowns')\n"
            "audit = load_table('feature_contract_audit')"
        ),
        markdown_cell("## Total Features"),
        code_cell("display(audit)\nprint(f\"total features: {len(contract)}\")"),
        markdown_cell("## Feature Families"),
        code_cell(
            "family_counts = contract['feature_family'].value_counts().sort_values()\n"
            "display(family_counts.rename_axis('feature_family').reset_index(name='features'))\n"
            "family_counts.plot.barh(figsize=(8, 6), title='Feature families')\n"
            "plt.tight_layout()"
        ),
        markdown_cell("## Global vs Map-abstract vs Map-specific"),
        code_cell("display(contract['map_scope'].value_counts(dropna=False).rename_axis('map_scope').reset_index(name='features'))"),
        markdown_cell("## Modeling-safe"),
        code_cell("display(contract[contract['modeling_allowed']].head(30))"),
        markdown_cell("## Dashboard-safe"),
        code_cell("display(contract[contract['dashboard_allowed']].head(30))"),
        markdown_cell("## Mirage-specific"),
        code_cell("display(contract[contract['mirage_specific']])"),
        markdown_cell("## Features Requiring Map Registry"),
        code_cell("display(map_readiness[map_readiness['requires_map_registry']])"),
        markdown_cell("## Unknowns"),
        code_cell("display(unknowns)"),
        markdown_cell("## Audit"),
        code_cell("display(audit)"),
        markdown_cell("Next: build map geometry and region registry."),
    ]
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {
                "codemirror_mode": {"name": "ipython", "version": 3},
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
                "version": "3.11",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(notebook, indent=1) + "\n"


def markdown_cell(source: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def code_cell(source: str) -> dict[str, Any]:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source.splitlines(keepends=True)}


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs: dict[str, Path] = {}
    for name in OUTPUT_NAMES:
        for suffix in ["csv", "parquet"]:
            path = output_dir / f"{name}.{suffix}"
            if force or not path.exists():
                if suffix == "csv":
                    frames[name].to_csv(path, index=False)
                else:
                    frames[name].to_parquet(path, index=False)
            outputs[f"{name}_{suffix}"] = path
    return outputs


def write_text(content: str, path: Path, *, force: bool) -> Path:
    ensure_dir(path.parent)
    if force or not path.exists():
        path.write_text(content, encoding="utf-8")
    return path


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("Feature Contract summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and freeze the current MVP feature contract.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--target-map", default=None)
    parser.add_argument("--contract-version", default=DEFAULT_CONTRACT_VERSION)
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_feature_contract(
        args.config,
        force=args.force,
        dry_run=args.dry_run,
        target_map=args.target_map,
        contract_version=args.contract_version,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
