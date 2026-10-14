import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const workspaceDir = "C:\\Users\\celso\\OneDrive\\Documentos\\ChatGPT\\Projeto CS";
const SKILL_DIR = "C:\\Users\\celso\\.codex\\plugins\\cache\\openai-primary-runtime\\presentations\\26.904.11930\\skills\\presentations";
const RUNTIME_PYTHON = "C:\\Users\\celso\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe";
const FINAL_PPTX = path.join(workspaceDir, "entregaveis", "revisao_projeto_cs_pipeline_v2.pptx");
const stagingDir = path.join(workspaceDir, ".codex-finalizer");

const { resolvePresentationFont, applyPresentationChartFont, makeNativeBulletParagraphs, finalizePresentation } = await import(
  pathToFileURL(path.join(SKILL_DIR, "container_tools", "artifact_tool_utils.mjs")).href,
);

const family = resolvePresentationFont();
const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });

const C = {
  bg: "#07111F",
  bg2: "#0C1928",
  panel: "#102235",
  ink: "#F4F7FB",
  muted: "#9CB0C4",
  faint: "#52677C",
  cyan: "#35D0E8",
  teal: "#29B8A6",
  amber: "#F3A640",
  red: "#FF6B6B",
  green: "#69D48C",
  white: "#FFFFFF",
};

const coverBytes = await fs.readFile(path.join(workspaceDir, "entregaveis", "assets", "capa_pipeline_cs2.png"));
const multiMapBytes = await fs.readFile(path.join(workspaceDir, "entregaveis", "assets", "arquitetura_multimapa_cs2.png"));

function addText(slide, text, x, y, w, h, options = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    typeface: family,
    fontSize: options.fontSize ?? 24,
    bold: options.bold ?? false,
    color: options.color ?? C.ink,
    alignment: options.align ?? "left",
    verticalAlignment: options.valign ?? "top",
    autoFit: options.autoFit ?? "none",
    wrap: "square",
    lineSpacing: options.lineSpacing ?? 1.0,
    insets: options.insets ?? { top: 0, right: 0, bottom: 0, left: 0 },
  };
  return shape;
}

function addRule(slide, x, y, w, color = C.faint, height = 2) {
  return slide.shapes.add({
    geometry: "rect",
    position: { left: x, top: y, width: w, height },
    fill: color,
    line: { fill: "none", width: 0 },
  });
}

function addTitle(slide, title, section, number) {
  addText(slide, section.toUpperCase(), 64, 34, 340, 24, { fontSize: 14, bold: true, color: C.cyan });
  addText(slide, title, 64, 65, 1120, 58, { fontSize: 34, bold: true, color: C.ink });
  addRule(slide, 64, 127, 1152, C.faint, 1);
  addText(slide, String(number).padStart(2, "0"), 1164, 38, 52, 22, { fontSize: 13, color: C.muted, align: "right" });
}

function addFooter(slide, text = "Fonte: repositório local E:\\Projeto CS") {
  addRule(slide, 64, 674, 1152, "#26394C", 1);
  addText(slide, text, 64, 684, 1152, 18, { fontSize: 11, color: C.faint });
}

function addBullets(slide, items, x, y, w, h, options = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { fill: "none", width: 0 },
  });
  shape.text = makeNativeBulletParagraphs(items, {
    marginLeftPoints: options.marginLeftPoints ?? 18,
    hangingPoints: options.hangingPoints ?? 9,
    spaceAfterPoints: options.spaceAfterPoints ?? 8,
  });
  shape.text.style = {
    typeface: family,
    fontSize: options.fontSize ?? 22,
    color: options.color ?? C.ink,
    autoFit: "none",
    wrap: "square",
    lineSpacing: options.lineSpacing ?? 1.0,
    insets: { top: 0, right: 0, bottom: 0, left: 0 },
  };
  return shape;
}

function addNode(slide, title, body, x, y, w, h, accent = C.cyan, options = {}) {
  const node = slide.shapes.add({
    geometry: "roundRect",
    position: { left: x, top: y, width: w, height: h },
    fill: options.fill ?? C.panel,
    line: { style: "solid", fill: accent, width: options.lineWidth ?? 2 },
    borderRadius: options.radius ?? 18,
  });
  addText(slide, title, x + 16, y + 14, w - 32, 32, { fontSize: options.titleSize ?? 21, bold: true, color: accent });
  if (body) {
    addText(slide, body, x + 16, y + 50, w - 32, h - 62, { fontSize: options.bodySize ?? 16, color: options.bodyColor ?? C.ink, lineSpacing: 1.03 });
  }
  return node;
}

function connect(slide, from, to, options = {}) {
  return slide.shapes.connect(from, to, {
    kind: options.kind ?? "straight",
    fromSide: options.fromSide ?? "right",
    toSide: options.toSide ?? "left",
    line: { style: options.style ?? "solid", fill: options.color ?? C.faint, width: options.width ?? 2 },
    tail: { type: options.head ?? "triangle", width: "sm", length: "sm" },
  });
}

function addMetric(slide, value, label, x, y, w, accent = C.cyan, options = {}) {
  addText(slide, value, x, y, w, 62, { fontSize: options.valueSize ?? 44, bold: true, color: accent, align: options.align ?? "left" });
  addText(slide, label, x, y + 58, w, 48, { fontSize: options.labelSize ?? 16, color: C.muted, align: options.align ?? "left", lineSpacing: 1.0 });
}

function slideBase(title, section, number, notes, footerText) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  addTitle(slide, title, section, number);
  addFooter(slide, footerText);
  slide.speakerNotes.textFrame.setText(notes);
  return slide;
}

// 1. Cover
{
  const slide = presentation.slides.add();
  slide.images.add({
    blob: coverBytes,
    contentType: "image/png",
    alt: "Ilustração de uma arena tática abstrata conectada a camadas de dados",
    fit: "cover",
    position: { left: 0, top: 0, width: 1280, height: 720 },
  });
  addText(slide, "CS2 Tactical\nAnalytics", 68, 126, 510, 180, { fontSize: 58, bold: true, color: C.white, lineSpacing: 0.9 });
  addText(slide, "Revisão do repositório e do pipeline completo", 72, 328, 470, 68, { fontSize: 25, color: "#C9D8E7", lineSpacing: 1.05 });
  addRule(slide, 72, 423, 116, C.cyan, 5);
  addText(slide, "Vitality, Mirage e Inferno\nImplementação atual até o estágio 8.12", 72, 452, 430, 72, { fontSize: 18, color: C.muted, lineSpacing: 1.15 });
  addText(slide, "5 set 2026", 72, 646, 220, 24, { fontSize: 13, color: C.faint });
  slide.speakerNotes.textFrame.setText("Fontes: E:\\Projeto CS\\README.md e estrutura local. Ilustração de capa gerada por IA para esta revisão.");
}

// 2. What it delivers
{
  const slide = slideBase(
    "O que o projeto entrega",
    "Visão geral",
    2,
    "Fonte: E:\\Projeto CS\\README.md, seção Current Status.",
  );
  addText(slide, "O repositório transforma demos locais em evidência tática rastreável e em modelos exploratórios com limites explícitos.", 74, 158, 1110, 78, { fontSize: 27, color: C.ink, lineSpacing: 1.08 });
  const xs = [74, 304, 534, 764, 994];
  const nodes = [
    ["Demos locais", "RAR e DEM\nseed manual"],
    ["Eventos", "Awpy\nBronze e Silver"],
    ["Features", "tempo, região\ne estado do round"],
    ["Evidência", "EDA, gates\ne revisão humana"],
    ["Modelos", "A/B exploratório\ne prontidão"],
  ].map((d, i) => addNode(slide, d[0], d[1], xs[i], 315, 190, 148, i === 4 ? C.amber : C.cyan, { bodySize: 18 }));
  for (let i = 0; i < nodes.length - 1; i += 1) connect(slide, nodes[i], nodes[i + 1], { color: i === 3 ? C.amber : C.teal });
  addText(slide, "Fora do escopo atual", 76, 522, 230, 30, { fontSize: 18, bold: true, color: C.amber });
  addText(slide, "deployment, dashboard, BigQuery e execução distribuída", 76, 558, 900, 40, { fontSize: 22, color: C.muted });
}

// 3. Repository scale
{
  const slide = slideBase(
    "Escala do repositório",
    "Inventário",
    3,
    "Fontes: inventário local gerado nesta revisão e E:\\Projeto CS\\README.md.",
  );
  addMetric(slide, "1.708", "arquivos no total", 72, 158, 210, C.cyan);
  addMetric(slide, "42,8 GiB", "tamanho local aproximado", 302, 158, 250, C.amber);
  addMetric(slide, "1.498", "arquivos de dados gerados", 576, 158, 250, C.teal);
  addMetric(slide, "210", "arquivos humanos e de suporte", 846, 158, 300, C.ink);
  const chart = slide.charts.add("bar", {
    position: { left: 72, top: 312, width: 690, height: 320 },
    categories: ["Código-fonte", "Testes", "Docs", "Notebooks", "Configs"],
    series: [{ name: "Arquivos", values: [77, 42, 28, 28, 16], fill: C.cyan }],
    barOptions: { direction: "bar", grouping: "clustered", gapWidth: 45 },
    hasLegend: false,
    xAxis: { visible: false, majorGridlines: null },
    yAxis: { textStyle: { fill: C.ink, fontSize: 15 }, line: { style: "solid", fill: C.faint, width: 1 } },
    dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.ink, fontSize: 14, bold: true } },
    chartFill: C.bg,
    plotAreaFill: C.bg,
    plotAreaLine: { fill: "none", width: 0 },
    chartLine: { fill: "none", width: 0 },
  });
  applyPresentationChartFont(chart, { fontFamily: family });
  addText(slide, "Onde o espaço está", 826, 324, 320, 34, { fontSize: 21, bold: true, color: C.ink });
  addText(slide, "Raw", 826, 382, 92, 30, { fontSize: 20, bold: true, color: C.amber });
  addText(slide, "42,0 GiB", 944, 382, 180, 30, { fontSize: 20, color: C.ink, align: "right" });
  addRule(slide, 826, 422, 320, C.faint, 1);
  addText(slide, "Bronze", 826, 444, 110, 30, { fontSize: 20, bold: true, color: C.cyan });
  addText(slide, "0,48 GiB", 944, 444, 180, 30, { fontSize: 20, color: C.ink, align: "right" });
  addText(slide, "Silver", 826, 492, 110, 30, { fontSize: 20, bold: true, color: C.teal });
  addText(slide, "0,24 GiB", 944, 492, 180, 30, { fontSize: 20, color: C.ink, align: "right" });
  addText(slide, "Gold", 826, 540, 110, 30, { fontSize: 20, bold: true, color: C.green });
  addText(slide, "0,07 GiB", 944, 540, 180, 30, { fontSize: 20, color: C.ink, align: "right" });
  addText(slide, "Arquivos brutos concentram cerca de 98% do espaço.", 826, 590, 320, 48, { fontSize: 16, color: C.muted });
}

// 4. Folder map
{
  const slide = slideBase(
    "Mapa das pastas",
    "Inventário",
    4,
    "Fonte: árvore local de E:\\Projeto CS.",
  );
  addText(slide, "E:\\Projeto CS", 78, 164, 300, 40, { fontSize: 26, bold: true, color: C.cyan });
  addRule(slide, 91, 210, 3, 420, C.cyan);
  const rows = [
    ["src/", "lógica do pipeline", C.cyan],
    ["configs/", "decisões versionadas", C.teal],
    ["data/", "Raw, Bronze, Silver e Gold", C.amber],
    ["dags/", "orquestração Airflow", C.cyan],
    ["tests/", "contratos e regressões", C.green],
    ["docs/", "relatórios narrativos", C.ink],
    ["notebooks/", "visões de inspeção", C.ink],
    ["docker/ e .github/", "execução local e CI", C.muted],
  ];
  rows.forEach((r, i) => {
    const y = 224 + i * 49;
    addRule(slide, 91, y + 14, 44, C.faint, 2);
    addText(slide, r[0], 148, y, 260, 32, { fontSize: 21, bold: true, color: r[2] });
    addText(slide, r[1], 415, y + 1, 430, 32, { fontSize: 20, color: C.ink });
  });
  addText(slide, "Separação importante", 900, 182, 250, 32, { fontSize: 20, bold: true, color: C.amber });
  addText(slide, "Código e configuração entram no Git. Demos e camadas geradas ficam locais.", 900, 230, 286, 130, { fontSize: 24, color: C.ink, lineSpacing: 1.1 });
  addText(slide, "O guia detalhado explica os 210 arquivos humanos individualmente e agrupa os 1.498 artefatos repetitivos por família.", 900, 420, 286, 142, { fontSize: 20, color: C.muted, lineSpacing: 1.1 });
}

// 5. End-to-end pipeline
{
  const slide = slideBase(
    "Pipeline de dados ponta a ponta",
    "Arquitetura",
    5,
    "Fontes: E:\\Projeto CS\\README.md, configs/project.yaml e src/**/*.py.",
  );
  const nodes = [
    addNode(slide, "RAW", "seed, archives\ne demos", 60, 242, 188, 144, C.amber, { bodySize: 18 }),
    addNode(slide, "BRONZE", "manifests e\ntabelas por demo", 305, 242, 188, 144, C.cyan, { bodySize: 18 }),
    addNode(slide, "SILVER", "eventos\nconsolidados", 550, 242, 188, 144, C.teal, { bodySize: 18 }),
    addNode(slide, "GOLD", "features, estado,\nanálise e modelos", 795, 242, 188, 144, C.green, { bodySize: 18 }),
    addNode(slide, "CONSUMO", "docs, notebooks\ne futuros dashboards", 1040, 242, 188, 144, C.ink, { bodySize: 17 }),
  ];
  for (let i = 0; i < nodes.length - 1; i += 1) connect(slide, nodes[i], nodes[i + 1], { color: C.faint });
  addText(slide, "Rastreio", 80, 460, 150, 26, { fontSize: 17, bold: true, color: C.cyan });
  addRule(slide, 80, 497, 1090, C.cyan, 2);
  addText(slide, "hashes, IDs de demo, parse_id, series_id, round_id e fingerprints", 80, 514, 1090, 38, { fontSize: 20, color: C.ink, align: "center" });
  addText(slide, "Quality gates separam materialização de interpretação em cada fronteira crítica.", 80, 586, 1090, 34, { fontSize: 20, color: C.muted, align: "center" });
}

// 6. Evolution
{
  const slide = slideBase(
    "Evolução do pipeline",
    "Arquitetura",
    6,
    "Fonte: E:\\Projeto CS\\README.md, seções Official Pipeline Order e Current Status.",
  );
  addText(slide, "MVP Mirage", 72, 170, 200, 34, { fontSize: 23, bold: true, color: C.cyan });
  addRule(slide, 72, 218, 1120, C.faint, 3);
  const first = [
    ["1 a 3.6", "ingestão e parsing"],
    ["4 a 4.2", "features e estado"],
    ["5 a 5.2", "EDA e revisão"],
    ["6 a 6.3", "baseline e candidato"],
    ["7", "pacote final"],
  ];
  first.forEach((d, i) => {
    const x = 76 + i * 224;
    addText(slide, d[0], x, 238, 184, 34, { fontSize: 23, bold: true, color: C.cyan, align: "center" });
    addText(slide, d[1], x, 276, 184, 52, { fontSize: 16, color: C.ink, align: "center" });
  });
  addText(slide, "Expansão multi-mapa", 72, 377, 260, 34, { fontSize: 23, bold: true, color: C.amber });
  addRule(slide, 72, 425, 1120, C.faint, 3);
  const second = [
    ["8.0 a 8.3", "contrato e proteção Mirage"],
    ["8.4 a 8.7", "onboarding Inferno"],
    ["8.8 a 8.9.1", "Gold e qualidade"],
    ["8.10 a 8.10.1", "EDA e hardening"],
    ["8.11 a 8.12", "modelo e prontidão"],
  ];
  second.forEach((d, i) => {
    const x = 76 + i * 224;
    addText(slide, d[0], x, 445, 184, 34, { fontSize: 22, bold: true, color: C.amber, align: "center" });
    addText(slide, d[1], x, 484, 184, 58, { fontSize: 16, color: C.ink, align: "center" });
  });
  addText(slide, "O estágio 8 não substitui o MVP. Ele generaliza a arquitetura e preserva o resultado anterior por regressão formal.", 110, 594, 1060, 50, { fontSize: 20, color: C.muted, align: "center" });
}

// 7. Ingestion and parsing
{
  const slide = slideBase(
    "Ingestão e parsing",
    "Pipeline",
    7,
    "Fontes: src/ingestion, src/parsing, dags/cs2_demo_ingestion.py e README.md.",
  );
  const labels = [
    ["Entrada local", "seed ou arquivo"],
    ["Catálogo", "IDs e aliases"],
    ["Extração", "RAR, ZIP e DEM"],
    ["Probe", "mapa real"],
    ["Awpy", "tabelas e eventos"],
    ["Quality gate", "elegibilidade"],
  ];
  const nodes = labels.map((d, i) => addNode(slide, d[0], d[1], 48 + i * 204, 240, 165, 126, i === 0 ? C.amber : i === 5 ? C.green : C.cyan, { titleSize: 18, bodySize: 15 }));
  for (let i = 0; i < nodes.length - 1; i += 1) connect(slide, nodes[i], nodes[i + 1], { color: C.faint });
  addBullets(slide, [
    "O modo manual continua funcional sem internet.",
    "Falhas de uma demo não interrompem as demais.",
    "Forçar um mapa substitui somente o escopo solicitado.",
    "Demos curtas, partidas divididas e parsing suspeito não entram em features.",
  ], 92, 432, 1060, 178, { fontSize: 21, spaceAfterPoints: 10 });
}

// 8. Features and round state
{
  const slide = slideBase(
    "Feature engineering e estado do round",
    "Pipeline",
    8,
    "Fontes: src/features/*.py, configs/project.yaml e docs/feature_contract.md.",
  );
  addText(slide, "Evidência do parser", 72, 170, 260, 34, { fontSize: 22, bold: true, color: C.cyan });
  addText(slide, "ticks, rounds, kills, danos, utilidade e bomba", 72, 215, 300, 88, { fontSize: 21, color: C.ink, lineSpacing: 1.1 });
  addRule(slide, 392, 170, 2, 420, C.faint);
  addText(slide, "Janelas temporais", 430, 170, 260, 34, { fontSize: 22, bold: true, color: C.teal });
  addText(slide, "Intervalos e acumulados até 115 segundos", 430, 215, 300, 68, { fontSize: 21, color: C.ink, lineSpacing: 1.1 });
  addRule(slide, 430, 312, 314, C.teal, 4);
  const times = [0, 15, 35, 75, 115];
  times.forEach((t, i) => {
    const x = 430 + i * 78;
    addRule(slide, x, 300, 2, 28, C.teal);
    addText(slide, String(t), x - 17, 338, 40, 24, { fontSize: 15, color: C.muted, align: "center" });
  });
  addText(slide, "posição, dispersão, regiões, inventário, uso de utilidade e progressão", 430, 402, 300, 118, { fontSize: 20, color: C.muted, lineSpacing: 1.12 });
  addRule(slide, 768, 170, 2, 420, C.faint);
  addText(slide, "Estado canônico", 806, 170, 300, 34, { fontSize: 22, bold: true, color: C.amber });
  addBullets(slide, [
    "lado da Vitality",
    "dono do plant",
    "bombsite A ou B",
    "confiança da label",
    "separação T-side e CT-side",
  ], 806, 220, 360, 240, { fontSize: 20, spaceAfterPoints: 9 });
  addText(slide, "O modelo usa apenas rounds T-side com plant próprio e label A/B de alta confiança.", 806, 504, 350, 90, { fontSize: 20, bold: true, color: C.ink, lineSpacing: 1.1 });
}

// 9. Multi-map architecture illustration
{
  const slide = presentation.slides.add();
  slide.images.add({
    blob: multiMapBytes,
    contentType: "image/png",
    alt: "Dois mapas abstratos conectados a uma camada semântica compartilhada",
    fit: "cover",
    position: { left: 0, top: 0, width: 1280, height: 720 },
  });
  slide.shapes.add({ geometry: "rect", position: { left: 0, top: 0, width: 1280, height: 124 }, fill: C.bg, line: { fill: "none", width: 0 } });
  addText(slide, "ARQUITETURA", 64, 28, 300, 22, { fontSize: 14, bold: true, color: C.cyan });
  addText(slide, "Arquitetura multi-mapa", 64, 58, 920, 54, { fontSize: 36, bold: true, color: C.ink });
  slide.shapes.add({ geometry: "rect", position: { left: 0, top: 622, width: 1280, height: 98 }, fill: C.bg, line: { fill: "none", width: 0 } });
  addText(slide, "Cada mapa mantém sua geometria física. Conceitos como controle de meio, pressão A/B e estado do round usam uma camada semântica comum.", 78, 640, 1120, 50, { fontSize: 19, color: C.ink, align: "center", lineSpacing: 1.08 });
  addText(slide, "09", 1164, 34, 52, 20, { fontSize: 13, color: C.muted, align: "right" });
  slide.speakerNotes.textFrame.setText("Fontes: configs/maps/map_registry.yaml, configs/maps/mirage.yaml, configs/maps/inferno.yaml e src/maps/*.py. Ilustração gerada por IA para representar a separação entre geometria e semântica.");
}

// 10. Quality gates
{
  const slide = slideBase(
    "Gates de qualidade",
    "Confiabilidade",
    10,
    "Fontes: src/validation/*.py, docs/inferno_feature_quality.md e README.md.",
  );
  const center = addNode(slide, "FAIL CLOSED", "sem evidência\nnão há aprovação", 492, 270, 296, 142, C.red, { titleSize: 26, bodySize: 19, fill: "#211824" });
  const n1 = addNode(slide, "Parse", "demos completas\nelegíveis", 90, 175, 240, 122, C.cyan, { bodySize: 17 });
  const n2 = addNode(slide, "Mirage", "regressão e\ncompatibilidade", 90, 454, 240, 122, C.teal, { bodySize: 17 });
  const n3 = addNode(slide, "Gold", "upsert, chaves\ne preservação", 950, 175, 240, 122, C.green, { bodySize: 17 });
  const n4 = addNode(slide, "Features", "missingness, domínio,\nsemântica e labels", 950, 454, 240, 122, C.amber, { bodySize: 17 });
  connect(slide, n1, center, { fromSide: "right", toSide: "left", kind: "elbow", color: C.faint });
  connect(slide, n2, center, { fromSide: "right", toSide: "left", kind: "elbow", color: C.faint });
  connect(slide, center, n3, { fromSide: "right", toSide: "left", kind: "elbow", color: C.faint });
  connect(slide, center, n4, { fromSide: "right", toSide: "left", kind: "elbow", color: C.faint });
  addText(slide, "Qualidade do Inferno", 454, 472, 370, 30, { fontSize: 18, bold: true, color: C.ink, align: "center" });
  addText(slide, "0 falhas bloqueantes\n166 avisos visíveis", 454, 510, 370, 72, { fontSize: 23, color: C.muted, align: "center", lineSpacing: 1.1 });
}

// 11. Tactical analysis
{
  const slide = slideBase(
    "Análise tática",
    "Análise",
    11,
    "Fontes: src/analysis/*.py, docs/vitality_mirage_vs_inferno_eda.md e docs/vitality_multi_map_tactical_findings.md.",
  );
  const nodes = [
    addNode(slide, "EDA multi-mapa", "coortes e\nbootstrap por demo", 82, 235, 222, 146, C.cyan, { bodySize: 18 }),
    addNode(slide, "Candidatos", "comparações A/B,\nplant e mapas", 362, 235, 222, 146, C.teal, { bodySize: 18 }),
    addNode(slide, "Hardening", "exposição, LODO,\noponente e taxonomia", 642, 235, 222, 146, C.amber, { bodySize: 17 }),
    addNode(slide, "Evidência final", "ranking auditável\npara revisão humana", 922, 235, 222, 146, C.green, { bodySize: 17 }),
  ];
  for (let i = 0; i < nodes.length - 1; i += 1) connect(slide, nodes[i], nodes[i + 1], { color: C.faint });
  addMetric(slide, "276", "features comparáveis", 102, 468, 200, C.cyan, { valueSize: 38, labelSize: 15 });
  addMetric(slide, "2.760", "candidatos brutos", 372, 468, 200, C.teal, { valueSize: 38, labelSize: 15 });
  addMetric(slide, "349", "achados consolidados", 652, 468, 210, C.amber, { valueSize: 38, labelSize: 15 });
  addMetric(slide, "9", "achados endurecidos", 944, 468, 190, C.green, { valueSize: 38, labelSize: 15 });
  addText(slide, "Associações continuam descritivas até a revisão de demos.", 256, 610, 770, 30, { fontSize: 18, color: C.muted, align: "center" });
}

// 12. Modeling path
{
  const slide = slideBase(
    "Modelagem A/B",
    "Modelagem",
    12,
    "Fontes: src/modeling/*.py, configs/modeling/*.yaml e relatórios de modelagem.",
  );
  addText(slide, "Mirage", 82, 170, 480, 38, { fontSize: 27, bold: true, color: C.cyan });
  addRule(slide, 82, 220, 482, C.cyan, 3);
  addBullets(slide, [
    "18 avaliações de horizonte e modelo",
    "análise de 120 erros selecionados",
    "30 experimentos controlados",
    "um candidato exploratório congelado",
  ], 82, 254, 470, 214, { fontSize: 20, spaceAfterPoints: 11 });
  addText(slide, "Objetivo histórico", 82, 504, 210, 28, { fontSize: 17, bold: true, color: C.muted });
  addText(slide, "priorizar rounds para análise, sem alegar produção", 82, 540, 470, 58, { fontSize: 20, color: C.ink });
  addRule(slide, 632, 170, 2, 440, C.faint);
  addText(slide, "Inferno", 692, 170, 470, 38, { fontSize: 27, bold: true, color: C.amber });
  addRule(slide, 692, 220, 480, C.amber, 3);
  addBullets(slide, [
    "horizonte fixo de 35 segundos",
    "regressão logística L2 com C 0,1",
    "leave-one-series-out em cinco grupos",
    "permutação por grupo e bootstrap",
    "oito features aprovadas de onze candidatas",
  ], 692, 254, 475, 258, { fontSize: 20, spaceAfterPoints: 9 });
  addText(slide, "Regra comum", 692, 530, 190, 28, { fontSize: 17, bold: true, color: C.muted });
  addText(slide, "labels e janelas futuras ficam fora da matriz de predição", 692, 566, 475, 58, { fontSize: 20, color: C.ink });
}

// 13. Data snapshot
{
  const slide = slideBase(
    "Snapshot de dados",
    "Resultados",
    13,
    "Fonte: E:\\Projeto CS\\README.md, Current Status.",
  );
  const chart = slide.charts.add("bar", {
    position: { left: 72, top: 182, width: 770, height: 420 },
    categories: ["Rounds", "T-side", "T-side plantado"],
    series: [
      { name: "Mirage", values: [405, 180, 98], fill: C.cyan },
      { name: "Inferno", values: [122, 65, 40], fill: C.amber },
    ],
    barOptions: { direction: "column", grouping: "clustered", gapWidth: 55 },
    hasLegend: true,
    legend: { position: "bottom", overlay: false, textStyle: { fill: C.ink, fontSize: 14 } },
    xAxis: { textStyle: { fill: C.ink, fontSize: 15 }, line: { style: "solid", fill: C.faint, width: 1 }, majorGridlines: null },
    yAxis: { visible: true, min: 0, max: 450, majorUnit: 100, textStyle: { fill: C.muted, fontSize: 13 }, majorGridlines: { style: "solid", fill: "#23384C", width: 1 } },
    dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.ink, fontSize: 13, bold: true } },
    chartFill: C.bg,
    plotAreaFill: C.bg,
    plotAreaLine: { fill: "none", width: 0 },
    chartLine: { fill: "none", width: 0 },
  });
  applyPresentationChartFont(chart, { fontFamily: family });
  addMetric(slide, "527", "rounds consolidados", 902, 202, 250, C.ink, { valueSize: 42 });
  addMetric(slide, "138", "plants T-side A/B", 902, 318, 250, C.teal, { valueSize: 42 });
  addMetric(slide, "94 / 44", "classe A e classe B", 902, 434, 250, C.amber, { valueSize: 38 });
  addMetric(slide, "107", "T-side sem plant válido", 902, 550, 250, C.muted, { valueSize: 38 });
}

// 14. Inferno baseline result
{
  const slide = slideBase(
    "Resultado do baseline Inferno",
    "Resultados",
    14,
    "Fontes: docs/inferno_ab_exploratory_baseline.md e docs/modeling_integrity_refactor_regression.md.",
  );
  addText(slide, "NO SIGNAL", 72, 176, 440, 82, { fontSize: 56, bold: true, color: C.red });
  addText(slide, "A performance OOF não supera uma referência nula de forma útil.", 72, 266, 470, 82, { fontSize: 24, color: C.ink, lineSpacing: 1.08 });
  addMetric(slide, "0,472", "macro F1", 72, 410, 170, C.cyan, { valueSize: 38, labelSize: 15 });
  addMetric(slide, "0,472", "balanced accuracy", 258, 410, 220, C.teal, { valueSize: 38, labelSize: 15 });
  addMetric(slide, "-0,055", "MCC", 72, 532, 170, C.amber, { valueSize: 38, labelSize: 15 });
  addMetric(slide, "0,487", "ROC AUC", 258, 532, 220, C.amber, { valueSize: 38, labelSize: 15 });
  addText(slide, "Matriz de confusão OOF", 678, 170, 420, 34, { fontSize: 24, bold: true, color: C.ink });
  addText(slide, "Predito A", 804, 232, 150, 28, { fontSize: 17, color: C.muted, align: "center" });
  addText(slide, "Predito B", 980, 232, 150, 28, { fontSize: 17, color: C.muted, align: "center" });
  addText(slide, "Real A", 680, 306, 100, 30, { fontSize: 18, color: C.muted, align: "right" });
  addText(slide, "Real B", 680, 430, 100, 30, { fontSize: 18, color: C.muted, align: "right" });
  addNode(slide, "11", "A classificado\ncomo A", 804, 278, 150, 94, C.green, { titleSize: 28, bodySize: 14 });
  addNode(slide, "11", "A classificado\ncomo B", 980, 278, 150, 94, C.red, { titleSize: 28, bodySize: 14 });
  addNode(slide, "10", "B classificado\ncomo A", 804, 402, 150, 94, C.red, { titleSize: 28, bodySize: 14 });
  addNode(slide, "8", "B classificado\ncomo B", 980, 402, 150, 94, C.green, { titleSize: 28, bodySize: 14 });
  addText(slide, "Status correto: exploratório. Próxima ação: ampliar a amostra sem tuning.", 664, 560, 500, 66, { fontSize: 21, bold: true, color: C.amber, align: "center", lineSpacing: 1.08 });
}

// 15. Readiness
{
  const slide = slideBase(
    "Prontidão da amostra Inferno",
    "Resultados",
    15,
    "Fontes: configs/modeling/inferno_sample_expansion.yaml e docs/inferno_sample_expansion.md.",
  );
  const chart = slide.charts.add("bar", {
    position: { left: 64, top: 174, width: 730, height: 438 },
    categories: ["Demos", "Séries", "Rounds plantados", "Menor classe", "Oponentes", "Grupos LOGO"],
    series: [{ name: "Percentual da meta", values: [50, 62.5, 50, 60, 80, 62.5], fill: C.cyan, valuesFormatCode: '0"%"' }],
    barOptions: { direction: "bar", grouping: "clustered", gapWidth: 48 },
    hasLegend: false,
    xAxis: { visible: true, min: 0, max: 100, majorUnit: 25, numberFormatCode: '0"%"', textStyle: { fill: C.muted, fontSize: 12 }, majorGridlines: { style: "solid", fill: "#23384C", width: 1 } },
    yAxis: { textStyle: { fill: C.ink, fontSize: 14 }, line: { style: "solid", fill: C.faint, width: 1 } },
    dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.ink, fontSize: 12, bold: true } },
    chartFill: C.bg,
    plotAreaFill: C.bg,
    plotAreaLine: { fill: "none", width: 0 },
    chartLine: { fill: "none", width: 0 },
  });
  applyPresentationChartFont(chart, { fontFamily: family });
  addText(slide, "Atual / meta", 868, 182, 280, 32, { fontSize: 22, bold: true, color: C.amber });
  const targets = ["5 / 8 grupos LOGO", "4 / 5 oponentes", "18 / 30 na menor classe", "40 / 80 rounds", "5 / 8 séries", "5 / 10 demos"];
  targets.forEach((t, i) => addText(slide, t, 868, 236 + i * 54, 300, 34, { fontSize: 20, color: C.ink }));
  addRule(slide, 868, 566, 300, C.faint, 1);
  addText(slide, "expanded_but_limited", 868, 584, 300, 28, { fontSize: 18, bold: true, color: C.red });
  addText(slide, "modeling_sample_ready = false", 868, 620, 300, 26, { fontSize: 16, color: C.muted });
}

// 16. Airflow
{
  const slide = slideBase(
    "Orquestração Airflow",
    "Operação",
    16,
    "Fontes: dags/*.py, compose.airflow.yml e docs/airflow.md.",
  );
  const lanes = [
    ["cs2_demo_ingestion", "catálogo, scan, probe, parser e quality", C.cyan, "cs2://silver/parse-quality"],
    ["cs2_gold_materialization", "features, estado, datasets e Gold gate", C.green, "cs2://gold/scoped-map-features"],
    ["cs2_inferno_analysis_modeling", "qualidade, EDA, modelo e readiness", C.amber, "cs2://gold/inferno-analysis-modeling"],
  ];
  lanes.forEach((d, i) => {
    const y = 178 + i * 148;
    addText(slide, d[0], 74, y, 360, 36, { fontSize: 22, bold: true, color: d[2] });
    addText(slide, d[1], 74, y + 44, 430, 54, { fontSize: 18, color: C.ink });
    addRule(slide, 526, y + 32, 92, d[2], 3);
    addText(slide, d[3], 650, y + 8, 480, 38, { fontSize: 20, bold: true, color: d[2] });
    addText(slide, "Asset de saída observável", 650, y + 52, 360, 30, { fontSize: 16, color: C.muted });
  });
  addText(slide, "Execução manual, LocalExecutor, PostgreSQL e no máximo uma run ativa por DAG.", 140, 617, 1000, 34, { fontSize: 20, color: C.muted, align: "center" });
}

// 17. File tour 1
{
  const slide = slideBase(
    "Tour de arquivos: base do pipeline",
    "Arquivos",
    17,
    "Fonte: inspeção de cada módulo em E:\\Projeto CS\\src. O guia complementar contém uma linha por arquivo.",
  );
  addText(slide, "Configuração e ingestão", 72, 168, 500, 34, { fontSize: 22, bold: true, color: C.cyan });
  addBullets(slide, [
    "config/schemas.py valida todo o YAML",
    "ingestion/ constrói catálogo, baixa ou registra archives",
    "scan_local_archives.py trata splits e demos diretas",
  ], 72, 215, 500, 160, { fontSize: 18, spaceAfterPoints: 8 });
  addText(slide, "Parsing", 72, 396, 500, 34, { fontSize: 22, bold: true, color: C.teal });
  addBullets(slide, [
    "awpy_parser.py isola o backend",
    "parse_demos.py controla escopo e falhas",
    "parsed_tables.py mantém Bronze e Silver",
    "parse_quality.py publica elegibilidade",
  ], 72, 443, 500, 170, { fontSize: 18, spaceAfterPoints: 7 });
  addRule(slide, 624, 164, 2, 476, C.faint);
  addText(slide, "Features", 674, 168, 500, 34, { fontSize: 22, bold: true, color: C.amber });
  addBullets(slide, [
    "build_round_features.py integra as famílias",
    "position, utility, bomb, death e progression são módulos separados",
    "round_state.py resolve a label sem proxy",
    "side_datasets.py publica T e CT",
    "run_map_pipeline.py encapsula o fluxo por mapa",
  ], 674, 215, 500, 208, { fontSize: 18, spaceAfterPoints: 7 });
  addText(slide, "Mapas e armazenamento", 674, 464, 500, 34, { fontSize: 22, bold: true, color: C.green });
  addBullets(slide, [
    "maps/ separa identidade, geometria e semântica",
    "storage/scoped_gold.py garante upsert por escopo",
    "utils/ centraliza I/O, logs, reports e notebooks",
  ], 674, 511, 500, 126, { fontSize: 18, spaceAfterPoints: 7 });
}

// 18. File tour 2
{
  const slide = slideBase(
    "Tour de arquivos: evidência e controle",
    "Arquivos",
    18,
    "Fonte: inspeção de cada módulo em E:\\Projeto CS\\src. O guia complementar contém uma linha por arquivo.",
  );
  addText(slide, "Análise", 72, 168, 500, 34, { fontSize: 22, bold: true, color: C.cyan });
  addBullets(slide, [
    "t_side_eda.py e t_side_findings.py cobrem o MVP Mirage",
    "t_side_manual_review.py liga achados a rounds",
    "multi_map_tactical_eda.py compara mapas",
    "tactical_finding_hardening.py consolida evidência",
  ], 72, 215, 500, 180, { fontSize: 18, spaceAfterPoints: 7 });
  addText(slide, "Modelagem", 72, 420, 500, 34, { fontSize: 22, bold: true, color: C.amber });
  addBullets(slide, [
    "t_side_ab_* mantém a trilha Mirage",
    "build_map_ab_dataset.py aprova features fail-closed",
    "inferno_ab_exploratory_baseline.py executa LOGO",
    "inferno_sample_expansion.py mede readiness",
  ], 72, 467, 500, 166, { fontSize: 18, spaceAfterPoints: 7 });
  addRule(slide, 624, 164, 2, 476, C.faint);
  addText(slide, "Validação", 674, 168, 500, 34, { fontSize: 22, bold: true, color: C.green });
  addBullets(slide, [
    "mirage_regression_gate.py protege o legado",
    "multi_map_parse_gate.py protege Silver",
    "multi_map_gold_gate.py protege Gold",
    "map_feature_quality_gate.py avalia 477 features",
    "feature_materialization_repair.py corrige sem relaxar limites",
  ], 674, 215, 500, 218, { fontSize: 18, spaceAfterPoints: 7 });
  addText(slide, "Reporting e operação", 674, 474, 500, 34, { fontSize: 22, bold: true, color: C.teal });
  addBullets(slide, [
    "build_final_mvp_report.py gera o pacote inicial",
    "dags/ apenas encadeia CLIs existentes",
    "scripts/check_airflow_dags.py valida imports na CI",
  ], 674, 521, 500, 116, { fontSize: 18, spaceAfterPoints: 7 });
}

// 19. Docs, notebooks, tests
{
  const slide = slideBase(
    "Documentação, notebooks e testes",
    "Arquivos",
    19,
    "Fontes: docs/notebook_inventory.md, pyproject.toml e execução de pytest nesta revisão.",
  );
  addMetric(slide, "28", "documentos Markdown", 72, 176, 260, C.cyan, { valueSize: 50 });
  addText(slide, "Relatórios narrativos por estágio, incluindo Airflow, mapas, qualidade, achados e modelos.", 72, 296, 300, 130, { fontSize: 20, color: C.ink, lineSpacing: 1.08 });
  addMetric(slide, "28", "notebooks sem outputs", 470, 176, 280, C.amber, { valueSize: 50 });
  addText(slide, "Visões de inspeção. Os atuais são 03, 04, 05 e 25 a 29. O número 28 não existe.", 470, 296, 310, 130, { fontSize: 20, color: C.ink, lineSpacing: 1.08 });
  addMetric(slide, "42", "arquivos de teste", 870, 176, 280, C.green, { valueSize: 50 });
  addText(slide, "290 testes aprovados. Cobertura forte de idempotência, leakage, regressão, gates e casos de erro.", 870, 296, 310, 130, { fontSize: 20, color: C.ink, lineSpacing: 1.08 });
  addRule(slide, 72, 488, 1080, C.faint, 1);
  addText(slide, "CI", 72, 524, 110, 30, { fontSize: 20, bold: true, color: C.cyan });
  addText(slide, "Python 3.11 e 3.12, Ruff, Pytest, build da imagem Airflow e import das DAGs", 170, 524, 980, 34, { fontSize: 20, color: C.ink });
  addText(slide, "Resultado desta revisão: lint aprovado, 290 testes aprovados, um aviso não bloqueante.", 72, 586, 1080, 34, { fontSize: 19, color: C.muted });
}

// 20. Rebuild safely
{
  const slide = slideBase(
    "Como reconstruir com segurança",
    "Operação",
    20,
    "Fontes: README.md, Official Pipeline Order, e docs/airflow.md.",
  );
  const p1 = addNode(slide, "1. Ingestão", "catálogo\nscan e extração\nprobe\nparsing\nparse quality", 80, 186, 280, 266, C.cyan, { bodySize: 20, titleSize: 24 });
  const p2 = addNode(slide, "2. Gold", "round features\nround state\nside datasets\nGold gate\nfeature quality", 500, 186, 280, 266, C.green, { bodySize: 20, titleSize: 24 });
  const p3 = addNode(slide, "3. Evidência", "reparo\nEDA multi-mapa\nhardening\ndataset A/B\nbaseline e readiness", 920, 186, 280, 266, C.amber, { bodySize: 20, titleSize: 24 });
  connect(slide, p1, p2, { color: C.faint });
  connect(slide, p2, p3, { color: C.faint });
  addText(slide, "Regras de invalidação", 88, 512, 280, 30, { fontSize: 20, bold: true, color: C.red });
  addText(slide, "Reprocessar parsing exige refazer quality e tudo a jusante. Reprocessar features exige refazer estado, datasets por lado e análises.", 88, 554, 1090, 70, { fontSize: 20, color: C.ink, lineSpacing: 1.08 });
}

// 21. Risks and next step
{
  const slide = slideBase(
    "Limitações e próximo passo",
    "Conclusão",
    21,
    "Fontes: README.md, docs/inferno_sample_expansion.md e docs/airflow.md.",
  );
  addText(slide, "Limitações atuais", 72, 170, 420, 34, { fontSize: 24, bold: true, color: C.red });
  addBullets(slide, [
    "quase 42 GiB em archives e demos com retenção manual",
    "armazenamento Gold local impede concorrência segura",
    "cinco grupos no Inferno ainda não sustentam inferência preditiva",
    "dashboard e plataforma de dados ainda não existem",
  ], 72, 220, 510, 236, { fontSize: 20, spaceAfterPoints: 10 });
  addRule(slide, 626, 168, 2, 460, C.faint);
  addText(slide, "Próxima decisão coerente", 680, 170, 470, 34, { fontSize: 24, bold: true, color: C.green });
  addText(slide, "Ampliar a amostra do Inferno antes de ajustar o modelo.", 680, 226, 480, 86, { fontSize: 29, bold: true, color: C.ink, lineSpacing: 1.06 });
  addBullets(slide, [
    "chegar a 10 demos e 8 séries",
    "atingir 80 rounds plantados",
    "obter 30 exemplos na menor classe",
    "cobrir pelo menos 5 adversários",
  ], 680, 352, 480, 190, { fontSize: 20, spaceAfterPoints: 9 });
  addText(slide, "Manter o baseline e os limites congelados durante a expansão.", 680, 574, 470, 50, { fontSize: 19, color: C.amber });
}

// 22. Deliverables
{
  const slide = slideBase(
    "Materiais da revisão",
    "Conclusão",
    22,
    "Materiais criados nesta revisão. Os arquivos estão em C:\\Users\\celso\\OneDrive\\Documentos\\ChatGPT\\Projeto CS\\entregaveis.",
    "Entregáveis em C:\\Users\\celso\\OneDrive\\Documentos\\ChatGPT\\Projeto CS\\entregaveis",
  );
  addText(slide, "A apresentação resume a arquitetura. O guia detalhado permite navegar arquivo por arquivo.", 90, 168, 1080, 68, { fontSize: 27, color: C.ink, align: "center", lineSpacing: 1.08 });
  addNode(slide, "Apresentação", "revisão visual\ndo pipeline", 90, 300, 240, 150, C.cyan, { bodySize: 19 });
  addNode(slide, "Guia Markdown", "210 arquivos humanos\nexplicados individualmente", 380, 300, 240, 150, C.green, { bodySize: 17 });
  addNode(slide, "Inventário CSV", "1.708 caminhos\ncom categoria e tamanho", 670, 300, 240, 150, C.amber, { bodySize: 17 });
  addNode(slide, "Assets visuais", "capa e arquitetura\nmulti-mapa", 960, 300, 240, 150, C.teal, { bodySize: 18 });
  addText(slide, "Ponto de partida recomendado: README.md, depois esta apresentação e por fim o guia completo.", 160, 548, 960, 58, { fontSize: 22, color: C.muted, align: "center", lineSpacing: 1.08 });
}

await fs.mkdir(stagingDir, { recursive: true });
await fs.mkdir(path.dirname(FINAL_PPTX), { recursive: true });
const candidatePath = path.join(stagingDir, "candidate-projeto-cs-v2.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);

const requirements = {
  explicitTotalSlideCount: 22,
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [3, 13, 15],
  requiredEmbeddedWorkbookChartOwnerSlides: [],
  materializeLiteralChartWorkbooks: true,
};

const result = await finalizePresentation({
  ...requirements,
  workspaceDir,
  candidatePath,
  finalPath: FINAL_PPTX,
  pythonExecutable: RUNTIME_PYTHON,
  integrityValidatorPath: path.join(SKILL_DIR, "container_tools", "inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(SKILL_DIR, "container_tools", "inspect_presentation_layout_geometry.py"),
  layoutArgs: [
    "--expected-slide-size-emu", "12192000,6858000",
    "--validate-bullet-geometry",
    "--validate-heading-fit",
  ],
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [3, 13, 15],
  materializeLiteralChartWorkbooks: true,
  fontPolicy: { basis: "design", families: [family] },
  verifyArtifactToolImport: true,
  receiptPath: path.join(stagingDir, `${path.basename(FINAL_PPTX)}.validation.json`),
});

console.log(JSON.stringify({ family, finalPath: FINAL_PPTX, result }, null, 2));
