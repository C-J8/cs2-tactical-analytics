# Reconciliação das quatro DEMs de `hltv_2389666`

Data da reconciliação: `2026-09-09T15:11:08-03:00`.

## Conclusão

Os quatro arquivos encontrados fora do manifesto canônico não são segmentos de uma única partida e não representam quatro partidas adicionais do Mirage. Eles são cópias legadas, byte a byte, das quatro DEMs extraídas do mesmo arquivo `hltv_2389666_mirage_map1.rar` pelo fluxo canônico.

Somente a primeira DEM é Mirage. As demais são Inferno, Nuke e Overpass. O diretório legado `data/raw/demos/Vitality/Mirage/` refletia o mapa informado no catálogo do download, não o mapa real de cada DEM dentro do pacote da série.

| arquivo legado | arquivo canônico | mapa real | tamanho (bytes) | SHA-256 |
| --- | --- | --- | ---: | --- |
| `hltv_2389666_mirage_map1_dem1.dem` | `hltv_2389666_mirage_map1_furia_vs_vitality_m1_mirage.dem` | Mirage | 740540720 | `9019e9ee6cdeee54d93a73625620f3372ee55b8560240b6381f67fdb84676cbb` |
| `hltv_2389666_mirage_map1_dem2.dem` | `hltv_2389666_mirage_map1_furia_vs_vitality_m2_inferno.dem` | Inferno | 604571739 | `affd22a7fb10a99d149cd343ebe29b83457a40862244a398de3cb48930110907` |
| `hltv_2389666_mirage_map1_dem3.dem` | `hltv_2389666_mirage_map1_furia_vs_vitality_m3_nuke.dem` | Nuke | 333796813 | `2b2f6f3ceeb869dccc3078c300918a1deb8b495f384ee3809d577dcb5d7da582` |
| `hltv_2389666_mirage_map1_dem4.dem` | `hltv_2389666_mirage_map1_furia_vs_vitality_m4_overpass.dem` | Overpass | 604583203 | `24370e1f72c2f2ca33108f786d9c08f175c3c821c4213641e782080a869c3640` |

Tamanho redundante total: `2.283.492.475` bytes.

## Ação aplicada

As quatro cópias legadas foram movidas, sem exclusão, para:

```text
data/raw/quarantine/duplicate_demos/hltv_2389666/
```

As quatro cópias canônicas permanecem em `data/raw/demos/Vitality/hltv_2389666_mirage_map1/`, continuam registradas em `dem_files_manifest` e são as únicas usadas pelo parsing atual.

Após a movimentação, o inventário ativo ficou com `55` DEMs físicas e `55` DEMs catalogadas, sem arquivos órfãos ou ausentes. O critério `physical_demo_inventory_reconciled` passou.

## Causa no pipeline

O manifesto `demo_manifest` foi produzido pelo downloader antigo, que também extraía arquivos diretamente em `data/raw/demos/<team>/<catalog_map>/`. Depois, `scan_local_archives` extraiu o mesmo arquivo novamente em `data/raw/demos/<team>/<local_archive_id>/` e criou o manifesto canônico `dem_files_manifest`.

A correção estrutural seguinte deve fazer o downloader possuir apenas a aquisição do arquivo compactado e deixar `scan_local_archives` como único responsável pela extração e pelo catálogo de DEMs. Até essa separação ser implementada, executar novamente o downloader com extração habilitada pode recriar as quatro cópias legadas.
