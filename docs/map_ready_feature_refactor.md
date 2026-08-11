# Map-Ready Feature Refactor

## Purpose

Stage 8.2 moves map-dependent feature resolution out of the feature core and into the versioned map registry created in Stage 8.1. The feature engine now uses map identity, registry semantics, and the frozen feature contract before generating spatial features.

## Architecture before

```text
Parsed demo
   |
   v
Mirage place-name mapping
   |
   v
Round features
```

The old path worked for the Mirage MVP, but it made Mirage region definitions an implicit dependency of feature engineering.

## Architecture after

```text
Parsed demo
   |
   v
Map identity
   |
   v
Map Registry
   |
   +--> Physical Regions
   |
   +--> Semantic Groups
   |
   v
Generic Feature Engine
   |
   v
Feature Contract
   |
   v
Round Features
```

## Registry integration

`src.features.build_round_features` now loads `configs/maps/map_registry.yaml` by default and resolves `Mirage`, `mirage`, or `de_mirage` to the registered `map_id = mirage`.

The current Mirage registry still uses Awpy/place-name areas. No Mirage coordinates or region boundaries were changed. The feature engine derives the legacy output groups from the registry so existing outputs such as `MID_CONTROL`, `A_PRESSURE`, `B_PRESSURE`, and `CT_SPACE` remain stable.

## Feature contract integration

Stage 8.2 reads the Stage 8.0 feature contract from:

```text
data/gold/features/feature_contract/feature_contract.parquet
```

The contract controls whether a feature is:

- `global`: no map-region resolution required;
- `map_abstract`: resolved through a registry semantic group;
- `map_specific`: resolved through a physical region when explicitly required.

## Global features

Global features continue to bypass map geometry. Examples include starting utility inventory and non-spatial round context.

## Map-abstract features

Map-abstract features now resolve through semantic groups such as `mid_control`, `a_pressure`, `b_pressure`, and `ct_space`. Mirage provides the physical-region membership for those semantics in `configs/maps/mirage.yaml`.

## Map-specific features

No current frozen MVP feature is classified as Mirage-specific in the validated snapshot. The code path exists for future map-specific features, but Stage 8.2 does not add new features.

## Mirage compatibility

The compatibility audit compares the available before/after datasets:

```text
round_features_mvp
region_presence_by_round
round_region_timeline
round_features_t_side_all
round_features_t_side_planted
```

Numeric comparisons use `atol = 1e-9` and `rtol = 1e-9`. Strings, booleans, and integers require exact equality.

Validated snapshot:

| Metric | Value |
| --- | ---: |
| Rounds processed | 405 |
| Features generated | 487 |
| Compatibility rows | 1511 |
| Failed compatibility rows | 0 |
| Compatibility status | passed |

## Candidate feature compatibility

The promoted candidate feature set remains intact:

| Metric | Value |
| --- | ---: |
| Candidate features expected | 31 |
| Candidate features found | 31 |
| Candidate features missing | 0 |
| Candidate feature values changed | 0 |

## Region timeline compatibility

`side_datasets` now uses the same registry-backed region lookup path when rebuilding `round_region_timeline`, `death_context_by_round`, `bomb_carrier_timeline`, and `round_outcome_context`.

Validated side dataset snapshot:

| Dataset | Rows |
| --- | ---: |
| T-side all | 180 |
| T-side planted | 98 |
| CT-side | 225 |
| Round region timeline | 43961 |

## Unknowns

`map_feature_unknowns` is empty in the validated Mirage snapshot. All 308 region-dependent features resolve through the registry.

## Performance

The validated run recorded `new_runtime_seconds` at about 42 seconds on the local machine. No old runtime baseline was available, so `old_runtime_seconds`, `runtime_delta_seconds`, and `runtime_delta_pct` remain null.

## Limitations

Only Mirage is onboarded as a production registry. Stage 8.2 does not add Inferno, Nuke, Ancient, Anubis, or any other map. Named Awpy/place areas cannot be evaluated by coordinate-only geometry helpers; coordinate support exists for future bounding boxes, polygons, and composite regions.

## Ready for next stage

`map_feature_engine_ready = true` for the current Mirage snapshot.

## Next stage

Next: Stage 8.3 -- Mirage Regression / Backward Compatibility Gate.

Stage 8.3 should rerun the full pipeline from parse quality through candidate model inputs and formally prove that the map-ready architecture preserves the MVP end to end.
