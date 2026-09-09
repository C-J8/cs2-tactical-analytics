# Consolidação técnica do Mirage

## Escopo executado

Esta revisão implementa os itens 1–9 da lista de consolidação. Gráficos/apresentação e revisão manual ficaram deliberadamente fora deste ciclo.

## Decisões consolidadas

1. **Tickrate:** 64 ticks/s agora é um contrato versionado em `configs/timing.yaml`, não uma constante implícita. Cada demo recebe `tickrate`, origem, método de resolução e confiança. Os 23 demos elegíveis atuais são consistentes com a duração de freeze esperada.
2. **Mapa completo:** o registro do Mirage referencia a release `awpy-data` ClientVersion `2000899` (Steam build `25000182`). Radar, `.nav`, geometria `.mesh`, manifesto e transformação do radar são copiados para `data/reference/maps/awpy/2000899`, cada um com SHA-256.
3. **Modelo conhecido:** o candidato permanece uma regressão logística balanceada, com imputação pela mediana e padronização, horizonte de 35 s, 31 features e limiar 0,5 para a classe B.
4. **Dependência entre rounds:** a validação oficial interna agora usa `series_id` como grupo, com fallback programático para `parse_id`. Nenhuma série pode aparecer simultaneamente em treino e teste.
5. **Features globais por papel:** a camada canônica produz namespaces `attack_*` e `defense_*`, além das projeções `target_team_*` e `opponent_*` baseadas no lado resolvido do round.
6. **Features de mapa:** cada feature é classificada como `global`, `map_abstract` ou `map_specific`. Controle de áreas usa semânticas abstratas resolvidas pelo registro do mapa; centros X/Y/Z são específicos do sistema de coordenadas do mapa.
7. **Nomes `team_*`:** os Golds históricos continuam congelados. `feature_aliases` documenta a migração para nomes explícitos sem alterar os inputs que reproduzem o candidato antigo.
8. **Dispersão:** a métrica recomendada é `median_pairwise_distance_2d_*_snapshot`. Também são calculadas a mediana da distância ao centroide e a área do casco convexo. O antigo `team_spread` foi renomeado como distância média 3D ao centro acumulado; o `avg_pairwise_distance = team_spread × √2` está marcado como proxy depreciado.
9. **Dicionário de equipes:** `configs/player_rosters.yaml` virou um registro v1 com `team_id`, aliases, fonte e suporte a vigência. IDs externos e datas não foram inventados; enquanto não houver fonte verificada, a confiança fica `manual_unverified`.

## Pipeline após a consolidação

```text
catálogo/demos
    -> parse Awpy (Bronze/Silver)
    -> gate de qualidade de parse
    -> contrato de timing por demo + dicionário de equipes
    -> features legadas congeladas
    -> estado do round e lado real da equipe
    -> feature engine genérico por ataque/defesa
         -> semânticas resolvidas pelo registro do mapa
         -> projeção equipe-alvo/oponente
         -> views globais e ligadas ao mapa
    -> datasets/modelos
    -> validação agrupada por série
```

O motor de features não contém uma condição `if Mirage`. O que muda entre mapas é o arquivo em `configs/maps`: áreas físicas, aliases, grupos semânticos, bombsites, coordenadas e assets. Essa é a fronteira entre pipeline geral e configuração específica.

Os nomes canônicos de diretórios, tabelas e etapas não carregam sufixos como `v2`. A versão continua registrada somente onde ela representa um contrato de schema histórico. Em particular, o `Feature Contract v2`, anterior a esta consolidação, permanece como metadado de compatibilidade e não representa um segundo pipeline de features.

## Contrato do modelo atual

| Campo | Valor |
|---|---|
| Tarefa | Estimar P(site B \| Vitality está TR, planta e observamos até 35 s) |
| Unidade | Round plantado |
| Modelo | Regressão logística |
| Pré-processamento | Imputação mediana + `StandardScaler` |
| Balanceamento | `class_weight=balanced` |
| Features | 31 numéricas, conjunto `stable_only` |
| Amostra | 89 rounds, 17 séries |
| Validação primária | `StratifiedGroupKFold`, 5 folds, grupo=`series_id` |
| Sensibilidade | `LeaveOneGroupOut`, 17 folds |
| Classe positiva | B |
| Limiar | 0,5 |
| Uso | Análise tática exploratória; não causal e não operacional em tempo real |

## Resultado estatístico agrupado

Na validação primária agrupada: macro-F1 `0,6258`, balanced accuracy `0,6394`, recall B `0,56`, ROC AUC `0,6563` e 11 erros B→A. O intervalo bootstrap por série para macro-F1 é `[0,5195; 0,7407]`.

O macro-F1 histórico por `StratifiedKFold` de rounds era `0,6711`. Com isolamento por série, ele cai para `0,6258` (`-0,0453`) e o recall B passa de `0,60` para `0,56`. O sinal não desaparece, mas fica mais fraco e o intervalo de incerteza continua largo. Portanto, o resultado está consolidado como **validação interna agrupada**, não como validação externa.

## Compatibilidade com o legado

A suíte completa passou com 296 testes. A checagem específica do candidato também confirmou os mesmos 98 rounds plantados, as mesmas 31 features, os mesmos valores e os mesmos labels.

O gate amplo de regressão ainda compara o Gold atual com o snapshot `mirage_mvp_map_ready_v1`, anterior ao reparo já existente de flash/HE/placar e granularidade de utilidades. Por isso ele acusa cinco tabelas com diferenças de schema/valores, embora os três datasets por lado mantenham os mesmos IDs/colunas/distribuições e o input do candidato esteja exatamente compatível. Esse baseline deve ser versionado novamente em uma etapa de governança própria; ele não foi sobrescrito silenciosamente nesta consolidação.

## Principais artefatos

- `data/gold/features/role_aware/round_role_features.parquet`: visão canônica completa.
- `round_attack_features`, `round_defense_features`, `round_target_team_features`: views por entidade.
- `round_map_features`: somente features `map_abstract`/`map_specific`.
- `feature_dictionary` e `feature_aliases`: semântica, unidade, escopo e migração de nomes.
- `data/gold/modeling/mirage_ab_grouped_validation/`: OOF, métricas, folds, bootstrap, coeficientes, contrato e auditoria de isolamento.
- `data/reference/maps/awpy/2000899/mirage_asset_manifest.parquet`: inventário e checksums do mapa completo.

## Execução

```powershell
python -m src.teams.build_team_dictionary --config configs/project.yaml --force
python -m src.features.demo_timing --config configs/project.yaml --force
python -m src.features.build_role_features --config configs/project.yaml --target-map Mirage --target-team Vitality --force
python -m src.modeling.mirage_ab_grouped_validation --config configs/modeling/mirage_ab_grouped_validation.yaml --project-root . --force
python -m src.maps.sync_awpy_map_assets --map Mirage --force
```
