# Map Geometry & Region Registry

## Purpose
Define an auditable map/region registry that separates physical map areas from tactical semantics.

## Why map geometry must be configurable
Map-abstract features can only expand safely when each map declares the regions behind shared semantics.

## Current reference map
| registry_version   | map_id   | display_name   | game_map_name   | region_schema_version   | config_path              | status   | is_reference_map   |   physical_region_count |   semantic_group_count |   bombsite_count | notes                                                         |
|:-------------------|:---------|:---------------|:----------------|:------------------------|:-------------------------|:---------|:-------------------|------------------------:|-----------------------:|-----------------:|:--------------------------------------------------------------|
| v1                 | mirage   | Mirage         | de_mirage       | v1                      | configs/maps/mirage.yaml | active   | True               |                      15 |                      8 |                2 | Reference map migrated from configs/maps/mirage_regions.yaml. |

## Coordinate system
The current Mirage implementation uses Awpy/place-name areas, not project-owned coordinate bounding boxes.

## Physical regions
| region_id   | display_name   | geometry_type   | geometry_source                |   priority | semantic_tags   | aliases                            |
|:------------|:---------------|:----------------|:-------------------------------|-----------:|:----------------|:-----------------------------------|
| t_spawn     | T Spawn        | named_area      | migrated_from_current_pipeline |         99 | t_spawn_area    | T Spawn|TSpawn                     |
| mid         | Mid            | named_area      | migrated_from_current_pipeline |         98 | mid_control     | Mid|Middle                         |
| top_mid     | Top Mid        | named_area      | migrated_from_current_pipeline |         97 | mid_control     | Top Mid|TopofMid                   |
| connector   | Connector      | named_area      | migrated_from_current_pipeline |         96 | mid_control     | Connector                          |
| window      | Window         | named_area      | migrated_from_current_pipeline |         95 | mid_control     | SnipersNest|Window                 |
| catwalk     | Catwalk        | named_area      | migrated_from_current_pipeline |         94 | mid_control     | Catwalk                            |
| a_ramp      | A Ramp         | named_area      | migrated_from_current_pipeline |         93 | a_pressure      | A Ramp|Ramp|TRamp                  |
| palace      | Palace         | named_area      | migrated_from_current_pipeline |         92 | a_pressure      | Palace|PalaceAlley|PalaceInterior  |
| a_site      | A Site         | named_area      | migrated_from_current_pipeline |         91 | site_a          | A Site|BombsiteA|Stairs            |
| b_apps      | B Apps         | named_area      | migrated_from_current_pipeline |         90 | b_pressure      | Apartments|B Apps|BackAlley|House  |
| b_short     | B Short        | named_area      | migrated_from_current_pipeline |         89 | b_pressure      | B Short|Ladder|Scaffolding         |
| b_site      | B Site         | named_area      | migrated_from_current_pipeline |         88 | site_b          | B Site|BombsiteB                   |
| market      | Market         | named_area      | migrated_from_current_pipeline |         87 | ct_space        | Market|Shop                        |
| ct_spawn    | CT Spawn       | named_area      | migrated_from_current_pipeline |         86 | ct_space        | CT Spawn|CTSpawn|TicketBooth|Truck |
| jungle      | Jungle         | named_area      | migrated_from_current_pipeline |         85 | rotation        | Jungle|SideAlley|Underpass         |

## Semantic regions
| registry_version   | map_id   | semantic_id   | description                                                                    |   member_region_count | member_regions                       |   feature_contract_usage_count | status   | notes                                            |
|:-------------------|:---------|:--------------|:-------------------------------------------------------------------------------|----------------------:|:-------------------------------------|-------------------------------:|:---------|:-------------------------------------------------|
| v1                 | mirage   | a_pressure    | Regions representing meaningful attacking pressure toward bombsite A.          |                     2 | a_ramp|palace                        |                             88 | active   | Migrated from current place-name region mapping. |
| v1                 | mirage   | b_pressure    | Regions representing meaningful attacking pressure toward bombsite B.          |                     2 | b_apps|b_short                       |                             88 | active   | Migrated from current place-name region mapping. |
| v1                 | mirage   | ct_space      | Defensive or CT-side space used by current region mapping.                     |                     2 | market|ct_spawn                      |                             44 | active   | Migrated from current place-name region mapping. |
| v1                 | mirage   | mid_control   | Map-dependent areas representing meaningful control of central tactical space. |                     5 | mid|top_mid|connector|window|catwalk |                             88 | active   | Migrated from current place-name region mapping. |
| v1                 | mirage   | rotation      | Connector or rotation areas linking major tactical spaces.                     |                     1 | jungle                               |                              0 | active   | Migrated from current place-name region mapping. |
| v1                 | mirage   | site_a        | Physical bombsite A regions.                                                   |                     1 | a_site                               |                              0 | active   | Migrated from current place-name region mapping. |
| v1                 | mirage   | site_b        | Physical bombsite B regions.                                                   |                     1 | b_site                               |                              0 | active   | Migrated from current place-name region mapping. |
| v1                 | mirage   | t_spawn_area  | Map-dependent areas representing the T-side spawn/start space.                 |                     1 | t_spawn                              |                              0 | active   | Migrated from current place-name region mapping. |

## Physical-to-semantic mapping
| map_id   | region_id   | semantic_id   | mapping_source    | confidence   | status   | notes                                        |
|:---------|:------------|:--------------|:------------------|:-------------|:---------|:---------------------------------------------|
| mirage   | a_ramp      | a_pressure    | existing_pipeline | high         | active   | Migrated from existing region_group mapping. |
| mirage   | palace      | a_pressure    | existing_pipeline | high         | active   | Migrated from existing region_group mapping. |
| mirage   | b_apps      | b_pressure    | existing_pipeline | high         | active   | Migrated from existing region_group mapping. |
| mirage   | b_short     | b_pressure    | existing_pipeline | high         | active   | Migrated from existing region_group mapping. |
| mirage   | market      | ct_space      | existing_pipeline | high         | active   | Migrated from existing region_group mapping. |
| mirage   | ct_spawn    | ct_space      | existing_pipeline | high         | active   | Migrated from existing region_group mapping. |
| mirage   | mid         | mid_control   | existing_pipeline | high         | active   | Migrated from existing region_group mapping. |
| mirage   | top_mid     | mid_control   | existing_pipeline | high         | active   | Migrated from existing region_group mapping. |
| mirage   | connector   | mid_control   | existing_pipeline | high         | active   | Migrated from existing region_group mapping. |
| mirage   | window      | mid_control   | existing_pipeline | high         | active   | Migrated from existing region_group mapping. |
| mirage   | catwalk     | mid_control   | existing_pipeline | high         | active   | Migrated from existing region_group mapping. |
| mirage   | jungle      | rotation      | existing_pipeline | high         | active   | Migrated from existing region_group mapping. |
| mirage   | a_site      | site_a        | existing_pipeline | high         | active   | Migrated from existing region_group mapping. |
| mirage   | b_site      | site_b        | existing_pipeline | high         | active   | Migrated from existing region_group mapping. |
| mirage   | t_spawn     | t_spawn_area  | existing_pipeline | high         | active   | Migrated from existing region_group mapping. |

## Bombsites
| map_id   | bombsite   | region_id   | mapping_role   |   priority | status   | notes                                              |
|:---------|:-----------|:------------|:---------------|-----------:|:---------|:---------------------------------------------------|
| mirage   | A          | a_site      | site_region    |         91 | active   | Bombsite A migrated from BOMB_SITE_A region group. |
| mirage   | B          | b_site      | site_region    |         88 | active   | Bombsite B migrated from BOMB_SITE_B region group. |

## Feature contract coverage
| feature_name                   | region_semantic   | map_scope    |   physical_region_count | map_ready   | blocking_reason   |
|:-------------------------------|:------------------|:-------------|------------------------:|:------------|:------------------|
| molotovs_to_a_pressure_0_105   | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_0_115   | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_0_15    | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_0_20    | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_0_25    | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_0_35    | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_0_45    | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_0_55    | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_0_65    | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_0_75    | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_0_85    | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_0_95    | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_105_115 | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_15_25   | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_25_35   | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_35_45   | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_45_55   | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_55_65   | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_65_75   | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_75_85   | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_85_95   | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_a_pressure_95_105  | a_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_0_105   | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_0_115   | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_0_15    | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_0_20    | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_0_25    | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_0_35    | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_0_45    | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_0_55    | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_0_65    | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_0_75    | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_0_85    | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_0_95    | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_105_115 | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_15_25   | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_25_35   | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_35_45   | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_45_55   | b_pressure        | map_abstract |                       2 | True        | none              |
| molotovs_to_b_pressure_55_65   | b_pressure        | map_abstract |                       2 | True        | none              |

## Map-abstract features
| feature_name                   | region_semantic   | physical_regions   | map_ready   |
|:-------------------------------|:------------------|:-------------------|:------------|
| molotovs_to_a_pressure_0_105   | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_0_115   | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_0_15    | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_0_20    | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_0_25    | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_0_35    | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_0_45    | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_0_55    | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_0_65    | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_0_75    | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_0_85    | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_0_95    | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_105_115 | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_15_25   | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_25_35   | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_35_45   | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_45_55   | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_55_65   | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_65_75   | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_75_85   | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_85_95   | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_a_pressure_95_105  | a_pressure        | a_ramp|palace      | True        |
| molotovs_to_b_pressure_0_105   | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_0_115   | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_0_15    | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_0_20    | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_0_25    | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_0_35    | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_0_45    | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_0_55    | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_0_65    | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_0_75    | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_0_85    | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_0_95    | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_105_115 | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_15_25   | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_25_35   | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_35_45   | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_45_55   | b_pressure        | b_apps|b_short     | True        |
| molotovs_to_b_pressure_55_65   | b_pressure        | b_apps|b_short     | True        |

## Mirage-specific features
_No rows available._

## Unknown / unresolved mappings
_No rows available._

## Backward compatibility
This stage writes configuration and metadata only. It does not recalculate round features or model outputs.

## Adding a new map
1. create `configs/maps/<map>.yaml`
2. register map in `map_registry.yaml`
3. define coordinate system
4. define physical regions
5. map physical regions to semantic groups
6. define bombsites
7. validate feature-contract coverage
8. run registry audit
9. only then run feature engineering

## Next stage
Next: Stage 8.2 -- Map-Ready Feature Refactor

## Audit
| audit_id                     | registry_version   |   maps_registered | reference_map   |   physical_regions |   semantic_groups |   region_semantic_mappings |   bombsite_mappings |   region_dependent_features |   resolved_region_features |   unresolved_region_features |   candidate_region_features |   candidate_region_features_resolved |   candidate_region_features_unresolved | ready_for_map_feature_refactor   |   unknown_rows |   invalid_region_references |   invalid_semantic_references |   invalid_alias_references | missing_optional_inputs   | config_written   | report_written   | status   | created_at                       |
|:-----------------------------|:-------------------|------------------:|:----------------|-------------------:|------------------:|---------------------------:|--------------------:|----------------------------:|---------------------------:|-----------------------------:|----------------------------:|-------------------------------------:|---------------------------------------:|:---------------------------------|---------------:|----------------------------:|------------------------------:|---------------------------:|:--------------------------|:-----------------|:-----------------|:---------|:---------------------------------|
| map_geometry_region_registry | v1                 |                 1 | mirage          |                 15 |                 8 |                         15 |                   2 |                         308 |                        308 |                            0 |                          11 |                                   11 |                                      0 | True                             |              0 |                           0 |                             0 |                          0 | none                      | True             | True             | ok       | 2026-08-09T14:40:11.597724+00:00 |
