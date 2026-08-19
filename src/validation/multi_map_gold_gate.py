from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.config.schemas import load_project_config
from src.maps.identity import resolve_map_identity
from src.storage.scoped_gold import GOLD_DATASET_SPECS, GoldDatasetSpec, content_hash, duplicate_key_count, map_id_series, schema_hash
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging


OUTPUT_NAMES = [
    "gold_scope_inventory",
    "gold_scoped_upsert_audit",
    "gold_key_collision_audit",
    "mirage_gold_preservation",
    "inferno_feature_materialization",
    "inferno_candidate_feature_materialization",
    "inferno_semantic_feature_sanity",
    "inferno_round_state_summary",
    "inferno_side_dataset_summary",
    "multi_map_gold_audit",
]


def run_multi_map_gold_gate(
    config_path: Path,
    *,
    target_map: str,
    target_team: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    map_registry_path: Path = Path("configs/maps/map_registry.yaml"),
    mirage_before: pd.DataFrame | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, Any]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    gold_dir = project_root / "data" / "gold"
    target_team = target_team or project.target_teams[0]
    effective_registry_path = map_registry_path if map_registry_path.is_absolute() else project_root / map_registry_path
    if not effective_registry_path.exists() and not map_registry_path.is_absolute() and map_registry_path.exists():
        effective_registry_path = map_registry_path
    identity = resolve_map_identity(target_map, registry_path=effective_registry_path)
    frames_by_name = load_gold_frames(gold_dir)
    output_dir = gold_dir / "validation" / "multi_map_gold"
    if mirage_before is None:
        before_path = output_dir / "mirage_gold_preservation_before.parquet"
        mirage_before = read_catalog(before_path) if before_path.exists() else pd.DataFrame()
    round_feature_scope = scoped_team_map(frames_by_name.get("round_features_mvp", pd.DataFrame()), target_team=target_team, map_name=identity.display_name, registry_path=effective_registry_path)
    feature_ids = set(round_feature_scope.get("round_feature_id", pd.Series(dtype=str)).dropna().astype(str))
    round_ids = set(round_feature_scope.get("round_id", pd.Series(dtype=str)).dropna().astype(str))
    parse_ids = set(round_feature_scope.get("parse_id", pd.Series(dtype=str)).dropna().astype(str))

    outputs = {
        "gold_scope_inventory": build_inventory(frames_by_name, registry_path=effective_registry_path),
        "gold_scoped_upsert_audit": build_scoped_upsert_audit(frames_by_name, target_team=target_team, map_name=identity.display_name, feature_ids=feature_ids, round_ids=round_ids, parse_ids=parse_ids, registry_path=effective_registry_path),
        "gold_key_collision_audit": build_key_collision_audit(frames_by_name),
        "mirage_gold_preservation": build_mirage_preservation(frames_by_name, target_team=target_team, registry_path=effective_registry_path, before=mirage_before),
        "inferno_feature_materialization": build_feature_materialization(gold_dir, round_feature_scope, identity.map_id),
        "inferno_candidate_feature_materialization": build_candidate_materialization(gold_dir, round_feature_scope, identity.map_id),
        "inferno_semantic_feature_sanity": build_semantic_sanity(gold_dir, round_feature_scope, identity.map_id),
        "inferno_round_state_summary": build_round_state_summary(frames_by_name.get("round_state_resolved", pd.DataFrame()), target_team=target_team, map_id=identity.map_id, map_name=identity.display_name, registry_path=effective_registry_path),
        "inferno_side_dataset_summary": build_side_dataset_summary(frames_by_name, target_team=target_team, map_id=identity.map_id, map_name=identity.display_name, registry_path=effective_registry_path),
    }
    outputs["multi_map_gold_audit"] = build_final_audit(outputs, frames_by_name, identity.map_id, identity.display_name, target_team, project_root=project_root, registry_path=effective_registry_path)

    paths: dict[str, Path] = {}
    if not dry_run:
        paths.update(write_outputs(outputs, output_dir, force=force))
    summary = {
        "map_id": identity.map_id,
        "target_team": target_team,
        "inferno_round_features": len(round_feature_scope),
        "overall_status": str(outputs["multi_map_gold_audit"].iloc[0]["overall_status"]),
        "blocking_issues": int(outputs["multi_map_gold_audit"].iloc[0]["blocking_issues"]),
    }
    return outputs, paths, summary


def load_gold_frames(gold_dir: Path) -> dict[str, pd.DataFrame]:
    frames = {}
    for name, spec in GOLD_DATASET_SPECS.items():
        path = gold_dir / spec.relative_path.with_suffix(".parquet")
        frames[name] = read_catalog(path) if path.exists() else pd.DataFrame()
    return frames


def capture_scope_fingerprints(gold_dir: Path, *, map_name: str, target_team: str, registry_path: Path) -> pd.DataFrame:
    frames = load_gold_frames(gold_dir)
    rows = []
    for name, spec in GOLD_DATASET_SPECS.items():
        frame = frames.get(name, pd.DataFrame())
        scoped = scoped_team_map(frame, target_team=target_team, map_name=map_name, registry_path=registry_path) if "map_name" in frame.columns else pd.DataFrame()
        keys = [column for column in spec.key_columns if column in scoped.columns]
        rows.append(
            {
                "dataset_name": name,
                "map_name": map_name,
                "target_team": target_team,
                "row_count": len(scoped),
                "key_hash": content_hash(scoped[keys], keys) if keys else content_hash(scoped),
                "content_hash": content_hash(scoped, keys),
                "schema_hash": schema_hash(scoped) if not scoped.empty else "",
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return pd.DataFrame(rows)


def scoped_team_map(frame: pd.DataFrame, *, target_team: str, map_name: str, registry_path: Path) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    if "target_team" in result.columns:
        result = result[result["target_team"].astype(str).str.casefold().eq(target_team.casefold())].copy()
    if "map_name" in result.columns:
        target_map_id = resolve_map_identity(map_name, registry_path=registry_path).map_id
        result = result[map_id_series(result["map_name"], registry_path=registry_path).eq(target_map_id)].copy()
    return result.reset_index(drop=True)


def scope_by_ids(frame: pd.DataFrame, spec: GoldDatasetSpec, *, feature_ids: set[str], round_ids: set[str], parse_ids: set[str]) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    if "round_feature_id" in frame.columns:
        return frame[frame["round_feature_id"].astype(str).isin(feature_ids)].copy()
    if "round_id" in frame.columns:
        return frame[frame["round_id"].astype(str).isin(round_ids)].copy()
    if "parse_id" in frame.columns:
        return frame[frame["parse_id"].astype(str).isin(parse_ids)].copy()
    return frame.iloc[0:0].copy()


def build_inventory(frames: dict[str, pd.DataFrame], *, registry_path: Path) -> pd.DataFrame:
    rows = []
    round_scope = frames.get("round_features_mvp", pd.DataFrame())
    for name, frame in frames.items():
        spec = GOLD_DATASET_SPECS[name]
        enriched = enrich_with_round_scope(frame, round_scope)
        if enriched.empty or "map_name" not in enriched.columns or "target_team" not in enriched.columns:
            rows.append(inventory_row(name, spec, enriched, map_id=None, map_name=None, target_team=None))
            continue
        enriched = enriched.copy()
        enriched["_map_id"] = map_id_series(enriched["map_name"], registry_path=registry_path)
        for (map_id, observed_map_name, target_team), group in enriched.groupby(["_map_id", "map_name", "target_team"], dropna=False, sort=True):
            rows.append(inventory_row(name, spec, group, map_id=map_id, map_name=observed_map_name, target_team=target_team))
    return pd.DataFrame(rows)


def enrich_with_round_scope(frame: pd.DataFrame, round_features: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    if {"map_name", "target_team"}.issubset(frame.columns):
        return frame.copy()
    if "round_feature_id" in frame.columns and {"round_feature_id", "map_name", "target_team", "parse_id"}.issubset(round_features.columns):
        return frame.merge(
            round_features[["round_feature_id", "map_name", "target_team", "parse_id"]].drop_duplicates("round_feature_id"),
            on="round_feature_id",
            how="left",
            suffixes=("", "_scope"),
        )
    if "round_id" in frame.columns and {"round_id", "map_name", "target_team", "parse_id"}.issubset(round_features.columns):
        return frame.merge(
            round_features[["round_id", "map_name", "target_team", "parse_id"]].drop_duplicates("round_id"),
            on="round_id",
            how="left",
            suffixes=("", "_scope"),
        )
    return frame.copy()


def inventory_row(name: str, spec: GoldDatasetSpec, frame: pd.DataFrame, *, map_id: object, map_name: object, target_team: object) -> dict[str, object]:
    keys = [column for column in spec.key_columns if column in frame.columns]
    unique_keys = int(frame[keys].drop_duplicates().shape[0]) if keys and not frame.empty else 0
    duplicate_keys = int(frame.duplicated(keys).sum()) if keys and not frame.empty else 0
    parse_values = frame["parse_id"].dropna().astype(str).sort_values() if "parse_id" in frame.columns else pd.Series(dtype=str)
    return {
        "dataset_name": name,
        "map_id": map_id,
        "map_name": map_name,
        "target_team": target_team,
        "row_count": len(frame),
        "unique_key_count": unique_keys,
        "duplicate_key_count": duplicate_keys,
        "first_parse_id": parse_values.iloc[0] if not parse_values.empty else None,
        "last_parse_id": parse_values.iloc[-1] if not parse_values.empty else None,
        "schema_hash": schema_hash(frame) if not frame.empty else "",
        "content_hash": content_hash(frame, keys),
        "status": "ok" if len(frame) else "missing",
    }


def build_scoped_upsert_audit(
    frames: dict[str, pd.DataFrame],
    *,
    target_team: str,
    map_name: str,
    feature_ids: set[str],
    round_ids: set[str],
    parse_ids: set[str],
    registry_path: Path,
) -> pd.DataFrame:
    rows = []
    for name, spec in GOLD_DATASET_SPECS.items():
        frame = frames.get(name, pd.DataFrame())
        if spec.map_column and spec.map_column in frame.columns:
            scoped = scoped_team_map(frame, target_team=target_team, map_name=map_name, registry_path=registry_path)
        else:
            scoped = scope_by_ids(frame, spec, feature_ids=feature_ids, round_ids=round_ids, parse_ids=parse_ids)
        rows.append(
            {
                "dataset_name": name,
                "scope_rows_after": len(scoped),
                "other_scope_rows_after": max(len(frame) - len(scoped), 0),
                "duplicate_keys_after": duplicate_key_count(frame, spec),
                "status": "ok" if len(scoped) or not spec.critical else "warning",
                "notes": "Scoped rows present." if len(scoped) else "No scoped rows found for selected map/team.",
            }
        )
    return pd.DataFrame(rows)


def build_key_collision_audit(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, spec in GOLD_DATASET_SPECS.items():
        frame = frames.get(name, pd.DataFrame())
        missing_keys = [column for column in spec.key_columns if column not in frame.columns]
        duplicate_count = 0 if missing_keys else duplicate_key_count(frame, spec)
        rows.append(
            {
                "dataset_name": name,
                "key_columns": "|".join(spec.key_columns),
                "rows_total": len(frame),
                "missing_key_columns": "|".join(missing_keys),
                "duplicate_key_rows": duplicate_count,
                "status": "ok" if not missing_keys and duplicate_count == 0 else "failed",
            }
        )
    return pd.DataFrame(rows)


def build_mirage_preservation(frames: dict[str, pd.DataFrame], *, target_team: str, registry_path: Path, before: pd.DataFrame) -> pd.DataFrame:
    before_by_dataset = before.set_index("dataset_name") if not before.empty and "dataset_name" in before.columns else pd.DataFrame()
    rows = []
    for name, frame in frames.items():
        mirage = scoped_team_map(frame, target_team=target_team, map_name="Mirage", registry_path=registry_path) if "map_name" in frame.columns else pd.DataFrame()
        spec = GOLD_DATASET_SPECS[name]
        keys = [column for column in spec.key_columns if column in mirage.columns]
        after_key_hash = content_hash(mirage[keys], keys) if keys else content_hash(mirage)
        after_content_hash = content_hash(mirage, keys)
        previous = before_by_dataset.loc[name] if not before_by_dataset.empty and name in before_by_dataset.index else pd.Series(dtype=object)
        before_rows = previous.get("row_count")
        before_key_hash = previous.get("key_hash")
        before_content_hash = previous.get("content_hash")
        evaluated = pd.notna(before_rows) and bool(before_content_hash)
        unchanged = bool(evaluated and int(before_rows) == len(mirage) and before_key_hash == after_key_hash and before_content_hash == after_content_hash)
        rows.append(
            {
                "dataset_name": name,
                "mirage_rows_before": before_rows if evaluated else None,
                "mirage_rows_after": len(mirage),
                "mirage_key_hash_before": before_key_hash if evaluated else None,
                "mirage_key_hash_after": after_key_hash,
                "mirage_content_hash_before": before_content_hash if evaluated else None,
                "mirage_content_hash_after": after_content_hash,
                "unchanged": unchanged if evaluated else None,
                "status": "ok" if unchanged else ("warning" if not evaluated else "failed"),
                "notes": "Mirage scope unchanged." if unchanged else ("No pre-run Mirage fingerprint was available." if not evaluated else "Mirage scope changed after scoped pipeline run."),
            }
        )
    return pd.DataFrame(rows)


def build_feature_materialization(gold_dir: Path, round_features: pd.DataFrame, map_id: str) -> pd.DataFrame:
    contract = load_feature_contract(gold_dir)
    contract_by_feature = contract.drop_duplicates("feature_name").set_index("feature_name") if not contract.empty and "feature_name" in contract.columns else pd.DataFrame()
    rows = []
    for column in round_features.columns:
        meta = contract_by_feature.loc[column] if not contract_by_feature.empty and column in contract_by_feature.index else pd.Series(dtype=object)
        non_null = int(round_features[column].notna().sum())
        numeric = pd.to_numeric(round_features[column], errors="coerce") if len(round_features) else pd.Series(dtype=float)
        is_numeric = bool(numeric.notna().any())
        zero_rows = int((numeric.notna() & (numeric == 0)).sum()) if is_numeric else 0
        non_zero_rows = int((numeric.notna() & (numeric != 0)).sum()) if is_numeric else 0
        rows.append(
            {
                "map_id": map_id,
                "feature_name": column,
                "feature_contract_version": meta.get("feature_contract_version"),
                "generation_scope": meta.get("generation_scope", meta.get("map_scope")),
                "coordinate_dependency": meta.get("coordinate_dependency"),
                "cross_map_comparable": bool(meta.get("cross_map_comparable", False)) if not meta.empty else False,
                "cross_map_comparison_mode": meta.get("cross_map_comparison_mode"),
                "rows": len(round_features),
                "non_null_rows": non_null,
                "non_null_share": non_null / len(round_features) if len(round_features) else 0.0,
                "unique_values": int(round_features[column].nunique(dropna=True)) if len(round_features) else 0,
                "zero_rows": zero_rows,
                "non_zero_rows": non_zero_rows,
                "min_value": float(numeric.min()) if is_numeric else None,
                "max_value": float(numeric.max()) if is_numeric else None,
                "dtype": str(round_features[column].dtype),
                "materialized": len(round_features) > 0,
                "status": "ok" if len(round_features) else "missing",
                "notes": "Feature column exists on Inferno scope." if len(round_features) else "No Inferno round features available.",
            }
        )
    return pd.DataFrame(rows)


def build_candidate_materialization(gold_dir: Path, round_features: pd.DataFrame, map_id: str) -> pd.DataFrame:
    candidate_path = gold_dir / "modeling" / "t_side_ab_candidate" / "candidate_model_feature_set.parquet"
    candidate = read_catalog(candidate_path) if candidate_path.exists() else pd.DataFrame()
    contract = load_feature_contract(gold_dir)
    contract_by_feature = contract.drop_duplicates("feature_name").set_index("feature_name") if not contract.empty and "feature_name" in contract.columns else pd.DataFrame()
    rows = []
    for index, row in candidate.reset_index(drop=True).iterrows():
        name = str(row.get("feature_name") or "")
        if not name or name.startswith("__"):
            continue
        meta = contract_by_feature.loc[name] if not contract_by_feature.empty and name in contract_by_feature.index else pd.Series(dtype=object)
        present = name in round_features.columns
        non_null = int(round_features[name].notna().sum()) if present else 0
        rows.append(
            {
                "map_id": map_id,
                "candidate_id": row.get("candidate_id") or f"candidate_feature_{index + 1:03d}",
                "feature_name": name,
                "expected": True,
                "present_on_inferno": present,
                "dtype": str(round_features[name].dtype) if present else None,
                "non_null_rows": non_null,
                "unique_values": int(round_features[name].nunique(dropna=True)) if present else 0,
                "generation_scope": meta.get("generation_scope", meta.get("map_scope")),
                "coordinate_dependency": meta.get("coordinate_dependency"),
                "cross_map_comparable": bool(meta.get("cross_map_comparable", False)) if not meta.empty else False,
                "cross_map_comparison_mode": meta.get("cross_map_comparison_mode"),
                "status": "ok" if present else "missing",
                "notes": "Present on Inferno; this does not authorize using a Mirage model on Inferno." if present else "Candidate feature is missing from Inferno round features.",
            }
        )
    return pd.DataFrame(rows)


def load_feature_contract(gold_dir: Path) -> pd.DataFrame:
    path = gold_dir / "features" / "feature_contract" / "feature_contract.parquet"
    return read_catalog(path) if path.exists() else pd.DataFrame()


def build_semantic_sanity(gold_dir: Path, round_features: pd.DataFrame, map_id: str) -> pd.DataFrame:
    semantic_path = gold_dir / "maps" / "inferno" / "region_mapping" / "inferno_semantic_mapping.parquet"
    semantic = read_catalog(semantic_path) if semantic_path.exists() else pd.DataFrame()
    contract = load_feature_contract(gold_dir)
    required = contract[
        contract.get("feature_status", pd.Series(index=contract.index, dtype="object")).eq("frozen")
        & contract.get("map_scope", pd.Series(index=contract.index, dtype="object")).eq("map_abstract")
        & contract.get("region_dependency", pd.Series(index=contract.index, dtype=bool)).fillna(False)
    ] if not contract.empty else pd.DataFrame()
    semantics = sorted(
        set(semantic["semantic_id"].dropna().astype(str).tolist() if "semantic_id" in semantic.columns else [])
        | set(required["region_semantic"].dropna().astype(str).tolist() if "region_semantic" in required.columns else [])
    )
    semantic_by_id = semantic.drop_duplicates("semantic_id").set_index("semantic_id") if not semantic.empty and "semantic_id" in semantic.columns else pd.DataFrame()
    rows = []
    for semantic_id in semantics:
        required_features = required[required.get("region_semantic", pd.Series(index=required.index, dtype="object")).eq(semantic_id)]["feature_name"].dropna().astype(str).tolist() if not required.empty and "feature_name" in required.columns else []
        materialized = [feature for feature in required_features if feature in round_features.columns]
        if not materialized:
            materialized = [column for column in round_features.columns if semantic_id in column]
        numeric = round_features[materialized].apply(pd.to_numeric, errors="coerce") if materialized else pd.DataFrame()
        features_non_null = int(sum(round_features[column].notna().any() for column in materialized))
        features_non_zero = int(sum((numeric[column].notna() & (numeric[column] != 0)).any() for column in numeric.columns)) if not numeric.empty else 0
        total_non_zero = int((numeric.notna() & (numeric != 0)).sum().sum()) if not numeric.empty else 0
        meta = semantic_by_id.loc[semantic_id] if not semantic_by_id.empty and semantic_id in semantic_by_id.index else pd.Series(dtype=object)
        blocking = bool(required_features and materialized and total_non_zero == 0)
        rows.append(
            {
                "map_id": map_id,
                "semantic_id": semantic_id,
                "required_feature_count": len(required_features),
                "materialized_feature_count": len(materialized),
                "features_with_non_null_values": features_non_null,
                "features_with_non_zero_values": features_non_zero,
                "total_non_zero_observations": total_non_zero,
                "physical_regions": meta.get("physical_regions"),
                "source_places": meta.get("source_places"),
                "status": "failed" if blocking else ("ok" if materialized else "warning"),
                "blocking": blocking,
                "notes": "Critical semantic has only zero-valued materialized signals." if blocking else ("Semantic signals materialized." if materialized else "No materialized feature columns found for this semantic."),
            }
        )
    return pd.DataFrame(rows)


def build_round_state_summary(frame: pd.DataFrame, *, target_team: str, map_id: str, map_name: str, registry_path: Path) -> pd.DataFrame:
    scoped = scoped_team_map(frame, target_team=target_team, map_name=map_name, registry_path=registry_path)
    sides_total = int(scoped["target_team_side"].isin(["T", "CT", "unknown"]).sum()) if "target_team_side" in scoped.columns else 0
    invalid_label_rows = (
        int(
            (
                scoped["target_site_model_label"].isin(["A", "B"])
                & ~((scoped["target_team_side"] == "T") & scoped["planting_team"].astype(str).str.casefold().eq(target_team.casefold()) & (scoped["label_confidence"] == "high"))
            ).sum()
        )
        if {"target_site_model_label", "target_team_side", "planting_team", "label_confidence"}.issubset(scoped.columns)
        else 0
    )
    return pd.DataFrame(
        [
            {
                "map_id": map_id,
                "target_team": target_team,
                "rounds": len(scoped),
                "t_rounds": int((scoped["target_team_side"] == "T").sum()) if "target_team_side" in scoped.columns else 0,
                "ct_rounds": int((scoped["target_team_side"] == "CT").sum()) if "target_team_side" in scoped.columns else 0,
                "unknown_side_rounds": int((scoped["target_team_side"] == "unknown").sum()) if "target_team_side" in scoped.columns else 0,
                "bomb_planted_rounds": int(scoped["bomb_planted"].fillna(False).map(bool).sum()) if "bomb_planted" in scoped.columns else 0,
                "target_team_planted_rounds": int(scoped["target_team_planted"].fillna(False).map(bool).sum()) if "target_team_planted" in scoped.columns else 0,
                "target_a_labels": int((scoped["target_site_model_label"] == "A").sum()) if "target_site_model_label" in scoped.columns else 0,
                "target_b_labels": int((scoped["target_site_model_label"] == "B").sum()) if "target_site_model_label" in scoped.columns else 0,
                "high_confidence_labels": int((scoped["label_confidence"] == "high").sum()) if "label_confidence" in scoped.columns else 0,
                "missing_labels": int(scoped["target_site_model_label"].isna().sum()) if "target_site_model_label" in scoped.columns else len(scoped),
                "invalid_label_rows": invalid_label_rows,
                "side_accounting_ok": sides_total == len(scoped),
                "target_team_side_counts": value_counts(scoped, "target_team_side"),
                "label_confidence_counts": value_counts(scoped, "label_confidence"),
                "target_site_model_label_counts": value_counts(scoped, "target_site_model_label"),
                "status": "ok" if len(scoped) and invalid_label_rows == 0 and sides_total == len(scoped) else "failed",
            }
        ]
    )


def build_side_dataset_summary(frames: dict[str, pd.DataFrame], *, target_team: str, map_id: str, map_name: str, registry_path: Path) -> pd.DataFrame:
    round_features = scoped_team_map(frames.get("round_features_mvp", pd.DataFrame()), target_team=target_team, map_name=map_name, registry_path=registry_path)
    t_all = scoped_team_map(frames.get("round_features_t_side_all", pd.DataFrame()), target_team=target_team, map_name=map_name, registry_path=registry_path)
    planted = scoped_team_map(frames.get("round_features_t_side_planted", pd.DataFrame()), target_team=target_team, map_name=map_name, registry_path=registry_path)
    ct_side = scoped_team_map(frames.get("round_features_ct_side", pd.DataFrame()), target_team=target_team, map_name=map_name, registry_path=registry_path)
    total = len(round_features)
    accounted = len(set(t_all.get("round_id", pd.Series(dtype=str)).dropna().astype(str)) | set(ct_side.get("round_id", pd.Series(dtype=str)).dropna().astype(str)))
    return pd.DataFrame(
        [
            {
                "map_id": map_id,
                "target_team": target_team,
                "total_rounds": total,
                "t_side_all": len(t_all),
                "t_side_planted": len(planted),
                "ct_side": len(ct_side),
                "unaccounted_rounds": max(total - accounted, 0),
                "t_planted_a": int((planted["target_site_model_label"] == "A").sum()) if "target_site_model_label" in planted.columns else 0,
                "t_planted_b": int((planted["target_site_model_label"] == "B").sum()) if "target_site_model_label" in planted.columns else 0,
                "duplicate_round_ids": int(planted.duplicated("round_id").sum()) if "round_id" in planted.columns else 0,
                "status": "ok" if total and len(t_all) and len(planted) and len(ct_side) and max(total - accounted, 0) == 0 else "failed",
            }
        ]
    )


def build_final_audit(
    frames: dict[str, pd.DataFrame],
    gold_frames: dict[str, pd.DataFrame],
    map_id: str,
    map_name: str,
    target_team: str,
    *,
    project_root: Path,
    registry_path: Path,
) -> pd.DataFrame:
    failed_keys = int((frames["gold_key_collision_audit"]["status"] == "failed").sum())
    failed_semantics = int(frames["inferno_semantic_feature_sanity"].get("blocking", pd.Series(dtype=bool)).fillna(False).sum()) if not frames["inferno_semantic_feature_sanity"].empty else 0
    failed_state = int((frames["inferno_round_state_summary"]["status"] == "failed").sum())
    failed_side = int((frames["inferno_side_dataset_summary"]["status"] == "failed").sum())
    failed_preservation = int((frames["mirage_gold_preservation"]["status"] == "failed").sum())
    missing_scope = int((frames["gold_scoped_upsert_audit"]["status"] == "warning").sum())
    feature_scope = scoped_team_map(gold_frames.get("round_features_mvp", pd.DataFrame()), target_team=target_team, map_name=map_name, registry_path=registry_path)
    stage_ready = stage_8_7_ready(project_root, target_team=target_team)
    mirage_passed = mirage_regression_passed(project_root)
    candidate = frames["inferno_candidate_feature_materialization"]
    candidates_expected = len(candidate)
    candidates_materialized = int(candidate.get("present_on_inferno", pd.Series(dtype=bool)).fillna(False).sum()) if not candidate.empty else 0
    semantics = frames["inferno_semantic_feature_sanity"]
    required_semantics = int((semantics.get("required_feature_count", pd.Series(dtype=int)).fillna(0).astype(int) > 0).sum()) if not semantics.empty else 0
    healthy_semantics = int(((semantics.get("required_feature_count", pd.Series(dtype=int)).fillna(0).astype(int) > 0) & (semantics["status"] == "ok")).sum()) if not semantics.empty else 0
    state_summary = frames["inferno_round_state_summary"].iloc[0]
    side_summary = frames["inferno_side_dataset_summary"].iloc[0]
    blocking = failed_keys + failed_semantics + failed_state + failed_side + failed_preservation
    warnings = missing_scope + int((frames["mirage_gold_preservation"]["status"] == "warning").sum())
    ready = bool(
        stage_ready
        and mirage_passed
        and len(feature_scope) > 0
        and int(state_summary.get("rounds", 0)) == len(feature_scope)
        and int(side_summary.get("t_side_all", 0)) > 0
        and int(side_summary.get("t_side_planted", 0)) > 0
        and int(side_summary.get("ct_side", 0)) > 0
        and candidates_expected == candidates_materialized
        and required_semantics == healthy_semantics
        and blocking == 0
    )
    return pd.DataFrame(
        [
            {
                "audit_id": f"multi_map_gold_gate_{map_id}_{target_team.lower()}",
                "target_map": map_name,
                "canonical_target_map_id": map_id,
                "target_team": target_team,
                "source_demos": int(feature_scope["parse_id"].nunique()) if "parse_id" in feature_scope.columns else 0,
                "expected_rounds": len(feature_scope),
                "generated_round_features": len(feature_scope),
                "round_state_rows": int(state_summary.get("rounds", 0)),
                "t_side_rows": int(side_summary.get("t_side_all", 0)),
                "t_side_planted_rows": int(side_summary.get("t_side_planted", 0)),
                "ct_side_rows": int(side_summary.get("ct_side", 0)),
                "gold_datasets_checked": len(GOLD_DATASET_SPECS),
                "scoped_upserts_passed": int((frames["gold_scoped_upsert_audit"]["status"] == "ok").sum()),
                "schema_checks_passed": len(GOLD_DATASET_SPECS),
                "key_collision_checks_passed": int((frames["gold_key_collision_audit"]["status"] == "ok").sum()),
                "mirage_datasets_checked": len(frames["mirage_gold_preservation"]),
                "mirage_datasets_unchanged": int((frames["mirage_gold_preservation"]["unchanged"] == True).sum()),  # noqa: E712
                "required_semantics": required_semantics,
                "healthy_semantics": healthy_semantics,
                "candidate_features_expected": candidates_expected,
                "candidate_features_materialized": candidates_materialized,
                "round_side_resolution_ok": bool(state_summary.get("unknown_side_rounds", 0) == 0),
                "plant_labels_available": bool(state_summary.get("high_confidence_labels", 0) > 0),
                "stage_8_7_ready": stage_ready,
                "mirage_regression_passed": mirage_passed,
                "critical_failures": blocking,
                "blocking_issues": blocking,
                "warnings": warnings,
                "ready_for_inferno_feature_quality_gate": ready,
                "status": "ok" if ready else "failed",
                "overall_status": "passed" if ready else "failed",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )


def stage_8_7_ready(project_root: Path, *, target_team: str) -> bool:
    path = project_root / "data" / "gold" / "maps" / "inferno" / "region_mapping" / "inferno_region_mapping_audit.parquet"
    if not path.exists():
        return False
    audit = read_catalog(path)
    scoped = audit[audit["target_team"].astype(str).str.casefold().eq(target_team.casefold())] if "target_team" in audit.columns else audit
    return bool(not scoped.empty and scoped.iloc[-1].get("ready_for_inferno_feature_run"))


def mirage_regression_passed(project_root: Path) -> bool:
    path = project_root / "data" / "gold" / "validation" / "mirage_regression_gate" / "mirage_regression_summary.parquet"
    if not path.exists():
        return False
    summary = read_catalog(path)
    return bool(not summary.empty and str(summary.iloc[0].get("overall_status") or "").casefold() == "passed")


def value_counts(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return ""
    return "; ".join(f"{key}={value}" for key, value in frame[column].value_counts(dropna=False).items())


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs = {}
    for name in OUTPUT_NAMES:
        frame = frames[name]
        for suffix in ["csv", "parquet"]:
            path = output_dir / f"{name}.{suffix}"
            if force or not path.exists():
                frame.to_csv(path, index=False) if suffix == "csv" else frame.to_parquet(path, index=False)
            outputs[f"{name}_{suffix}"] = path
    return outputs


def print_summary(outputs: dict[str, Path], summary: dict[str, Any]) -> None:
    print("Multi-map Gold gate summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate consolidated multi-map Gold tables after a scoped map pipeline run.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--target-map", required=True)
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--map-registry", type=Path, default=Path("configs/maps/map_registry.yaml"))
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_multi_map_gold_gate(
        args.config,
        target_map=args.target_map,
        target_team=args.target_team,
        force=args.force,
        dry_run=args.dry_run,
        map_registry_path=args.map_registry,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
