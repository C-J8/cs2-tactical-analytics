from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from src.maps.identity import resolve_map_identity, try_resolve_map_identity
from src.utils.io import ensure_dir, read_catalog


ScopeStrategy = Literal["team_map", "parse_id", "round_feature_id", "round_id"]


@dataclass(frozen=True)
class GoldScope:
    map_id: str
    map_name: str
    target_team: str
    parse_ids: frozenset[str] = frozenset()
    round_feature_ids: frozenset[str] = frozenset()
    round_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class GoldDatasetSpec:
    dataset_name: str
    relative_path: Path
    key_columns: tuple[str, ...]
    scope_strategy: ScopeStrategy
    map_column: str | None = "map_name"
    team_column: str | None = "target_team"
    parse_id_column: str | None = "parse_id"
    critical: bool = True
    write_csv: bool = False


GOLD_DATASET_SPECS: dict[str, GoldDatasetSpec] = {
    "round_features_mvp": GoldDatasetSpec("round_features_mvp", Path("round_features/round_features_mvp"), ("round_feature_id",), "team_map", write_csv=True),
    "round_base": GoldDatasetSpec("round_base", Path("round_features/round_base"), ("round_feature_id",), "team_map"),
    "player_round_utility": GoldDatasetSpec("player_round_utility", Path("round_features/player_round_utility"), ("round_feature_id", "player_steamid"), "round_feature_id", map_column=None),
    "utility_events": GoldDatasetSpec("utility_events", Path("utility_events/utility_events"), ("utility_event_id",), "round_feature_id", map_column=None),
    "region_presence_by_round": GoldDatasetSpec(
        "region_presence_by_round",
        Path("region_presence/region_presence_by_round"),
        ("round_feature_id", "window_type", "window_start", "window_end", "region_name", "region_group"),
        "team_map",
    ),
    "round_state_resolved": GoldDatasetSpec("round_state_resolved", Path("round_state/round_state_resolved"), ("round_id",), "team_map", write_csv=True),
    "round_features_t_side_all": GoldDatasetSpec("round_features_t_side_all", Path("round_features/round_features_t_side_all"), ("round_feature_id",), "team_map", write_csv=True),
    "round_features_t_side_planted": GoldDatasetSpec("round_features_t_side_planted", Path("round_features/round_features_t_side_planted"), ("round_feature_id",), "team_map", write_csv=True),
    "round_features_ct_side": GoldDatasetSpec("round_features_ct_side", Path("round_features/round_features_ct_side"), ("round_feature_id",), "team_map", write_csv=True),
    "round_region_timeline": GoldDatasetSpec(
        "round_region_timeline",
        Path("round_progression/round_region_timeline"),
        ("round_feature_id", "window_type", "window_start", "window_end", "region_name", "region_group"),
        "team_map",
        write_csv=True,
    ),
    "death_context_by_round": GoldDatasetSpec("death_context_by_round", Path("round_progression/death_context_by_round"), ("death_context_id",), "team_map", write_csv=True),
    "bomb_carrier_timeline": GoldDatasetSpec(
        "bomb_carrier_timeline",
        Path("round_progression/bomb_carrier_timeline"),
        ("round_feature_id", "window_type", "window_start", "window_end"),
        "team_map",
        write_csv=True,
    ),
    "round_outcome_context": GoldDatasetSpec("round_outcome_context", Path("round_progression/round_outcome_context"), ("round_feature_id",), "team_map", write_csv=True),
}


def make_gold_scope(
    *,
    map_id: str,
    map_name: str,
    target_team: str,
    parse_ids: set[str] | frozenset[str] | None = None,
    round_feature_ids: set[str] | frozenset[str] | None = None,
    round_ids: set[str] | frozenset[str] | None = None,
) -> GoldScope:
    return GoldScope(
        map_id=map_id,
        map_name=map_name,
        target_team=target_team,
        parse_ids=frozenset(str(value) for value in (parse_ids or set())),
        round_feature_ids=frozenset(str(value) for value in (round_feature_ids or set())),
        round_ids=frozenset(str(value) for value in (round_ids or set())),
    )


def upsert_gold_scope(
    existing: pd.DataFrame,
    incoming: pd.DataFrame,
    scope: GoldScope,
    spec: GoldDatasetSpec,
    *,
    registry_path: Path,
    strict_schema: bool = True,
) -> tuple[pd.DataFrame, dict[str, object]]:
    incoming = incoming.copy()
    validate_incoming(incoming, spec)
    existing = existing.copy() if not existing.empty else pd.DataFrame(columns=incoming.columns)
    schema_compatible, schema_notes = schema_is_compatible(existing, incoming, strict=strict_schema)
    if not schema_compatible:
        raise ValueError(f"Schema mismatch for {spec.dataset_name}: {schema_notes}")

    existing_scope_mask = scope_mask(existing, scope, spec, registry_path=registry_path) if not existing.empty else pd.Series(dtype=bool)
    other = existing.loc[~existing_scope_mask].copy() if not existing.empty else pd.DataFrame(columns=incoming.columns)
    scope_before = existing.loc[existing_scope_mask].copy() if not existing.empty else pd.DataFrame(columns=incoming.columns)
    incoming_scope_mask = scope_mask(incoming, scope, spec, registry_path=registry_path) if not incoming.empty else pd.Series(dtype=bool)
    if not incoming.empty and not bool(incoming_scope_mask.all()):
        bad = int((~incoming_scope_mask).sum())
        raise ValueError(f"Incoming {spec.dataset_name} contains {bad} rows outside selected scope.")

    columns = list(dict.fromkeys([*existing.columns, *incoming.columns]))
    combined = pd.concat([other.reindex(columns=columns), incoming.reindex(columns=columns)], ignore_index=True)
    combined = sort_deterministically(combined, spec)
    duplicates = duplicate_key_count(combined, spec)
    if duplicates:
        raise ValueError(f"{spec.dataset_name} has {duplicates} duplicate stable keys after scoped upsert.")
    collision_count = cross_map_key_collision_count(combined, spec, registry_path=registry_path)
    if collision_count:
        raise ValueError(f"{spec.dataset_name} has {collision_count} cross-map key collisions after scoped upsert.")

    audit = {
        "dataset_name": spec.dataset_name,
        "scope_map_id": scope.map_id,
        "target_team": scope.target_team,
        "rows_before": len(existing),
        "scope_rows_before": len(scope_before),
        "other_scope_rows_before": len(other),
        "incoming_rows": len(incoming),
        "scope_rows_after": int(scope_mask(combined, scope, spec, registry_path=registry_path).sum()) if not combined.empty else 0,
        "other_scope_rows_after": len(combined) - (int(scope_mask(combined, scope, spec, registry_path=registry_path).sum()) if not combined.empty else 0),
        "rows_after": len(combined),
        "duplicate_keys_after": duplicates,
        "other_scope_hash_before": content_hash(other, list(spec.key_columns)),
        "other_scope_hash_after": content_hash(combined.loc[~scope_mask(combined, scope, spec, registry_path=registry_path)], list(spec.key_columns)) if not combined.empty else content_hash(pd.DataFrame(), list(spec.key_columns)),
        "other_scope_unchanged": content_hash(other, list(spec.key_columns)) == (content_hash(combined.loc[~scope_mask(combined, scope, spec, registry_path=registry_path)], list(spec.key_columns)) if not combined.empty else content_hash(pd.DataFrame(), list(spec.key_columns))),
        "idempotent": True,
        "schema_compatible": schema_compatible,
        "status": "ok",
        "notes": schema_notes,
    }
    return combined, audit


def write_scoped_dataset(
    incoming: pd.DataFrame,
    gold_dir: Path,
    scope: GoldScope,
    spec: GoldDatasetSpec,
    *,
    registry_path: Path,
    force: bool,
    csv: bool | None = None,
) -> tuple[dict[str, Path], dict[str, object]]:
    base_path = gold_dir / spec.relative_path
    parquet_path = base_path.with_suffix(".parquet")
    existing = read_catalog(parquet_path) if parquet_path.exists() else pd.DataFrame()
    if parquet_path.exists() and not force:
        return {parquet_path.name: parquet_path}, {
            "dataset_name": spec.dataset_name,
            "scope_map_id": scope.map_id,
            "target_team": scope.target_team,
            "rows_before": len(existing),
            "scope_rows_before": int(scope_mask(existing, scope, spec, registry_path=registry_path).sum()) if not existing.empty else 0,
            "other_scope_rows_before": len(existing),
            "incoming_rows": len(incoming),
            "scope_rows_after": int(scope_mask(existing, scope, spec, registry_path=registry_path).sum()) if not existing.empty else 0,
            "other_scope_rows_after": len(existing),
            "rows_after": len(existing),
            "duplicate_keys_after": duplicate_key_count(existing, spec) if not existing.empty else 0,
            "other_scope_hash_before": "",
            "other_scope_hash_after": "",
            "other_scope_unchanged": True,
            "idempotent": True,
            "schema_compatible": True,
            "status": "skipped_existing",
            "notes": "Existing dataset preserved because force was not requested.",
        }
    combined, audit = upsert_gold_scope(existing, incoming, scope, spec, registry_path=registry_path)
    ensure_dir(base_path.parent)
    atomic_write_parquet(combined, parquet_path)
    outputs = {parquet_path.name: parquet_path}
    write_csv = spec.write_csv if csv is None else csv
    if write_csv:
        csv_path = base_path.with_suffix(".csv")
        atomic_write_csv(combined, csv_path)
        outputs[csv_path.name] = csv_path
    return outputs, audit


def scope_mask(frame: pd.DataFrame, scope: GoldScope, spec: GoldDatasetSpec, *, registry_path: Path) -> pd.Series:
    if frame.empty:
        return pd.Series([], dtype=bool)
    mask = pd.Series(True, index=frame.index)
    if spec.team_column and spec.team_column in frame.columns:
        mask &= frame[spec.team_column].astype(str).str.casefold().eq(scope.target_team.casefold())
    if spec.scope_strategy == "team_map" and spec.map_column and spec.map_column in frame.columns:
        target_map_id = resolve_map_identity(scope.map_name, registry_path=registry_path).map_id
        mask &= map_id_series(frame[spec.map_column], registry_path=registry_path).eq(target_map_id)
    elif spec.scope_strategy == "parse_id" and spec.parse_id_column and spec.parse_id_column in frame.columns:
        mask &= frame[spec.parse_id_column].astype(str).isin(scope.parse_ids)
    elif spec.scope_strategy == "round_feature_id" and "round_feature_id" in frame.columns:
        mask &= frame["round_feature_id"].astype(str).isin(scope.round_feature_ids)
    elif spec.scope_strategy == "round_id" and "round_id" in frame.columns:
        mask &= frame["round_id"].astype(str).isin(scope.round_ids)
    elif spec.map_column not in frame.columns and spec.scope_strategy == "team_map":
        raise ValueError(f"{spec.dataset_name} cannot be scoped safely: missing map column {spec.map_column}.")
    return mask


def validate_incoming(frame: pd.DataFrame, spec: GoldDatasetSpec) -> None:
    missing = [column for column in spec.key_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{spec.dataset_name} missing key columns: {missing}")
    null_keys = int(frame[list(spec.key_columns)].isna().any(axis=1).sum()) if not frame.empty else 0
    if null_keys:
        raise ValueError(f"{spec.dataset_name} has {null_keys} rows with null stable keys.")
    duplicates = duplicate_key_count(frame, spec)
    if duplicates:
        raise ValueError(f"{spec.dataset_name} incoming rows have {duplicates} duplicate stable keys.")


def schema_is_compatible(existing: pd.DataFrame, incoming: pd.DataFrame, *, strict: bool) -> tuple[bool, str]:
    if existing.empty:
        return True, "No existing rows; incoming schema accepted."
    if list(existing.columns) == list(incoming.columns):
        return True, "Schema exact match."
    if set(existing.columns) != set(incoming.columns):
        return False, f"Columns differ. missing_from_incoming={sorted(set(existing.columns)-set(incoming.columns))}; extra_in_incoming={sorted(set(incoming.columns)-set(existing.columns))}"
    if strict:
        return False, "Column set matches, but column order differs."
    return True, "Column set matches; order normalized."


def duplicate_key_count(frame: pd.DataFrame, spec: GoldDatasetSpec) -> int:
    if frame.empty or not all(column in frame.columns for column in spec.key_columns):
        return 0
    return int(frame.duplicated(list(spec.key_columns)).sum())


def cross_map_key_collision_count(frame: pd.DataFrame, spec: GoldDatasetSpec, *, registry_path: Path) -> int:
    if frame.empty or "map_name" not in frame.columns or not all(column in frame.columns for column in spec.key_columns):
        return 0
    keyed = frame[list(spec.key_columns) + ["map_name"]].drop_duplicates().copy()
    keyed["_map_id"] = map_id_series(keyed["map_name"], registry_path=registry_path)
    return int(keyed.groupby(list(spec.key_columns))["_map_id"].nunique().gt(1).sum())


def sort_deterministically(frame: pd.DataFrame, spec: GoldDatasetSpec) -> pd.DataFrame:
    candidates = [column for column in ["target_team", "map_name", *spec.key_columns, "round_num", "window_type", "window_start", "window_end"] if column in frame.columns]
    if candidates:
        return frame.sort_values(candidates, kind="mergesort").reset_index(drop=True)
    return frame.reset_index(drop=True)


def map_id_series(values: pd.Series, *, registry_path: Path) -> pd.Series:
    cache: dict[str, str | None] = {}

    def resolve(value: object) -> str | None:
        key = str(value or "")
        if key not in cache:
            identity = try_resolve_map_identity(key, registry_path=registry_path)
            cache[key] = identity.map_id if identity else None
        return cache[key]

    return values.map(resolve)


def atomic_write_parquet(frame: pd.DataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    tmp = path.with_name(f"{path.stem}.tmp{path.suffix}")
    frame.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    tmp = path.with_name(f"{path.name}.tmp")
    frame.to_csv(tmp, index=False)
    os.replace(tmp, path)


def schema_hash(frame: pd.DataFrame) -> str:
    payload = "|".join(f"{column}:{frame[column].dtype}" for column in frame.columns)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def content_hash(frame: pd.DataFrame, keys: list[str] | None = None) -> str:
    if frame.empty:
        return hashlib.sha256(b"empty").hexdigest()
    canonical = frame.copy()
    sort_keys = [key for key in (keys or []) if key in canonical.columns]
    if sort_keys:
        canonical = canonical.sort_values(sort_keys, kind="mergesort")
    text = canonical.reset_index(drop=True).map(cell_text).to_json(orient="split")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cell_text(value: object) -> str:
    if value is None:
        return "<NA>"
    try:
        if pd.isna(value):
            return "<NA>"
    except (TypeError, ValueError):
        pass
    return str(value)
