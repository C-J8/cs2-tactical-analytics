# Guia completo do projeto CS2 Tactical Analytics

Revisão realizada em 5 de setembro de 2026 sobre o repositório ativo em `E:\Projeto CS`.

## Visão geral

O projeto transforma demos locais de Counter-Strike 2 em tabelas auditáveis para análise tática e modelagem exploratória. A arquitetura segue camadas de dados:

1. **Raw** guarda sementes manuais, arquivos compactados e demos `.dem`.
2. **Bronze** preserva manifests, auditorias e tabelas por demo quase como o parser as produziu.
3. **Silver** consolida os eventos elegíveis entre demos.
4. **Gold** materializa estados de round, features, análises, validações e resultados de modelos.
5. **Docs e notebooks** apresentam os resultados sem assumir o papel de fonte de verdade.

O repositório contém 1.708 arquivos e aproximadamente 42,8 GiB. Há 210 arquivos de código, configuração, documentação, testes e infraestrutura. Os outros 1.498 arquivos são dados ou artefatos gerados. O inventário exato de todos os caminhos está em `inventario_completo_arquivos.csv`.

Estado verificado nesta revisão:

- `ruff check .`: aprovado.
- `pytest`: 290 testes aprovados em 99,85 segundos.
- Aviso único: um fold de teste do scikit-learn contém classe predita ausente em `y_true`; o teste passa e o aviso não representa falha.
- Git: árvore de trabalho limpa.

## Como o pipeline foi construído

### Linha principal

```text
semente manual e arquivos locais
    -> catálogo de partidas
    -> extração e manifest dos .dem
    -> identificação de mapa
    -> parsing com Awpy
    -> quality gate de parsing
    -> features temporais e espaciais
    -> resolução de lado e plant
    -> datasets T e CT
    -> EDA tática
    -> consolidação de achados
    -> dataset A/B sem vazamento
    -> baseline exploratório
    -> auditoria de prontidão e relatórios
```

### Sequência histórica dos estágios

| Estágio | Responsabilidade | Resultado principal |
|---|---|---|
| 1 | Catálogo offline de partidas | Bronze bruto e catálogo Silver |
| 2 | Download opcional ou uso de arquivos locais | Archives, demos e manifests |
| 3 e 3.5 | Parsing e identificação de mapa | Tabelas Bronze por demo |
| 3.6 | Qualidade do parsing | Lista de demos elegíveis |
| 4 | Features por round e janelas até 115 s | `round_features_mvp` |
| 4.1 | Separação por lado e progressão | T-side, CT-side e timelines |
| 4.2 | Estado canônico do round | lado, dono do plant e alvo A/B |
| 5 a 5.2 | EDA, ranking e revisão manual | achados e fila de rounds |
| 6 a 6.3 | Baseline Mirage, erros e promoção | candidato exploratório de Mirage |
| 7 | Pacote final do MVP inicial | relatório, apêndice e outline |
| 8.0 | Contrato de features | 492 features classificadas |
| 8.1 a 8.3 | Registro de mapas e regressão | Mirage protegido para expansão |
| 8.4 a 8.7 | Onboarding do Inferno | identidade, áreas e semântica |
| 8.8 a 8.9.1 | Gold multi-mapa e qualidade | Inferno materializado e reparado |
| 8.10 e 8.10.1 | EDA multi-mapa e hardening | 9 achados consolidados e auditáveis |
| 8.11 e 8.11.1 | Baseline Inferno e integridade | modelo exploratório com evidência fail-closed |
| 8.12 | Prontidão amostral | recomendação de ampliar a amostra |

### Princípios de engenharia

- **Offline first:** o seed manual e os arquivos locais continuam sendo a fonte confiável.
- **Escopo explícito:** mapa e equipe entram como parâmetros; gravações forçadas substituem apenas o escopo solicitado.
- **Idempotência:** upserts preservam outros mapas e verificam chaves estáveis.
- **Fail closed:** ausência de evidência obrigatória bloqueia features ou estágios, em vez de presumir validade.
- **Separação de responsabilidades:** análise não altera Gold central; validação não treina; promoção não retreina.
- **Proteção contra leakage:** labels, eventos futuros e janelas após o horizonte ficam fora do modelo.
- **Reprodutibilidade:** YAML congela decisões, relatórios registram auditorias e notebooks ficam sem outputs no Git.

## Snapshot atual

| Métrica | Valor |
|---|---:|
| Demos elegíveis consolidadas | 18 |
| Rounds | 527 |
| Rounds Mirage | 405 |
| Rounds Inferno | 122 |
| Rounds T-side | 245 |
| Rounds CT-side | 282 |
| T-side com plant A/B de alta confiança | 138 |
| Plant A | 94 |
| Plant B | 44 |
| T-side sem plant válido da Vitality | 107 |
| Features no contrato | 492 |
| Features avaliadas no gate Inferno | 477 |
| Testes | 290 aprovados |

O baseline Inferno usa 40 rounds plantados, 22 A e 18 B, distribuídos em cinco séries e quatro adversários. O resultado OOF tem macro F1 0,472, balanced accuracy 0,472, MCC -0,055 e ROC AUC 0,487. O status correto é `no_signal` e `exploratory_only`. O pipeline recomenda continuar a expansão da amostra, não ajustar hiperparâmetros.

## Arquivos na raiz

| Arquivo | Função |
|---|---|
| `.dockerignore` | Evita copiar dados, ambientes e arquivos desnecessários para as imagens Docker. |
| `.env.airflow.example` | Modelo das variáveis locais do Airflow, incluindo credenciais do administrador. |
| `.gitattributes` | Regras de atributos do Git para o repositório. |
| `.gitignore` | Exclui demos, dados gerados, caches, ambientes e segredos. |
| `compose.airflow.yml` | Sobe PostgreSQL, API server, scheduler, DAG processor, triggerer e inicialização do Airflow. |
| `pyproject.toml` | Define pacote, Python 3.11/3.12, dependências, Ruff e Pytest. |
| `README.md` | Documento mestre do estágio atual, comandos, contratos e histórico completo. |
| `requirements.txt` | Entrada curta para instalar o conjunto principal de dependências. |
| `requirements.lock` | Versões travadas para execução do pipeline. |
| `requirements-dev.lock` | Versões travadas para desenvolvimento, lint e testes. |

## Infraestrutura, CI e orquestração

| Arquivo | Função |
|---|---|
| `.github/workflows/ci.yml` | Executa Ruff e 290 testes em Python 3.11 e 3.12; depois monta a imagem Airflow e valida imports das DAGs. |
| `docker/Dockerfile.pipeline` | Imagem Python mínima para executar os módulos do pipeline. |
| `docker/Dockerfile.airflow` | Imagem Airflow 3.3.1 com dependências do projeto. |
| `scripts/check_airflow_dags.py` | Importa e valida todas as DAGs, falhando a CI se houver erro. |
| `dags/__init__.py` | Marca o pacote de DAGs. |
| `dags/_common.py` | Converte cada CLI `python -m src...` em uma task isolada, com retry e `PYTHONPATH` controlado. |
| `dags/cs2_demo_ingestion.py` | Encadeia catálogo, arquivos locais, probe, parsing e quality gate. |
| `dags/cs2_gold_materialization.py` | Dispara o pipeline de features por mapa e o gate de preservação multi-mapa. |
| `dags/cs2_inferno_analysis_modeling.py` | Encadeia qualidade, reparo, EDA, hardening, dataset A/B, baseline Inferno e prontidão amostral. |

As DAGs são manuais, aceitam poucos parâmetros, usam `LocalExecutor`, limitam-se a uma execução ativa e trocam apenas caminhos ou status pequenos. O código de negócio permanece em `src/`.

## Configurações

| Arquivo | Função |
|---|---|
| `configs/project.yaml` | Configuração central de datas, mapas, equipe, diretórios, parser, tabelas e janelas de 0 a 115 s. |
| `configs/teams.yaml` | Identidades e aliases das equipes. |
| `configs/player_rosters.yaml` | Elencos usados para inferir a equipe do jogador e o dono do plant. |
| `configs/maps.yaml` | Mapeamento legado de nomes e aliases de mapas. |
| `configs/maps/map_registry.yaml` | Índice canônico multi-mapa com versão e status. |
| `configs/maps/mirage.yaml` | Geometria, regiões físicas, semânticas e bombsites de Mirage. |
| `configs/maps/mirage_regions.yaml` | Mapeamento legado de `place` para regiões de Mirage. |
| `configs/maps/inferno.yaml` | Registro ativo do Inferno e sua topologia semântica. |
| `configs/maps/region_mapping/inferno.yaml` | Crosswalk auditado de lugares brutos para regiões físicas e grupos táticos. |
| `configs/features/feature_contract.yaml` | Contrato congelado de escopo, leakage, comparabilidade, materialização e usos permitidos. |
| `configs/quality/map_feature_quality.yaml` | Limiares de missingness, degeneração, domínio, semântica e tamanho amostral. |
| `configs/analysis/multi_map_tactical_eda.yaml` | Coortes, bootstrap por demo, exposição temporal e critérios de ranking multi-mapa. |
| `configs/analysis/tactical_finding_hardening.yaml` | Regras de consolidação, sensibilidade, taxonomia e limites do ranking final. |
| `configs/modeling/t_side_ab_candidate_baseline.yaml` | Especificação congelada do candidato de Mirage promovido no estágio 6.3. |
| `configs/modeling/inferno_ab_exploratory.yaml` | Horizonte 35 s, LOGO, regressão logística, nulidade, bootstrap e conjunto candidato do Inferno. |
| `configs/modeling/inferno_sample_expansion.yaml` | Metas mínimas de demos, séries, classes, oponentes e rounds para nova avaliação. |

## Código-fonte: `src/config`

| Arquivo | Função |
|---|---|
| `src/config/__init__.py` | Marca o pacote de configuração. |
| `src/config/schemas.py` | Modelos Pydantic e carregadores tipados para projeto, mapas, equipes e catálogo. |

## Código-fonte: `src/ingestion`

| Arquivo | Função |
|---|---|
| `src/ingestion/__init__.py` | Marca o pacote de ingestão. |
| `src/ingestion/manual_loader.py` | Lê o seed manual e completa colunas opcionais ausentes. |
| `src/ingestion/hltv_client.py` | Cliente conservador para enriquecer metadados de páginas HLTV quando permitido. |
| `src/ingestion/validators.py` | Padroniza nomes, cria IDs estáveis, identifica adversário e detecta duplicatas. |
| `src/ingestion/build_match_catalog.py` | Constrói o catálogo Bronze/Silver e aplica validações. |
| `src/ingestion/demo_downloader.py` | Baixa arquivos com sessão HTTP, timeout, hash e detecção segura de extensão. |
| `src/ingestion/archive_extractor.py` | Extrai ZIP/RAR/7z, normaliza nomes e registra demos encontradas. |
| `src/ingestion/download_demos.py` | Orquestra download, reutilização local, extração e manifest de demos. |
| `src/ingestion/scan_local_archives.py` | Varre archives e `.dem`, infere metadados e trata demos divididas em partes. |

## Código-fonte: `src/parsing`

| Arquivo | Função |
|---|---|
| `src/parsing/__init__.py` | Marca o pacote de parsing. |
| `src/parsing/awpy_parser.py` | Adaptador do Awpy; normaliza DataFrames e eventos retornados pelo parser. |
| `src/parsing/probe_dem_metadata.py` | Obtém o mapa real de cada demo antes do parsing completo. |
| `src/parsing/parse_demos.py` | Seleciona demos por mapa/equipe, processa falhas isoladamente e preserva outros escopos. |
| `src/parsing/parsed_tables.py` | Acrescenta colunas de rastreio e grava Bronze por demo e Silver consolidado. |
| `src/parsing/parse_manifest.py` | Mantém o manifest idempotente do parsing. |
| `src/parsing/parse_audit.py` | Registra sucessos, falhas, tempos e mensagens de erro. |
| `src/parsing/parse_quality.py` | Classifica a qualidade e publica `feature_eligible_demos`. |

## Código-fonte: `src/features`

| Arquivo | Função |
|---|---|
| `src/features/__init__.py` | Marca o pacote de feature engineering. |
| `src/features/feature_windows.py` | Representa janelas intervalares e cumulativas e corta eventos pelo tempo do round. |
| `src/features/round_context.py` | Constrói a linha-base do round, score anterior, vencedor e bombsite. |
| `src/features/region_mapping.py` | Resolve `place` para região usando o registro de mapas. |
| `src/features/position_features.py` | Calcula presença regional, centro da equipe, dispersão e jogadores vivos. |
| `src/features/utility_features.py` | Reconstrói inventário e uso de smoke, flash, HE e molotov por janela. |
| `src/features/bomb_context.py` | Produz timeline do portador da C4 e eventos de drop. |
| `src/features/death_context.py` | Resume mortes, ordem das baixas e contexto regional. |
| `src/features/round_progression.py` | Monta timelines de regiões, outcomes e assinaturas de progressão. |
| `src/features/feature_audit.py` | Resume completude e sanidade das features geradas. |
| `src/features/map_refactor_audit.py` | Compara schema e valores antes/depois da refatoração multi-mapa. |
| `src/features/build_round_features.py` | Junta todas as famílias e grava `round_features_mvp`. |
| `src/features/round_state.py` | Resolve lado da Vitality, plant próprio, label A/B e confiança do estado. |
| `src/features/side_dataset_audit.py` | Audita contagens e labels dos datasets por lado. |
| `src/features/side_datasets.py` | Gera T-side all, T-side planted, CT-side e tabelas de progressão. |
| `src/features/build_feature_contract.py` | Classifica as 492 features por família, horizonte, leakage, mapa e uso. |
| `src/features/run_map_pipeline.py` | Executa features, estado, datasets por lado e gate Gold para um mapa ativo. |

## Código-fonte: `src/maps`

| Arquivo | Função |
|---|---|
| `src/maps/__init__.py` | Marca o pacote de mapas. |
| `src/maps/registry.py` | Carrega e valida regiões físicas, grupos semânticos, bombsites e referências. |
| `src/maps/identity.py` | Canonicaliza aliases como `de_inferno`, `Inferno` e nomes equivalentes. |
| `src/maps/geometry.py` | Testa pontos em bounding boxes e polígonos, incluindo eixo Z. |
| `src/maps/place_columns.py` | Detecta qual coluna do parser representa o local do jogador. |
| `src/maps/semantic.py` | Traduz regiões físicas em conceitos comuns, como controle de meio e pressão A/B. |
| `src/maps/build_map_registry.py` | Migra Mirage para o registro versionado e gera tabelas de cobertura. |
| `src/maps/onboard_map.py` | Verifica se um novo mapa possui dados e metadados suficientes para avançar. |
| `src/maps/discover_map_areas.py` | Descobre `place`, cobertura por demo/round e perfis X/Y/Z sem editar o registro. |
| `src/maps/build_region_mapping.py` | Constrói o crosswalk físico/semântico do Inferno e audita portabilidade. |

## Código-fonte: `src/storage` e `src/utils`

| Arquivo | Função |
|---|---|
| `src/storage/__init__.py` | Marca o pacote de armazenamento. |
| `src/storage/scoped_gold.py` | Implementa upsert Gold por mapa/equipe, valida chaves e grava de forma atômica. |
| `src/utils/__init__.py` | Marca o pacote de utilitários. |
| `src/utils/io.py` | Centraliza leitura e escrita CSV/Parquet, fallback e criação de diretórios. |
| `src/utils/logging.py` | Configura logging consistente para todas as CLIs. |
| `src/utils/text.py` | Normaliza chaves, strings e slugs. |
| `src/utils/reports.py` | Oferece data UTC, divisão segura e renderização de tabelas Markdown. |
| `src/utils/notebooks.py` | Cria notebooks de inspeção sem outputs incorporados. |

## Código-fonte: `src/analysis`

| Arquivo | Função |
|---|---|
| `src/analysis/__init__.py` | Marca o pacote de análises Gold. |
| `src/analysis/t_side_eda.py` | EDA original de Mirage por site, utilidade, regiões, falhas e progressão. |
| `src/analysis/t_side_findings.py` | Converte agregados do EDA em diferenças A/B e achados conservadores. |
| `src/analysis/t_side_manual_review.py` | Liga achados a rounds concretos e cria o ledger de revisão humana. |
| `src/analysis/multi_map_tactical_eda.py` | Compara mapas com bootstrap por demo e exclui features não comparáveis. |
| `src/analysis/tactical_finding_hardening.py` | Consolida candidatos redundantes e aplica exposição, LODO, adversário e taxonomia. |

## Código-fonte: `src/modeling`

| Arquivo | Função |
|---|---|
| `src/modeling/__init__.py` | Marca o pacote de modelagem controlada. |
| `src/modeling/t_side_ab_baseline.py` | Treina baselines de Mirage em vários horizontes com predições OOF. |
| `src/modeling/t_side_ab_error_analysis.py` | Interpreta erros do baseline sem retreinar. |
| `src/modeling/t_side_ab_refined_experiment.py` | Compara conjuntos fixos de features e horizontes contra o baseline. |
| `src/modeling/t_side_ab_candidate_promotion.py` | Seleciona, congela e documenta o candidato exploratório de Mirage. |
| `src/modeling/build_map_ab_dataset.py` | Monta dataset A/B por mapa e aprova features somente com evidência completa. |
| `src/modeling/inferno_ab_exploratory_baseline.py` | Executa LOGO, nulidade, bootstrap, ablações e erros OOF no Inferno. |
| `src/modeling/inferno_sample_expansion.py` | Mede independência e diversidade da amostra sem alterar o baseline congelado. |

## Código-fonte: `src/validation`

| Arquivo | Função |
|---|---|
| `src/validation/__init__.py` | Marca o pacote de gates e regressões. |
| `src/validation/mirage_regression_gate.py` | Compara 16 datasets e invariantes com um baseline congelado de Mirage. |
| `src/validation/multi_map_parse_gate.py` | Verifica escopo, identidade, preservação Silver e prontidão de `place`. |
| `src/validation/multi_map_gold_gate.py` | Verifica upserts Gold, colisões, preservação Mirage e materialização do novo mapa. |
| `src/validation/map_feature_quality_gate.py` | Audita reconciliação, missingness, domínio, degeneração, semântica e labels. |
| `src/validation/feature_materialization_repair.py` | Reconstrói flash/HE, corrige score anterior e reexecuta a qualidade sem baixar limites. |

## Código-fonte: `src/reporting`

| Arquivo | Função |
|---|---|
| `src/reporting/__init__.py` | Marca o pacote de reporting. |
| `src/reporting/build_final_mvp_report.py` | Consolida estágios 1 a 7 em relatório, apêndice, outline, notebook e manifests. |

## Documentação

| Arquivo | Função |
|---|---|
| `docs/airflow.md` | Arquitetura local, inicialização e regras operacionais do Airflow. |
| `docs/feature_contract.md` | Explica contrato, leakage, mapas e usos permitidos das features. |
| `docs/feature_materialization_repair.md` | Documenta o reparo do estágio 8.9.1. |
| `docs/final_mvp_report.md` | Relatório executivo do MVP original de Mirage. |
| `docs/final_mvp_technical_appendix.md` | Linhagem, gates, métricas e comandos reprodutíveis do MVP. |
| `docs/final_presentation_outline.md` | Estrutura de 15 slides gerada pelo estágio 7. |
| `docs/inferno_ab_exploratory_baseline.md` | Relatório completo do baseline A/B do Inferno. |
| `docs/inferno_feature_pipeline.md` | Execução Gold do Inferno e preservação multi-mapa. |
| `docs/inferno_feature_quality.md` | Perfil de 477 features e prontidão exploratória. |
| `docs/inferno_onboarding_report.md` | Entrada conservadora do Inferno como primeiro novo mapa. |
| `docs/inferno_region_mapping.md` | Lugares, regiões físicas e grupos semânticos do Inferno. |
| `docs/inferno_sample_expansion.md` | Lacunas amostrais e próximos alvos de aquisição. |
| `docs/map_area_discovery.md` | Método genérico de descoberta de áreas por `place` e coordenadas. |
| `docs/map_geometry_region_registry.md` | Design do registro de mapas e geometrias. |
| `docs/map_ready_feature_refactor.md` | Arquitetura antes/depois da remoção de regras específicas de Mirage. |
| `docs/mirage_regression_gate.md` | Proteção de compatibilidade após a refatoração. |
| `docs/modeling_integrity_refactor_regression.md` | Evidência fail-closed, métricas completas e regressão dos helpers. |
| `docs/multi_map_parsing.md` | Identidade canônica e upsert seguro no parsing. |
| `docs/notebook_inventory.md` | Classifica notebooks atuais e históricos. |
| `docs/t_side_ab_baseline_report.md` | Baseline A/B de Mirage por horizonte. |
| `docs/t_side_ab_candidate_baseline_report.md` | Relatório do candidato promovido de Mirage. |
| `docs/t_side_ab_candidate_model_card.md` | Uso, dados, limitações e decisão do candidato. |
| `docs/t_side_ab_error_analysis_report.md` | Erros, classes, adversários e fila de revisão. |
| `docs/t_side_ab_refined_experiment_report.md` | Experimento controlado de refinamento. |
| `docs/t_side_manual_review_pack.md` | Protocolo de validação humana dos achados. |
| `docs/t_side_tactical_findings.md` | Achados descritivos originais de Mirage. |
| `docs/vitality_mirage_vs_inferno_eda.md` | EDA comparativa multi-mapa antes do hardening. |
| `docs/vitality_multi_map_tactical_findings.md` | Achados consolidados com caveats de exposição e estabilidade. |

## Notebooks

Os notebooks são visões de inspeção, não a fonte de verdade. Permanecem sem outputs no Git.

| Arquivo | Função |
|---|---|
| `notebooks/01_validate_match_catalog.ipynb` | Inspeciona o catálogo de partidas. |
| `notebooks/02_validate_parsed_demo.ipynb` | Inspeciona tabelas de uma demo parseada. |
| `notebooks/03_feature_engineering_mvp.ipynb` | Inspeciona features e janelas temporais. |
| `notebooks/04_side_datasets_and_progression.ipynb` | Inspeciona T-side, CT-side e progressão. |
| `notebooks/05_round_state_resolution.ipynb` | Inspeciona lado, plant e qualidade das labels. |
| `notebooks/06_t_side_tactical_eda.ipynb` | EDA original de Mirage. |
| `notebooks/07_t_side_tactical_findings.ipynb` | Achados e diferenças A/B de Mirage. |
| `notebooks/08_t_side_manual_review_pack.ipynb` | Rounds escolhidos para revisão humana. |
| `notebooks/09_t_side_ab_baseline_model.ipynb` | Métricas do baseline Mirage. |
| `notebooks/10_t_side_ab_error_analysis.ipynb` | Erros do baseline Mirage. |
| `notebooks/11_t_side_ab_refined_experiment.ipynb` | Comparação de conjuntos refinados. |
| `notebooks/12_t_side_ab_candidate_promotion.ipynb` | Pacote do candidato selecionado. |
| `notebooks/13_final_mvp_report_pack.ipynb` | Inspeção do pacote final do MVP. |
| `notebooks/14_feature_contract.ipynb` | Inventário do contrato de features. |
| `notebooks/15_map_region_registry.ipynb` | Regiões, semântica, bombsites e cobertura. |
| `notebooks/16_map_ready_feature_refactor.ipynb` | Auditoria da refatoração multi-mapa. |
| `notebooks/17_mirage_regression_gate.ipynb` | Comparações e falhas do gate Mirage. |
| `notebooks/18_inferno_onboarding.ipynb` | Estado inicial do onboarding Inferno. |
| `notebooks/19_multi_map_parsing.ipynb` | Preservação e prontidão do parsing multi-mapa. |
| `notebooks/20_map_area_discovery.ipynb` | Perfis de `place` e coordenadas. |
| `notebooks/21_inferno_region_mapping.ipynb` | Crosswalk e semântica do Inferno. |
| `notebooks/22_inferno_feature_pipeline.ipynb` | Inventário Gold do Inferno. |
| `notebooks/23_inferno_feature_quality.ipynb` | Missingness, degeneração e scorecard. |
| `notebooks/24_feature_materialization_repair.ipynb` | Evidências e efeitos do reparo. |
| `notebooks/25_vitality_multi_map_tactical_eda.ipynb` | Visão atual da EDA Mirage versus Inferno. |
| `notebooks/26_tactical_finding_hardening.ipynb` | Visão atual dos achados consolidados. |
| `notebooks/27_inferno_ab_exploratory_baseline.ipynb` | Visão atual do modelo Inferno. |
| `notebooks/29_inferno_sample_expansion.ipynb` | Visão atual da prontidão amostral. |

O número 28 não existe. A sequência salta de 27 para 29; isso não quebra o pipeline, mas vale normalizar em uma futura organização.

## Testes

| Arquivo | Principal cobertura |
|---|---|
| `tests/test_archive_extractor.py` | ZIP/RAR, nomes seguros e localização de `.dem`. |
| `tests/test_awpy_parser.py` | Adaptador Awpy e normalização de retornos. |
| `tests/test_cli.py` | CLI do catálogo ponta a ponta. |
| `tests/test_config.py` | Carregamento de YAML e janelas até 115 s. |
| `tests/test_demo_downloader.py` | Download, redirect, extensão, cache e bloqueio remoto. |
| `tests/test_discover_map_areas.py` | Escopo canônico, `place`, X/Y/Z, crosswalk e isolamento. |
| `tests/test_download_demos_cli.py` | Dry run, arquivos locais, extração e manifests. |
| `tests/test_feature_contract.py` | Classificação, leakage, comparabilidade e não alteração de upstream. |
| `tests/test_feature_materialization_repair.py` | Dry run e fixtures do reparo. |
| `tests/test_features_mvp.py` | Contexto do round, regiões, utilidade, janelas e auditorias. |
| `tests/test_final_mvp_report.py` | Docs, notebook, estágios, snapshot e manifest final. |
| `tests/test_inferno_ab_exploratory.py` | Dataset, fail-closed, LOGO, nulidade, métricas e erros OOF. |
| `tests/test_inferno_onboarding.py` | Precondições, ausência de dados, registro e cobertura. |
| `tests/test_inferno_sample_expansion.py` | Gates, deduplicação, lacunas, prontidão e segurança. |
| `tests/test_manual_loader.py` | Colunas faltantes no seed manual. |
| `tests/test_map_feature_quality_gate.py` | Integridade, missingness, domínios, semântica, labels e upsert. |
| `tests/test_map_identity.py` | Aliases, mapas conhecidos e falha explícita. |
| `tests/test_map_ready_feature_refactor.py` | Geometria, semântica e compatibilidade de features. |
| `tests/test_map_registry.py` | Geração, referências, YAML inválido e cobertura do contrato. |
| `tests/test_mirage_regression_gate.py` | Baseline, schema, linhas, valores, tolerância e invariantes. |
| `tests/test_multi_map_parse_gate.py` | Saídas, `place` e bloqueio sem coordenadas. |
| `tests/test_multi_map_tactical_eda.py` | Coortes, exclusões, bootstrap e auditoria somente leitura. |
| `tests/test_parse_demos_cli.py` | Seleção, erros, escopo, força idempotente e reset explícito. |
| `tests/test_parse_manifest.py` | Schema e gravação do manifest. |
| `tests/test_parse_quality.py` | Elegibilidade, demos curtas, falhas e preservação multi-mapa. |
| `tests/test_probe_dem_metadata.py` | Inferência, fallback, erro controlado e dry run. |
| `tests/test_refactor_regression.py` | Contratos dos helpers de escrita. |
| `tests/test_region_mapping.py` | Gate anterior, crosswalk, portabilidade e coordenadas suspeitas. |
| `tests/test_round_state.py` | Lado, roster, plants, labels, audit e dry run. |
| `tests/test_scan_local_archives.py` | Varredura, extração, splits e manifests. |
| `tests/test_scoped_gold.py` | Upsert por escopo, chaves duplicadas e idempotência. |
| `tests/test_side_datasets.py` | Separação T/CT, progressão, mortes, C4 e precondição. |
| `tests/test_t_side_ab_baseline.py` | Amostra A/B, leakage, métricas e outputs. |
| `tests/test_t_side_ab_candidate_promotion.py` | Seleção única, congelamento, erros e documentação. |
| `tests/test_t_side_ab_error_analysis.py` | Erros, confiança, adversário, contrastes e fila manual. |
| `tests/test_t_side_ab_refined_experiment.py` | Feature sets, comparação e recomendação. |
| `tests/test_t_side_eda.py` | Contagens, janelas e catálogo de leakage. |
| `tests/test_t_side_findings.py` | Achados, timing, no-plant e Markdown. |
| `tests/test_t_side_manual_review.py` | Seleção de rounds, decisões pendentes e readiness. |
| `tests/test_tactical_finding_hardening.py` | Direção, exposição, LODO, consolidação e taxonomia. |
| `tests/test_utils_shared.py` | CSV/Parquet, fallback, empty frames, Markdown e notebooks. |
| `tests/test_validators.py` | Aliases, duplicatas, adversário e persistência. |

## Dados e artefatos gerados

### `data/raw`

Contém 79 arquivos e cerca de 42,0 GiB. `manual/matches_seed.csv` é o único arquivo de dados pequeno versionado. `demo_archives/Vitality/` guarda 19 arquivos RAR e `demos/vitality/` guarda 59 demos extraídas. Os nomes codificam evento, equipes, formato e mapa.

### `data/bronze`

Contém 781 arquivos e cerca de 0,48 GiB.

| Família | Função |
|---|---|
| `match_catalog_raw` | Snapshot antes da transformação canônica. |
| `demo_manifest` | Resultado do download ou registro local. |
| `local_archive_manifest` | Archives encontrados e extraídos. |
| `dem_files_manifest` | Cada `.dem`, mapa inferido, hash e elegibilidade. |
| `parsed_demos/Vitality/...` | Tabelas por demo, incluindo eventos detalhados. |
| `parse_manifest` | Estado idempotente de cada parsing. |
| `parse_quality` | Classificação de qualidade por demo. |
| `parse_audit` | Histórico operacional e falhas. |

### `data/silver`

Contém 14 arquivos e cerca de 0,24 GiB. O catálogo aparece em CSV e Parquet. As tabelas consolidadas do parser são `rounds`, `kills`, `damages`, `shots`, `bomb`, `smokes`, `infernos`, `grenades`, `footsteps` e `ticks`. `feature_eligible_demos` determina quais demos alimentam Gold.

### `data/gold`

Contém 624 arquivos e cerca de 0,07 GiB.

| Família | Função |
|---|---|
| `round_features` | Dataset mestre e recortes T/CT. |
| `round_state` | Estado, lado, plant e labels. |
| `round_progression` | Timelines de regiões, C4, mortes e outcome. |
| `utility_events` e `region_presence` | Evidências normalizadas de utilidade e posição. |
| `feature_audit` | Qualidade e compatibilidade das features. |
| `features/feature_contract` | Contrato, readiness e unknowns. |
| `maps/map_registry` | Tabelas canônicas do registro. |
| `maps/area_discovery` | Frequência, coordenadas e crosswalk de `place`. |
| `maps/inferno` | Onboarding, region mapping e auditorias do Inferno. |
| `validation/multi_map_parsing` | Preservação e prontidão do Silver. |
| `validation/multi_map_gold` | Preservação e integridade do Gold. |
| `validation/map_feature_quality` | Perfil de qualidade do Inferno. |
| `validation/feature_materialization_repair` | Evidências do reparo 8.9.1. |
| `validation/mirage_regression_*` | Baseline e comparações que protegem Mirage. |
| `analysis/t_side_*` | EDA, achados e revisão manual do MVP Mirage. |
| `analysis/multi_map_tactical_eda` | Comparações Mirage versus Inferno. |
| `analysis/tactical_finding_hardening` | Consolidação, caveats e ranking final. |
| `modeling/t_side_ab_*` | Baseline, refinamento, candidato e erros de Mirage. |
| `modeling/inferno_ab_exploratory` | Dataset, predições OOF, métricas, coeficientes e auditorias. |
| `modeling/inferno_sample_expansion` | Inventário, gaps, concentração e alvos de novos dados. |
| `reporting/final_mvp` | Tabelas usadas no pacote final inicial. |

Muitas saídas aparecem em par CSV/Parquet. O CSV favorece inspeção e diffs; o Parquet preserva tipos, reduz tamanho e é a prioridade de leitura.

## Airflow em termos práticos

O Airflow não substitui as CLIs. Cada task executa um módulo existente por subprocesso.

```text
cs2_demo_ingestion
catálogo -> archives -> probe -> parser -> parse quality

cs2_gold_materialization
run_map_pipeline
    -> round features
    -> round state
    -> side datasets
    -> multi-map Gold gate

cs2_inferno_analysis_modeling
quality -> repair -> EDA -> hardening -> A/B dataset -> baseline -> readiness
```

Os Assets `cs2://silver/parse-quality`, `cs2://gold/scoped-map-features` e `cs2://gold/inferno-analysis-modeling` tornam os limites observáveis, mas ainda não agendam uma cadeia automática. A ordem operacional continua manual: ingestão, materialização Gold e análise/modelagem.

## Pontos fortes

- A linhagem entre arquivos locais e cada linha analítica é explícita.
- Os upserts por escopo reduzem o risco de apagar Mirage ao processar Inferno.
- A refatoração multi-mapa preserva compatibilidade por gates formais.
- Qualidade, análise, modelagem e promoção têm limites bem definidos.
- O baseline Inferno registra `no_signal` sem tentar maquiar a amostra pequena.
- A suíte testa casos de segurança, idempotência, leakage e regressão, não apenas caminhos felizes.

## Pontos de atenção

- Os 19 archives e 59 demos ocupam quase todo o espaço local; a política de retenção ainda é manual.
- O pipeline é local e compartilhado, então `max_active_runs=1` continua necessário.
- O Airflow cobre o fluxo atual, mas alguns estágios históricos permanecem disponíveis somente como CLIs.
- O baseline Inferno tem apenas cinco grupos; ainda não suporta uma conclusão preditiva confiável.
- Há 166 avisos no gate de qualidade do Inferno, majoritariamente degeneração e diferenças cross-map; nenhum bloqueia, mas devem continuar visíveis.
- A numeração dos notebooks não possui item 28.
- Dashboards, BigQuery, object storage e execução distribuída ainda não existem.

## Próxima evolução coerente

1. Adicionar pelo menos cinco demos e três séries independentes do Inferno, buscando mais adversários e maior cobertura da classe B.
2. Reexecutar ingestão, parsing, Gold, qualidade e o estágio 8.12 com o baseline congelado.
3. Só considerar nova avaliação do modelo quando as metas de 10 demos, 8 séries, 80 rounds plantados, 30 exemplos por classe e 5 adversários forem atendidas.
4. Definir retenção para archives/demos e armazenamento de objetos antes de paralelizar o Airflow.
5. Criar dashboard somente depois de estabilizar o contrato de consumo e escolher quais achados passaram por revisão humana.

## Fontes locais usadas

- `README.md`
- `docs/airflow.md`
- `docs/notebook_inventory.md`
- `docs/final_mvp_technical_appendix.md`
- `docs/inferno_feature_quality.md`
- `docs/modeling_integrity_refactor_regression.md`
- `docs/inferno_sample_expansion.md`
- `dags/*.py`
- `configs/**/*.yaml`
- `src/**/*.py`
- `tests/**/*.py`
- artefatos sob `data/`

