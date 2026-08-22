from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PAPERS_DIR = REPO_ROOT / "papers"
DATA_PATH = REPO_ROOT / "research_map.json"
PAGE_PATH = REPO_ROOT / "research-map.html"
SUPPLEMENTS_PATH = REPO_ROOT / "research_supplements.json"

CATEGORIES = {
    "D": {
        "slug": "dp-quality-diversity",
        "label": "DP、遗传规划与质量多样性搜索",
        "short": "DP / QD 搜索",
        "description": "Route1-DP 的 archive、约束、emitter、credit 与 parent supply 算法底座。",
    },
    "N": {
        "slug": "neural-surrogate",
        "label": "神经网络、表示学习与多保真代理",
        "short": "神经与代理模型",
        "description": "面向市场状态、图关系、持续适应和 Full FSIM 前的轻量排序。",
    },
    "R": {
        "slug": "adaptive-search",
        "label": "强化学习、Bandit 与自适应搜索控制",
        "short": "自适应搜索",
        "description": "理解 credit assignment、上下文路由和 operator / emitter 动态分配。",
    },
    "Q": {
        "slug": "quant-llm",
        "label": "Quant Research、LLM 因子挖掘与研究智能体",
        "short": "Quant + LLM",
        "description": "连接研究 Agent、公式实现、经验记忆、多智能体协作与 Alpha 评估。",
    },
    "A": {
        "slug": "auto-research",
        "label": "AI / Auto Research 与多智能体科学发现",
        "short": "Auto Research",
        "description": "围绕失败驱动迭代、可证伪实验、技能记忆和科学发现工作流。",
    },
    "E": {
        "slug": "research-validation",
        "label": "回测过拟合、数据窥探与多重检验",
        "short": "统计防线",
        "description": "从版本级实验账本、PBO、DSR 到 Reality Check 和多重检验。",
    },
    "I": {
        "slug": "industry-reports",
        "label": "国内券商研报与工程化行业参考",
        "short": "券商工程参考",
        "description": "贴近 A 股数据与实现细节的遗传规划、神经网络和强化学习案例。",
    },
    "G": {
        "slug": "gp-ast-emitter",
        "label": "GP、AST 程序进化与 Emitter（补充专题）",
        "short": "GP / AST / Emitter",
        "description": "连接量化 Alpha 自动发现、Grammar / Semantic GP、AST variation 与离散 QD emitter。",
    },
}

WEEKS = [
    {
        "week": "第 1 周",
        "theme": "系统底座",
        "codes": ["D01", "D03", "D04", "D06", "D10", "Q01", "E01", "E02"],
        "goal": "读透 archive、约束、评价与多重检验。",
    },
    {
        "week": "第 2 周",
        "theme": "第二代表达与效率",
        "codes": ["Q05", "Q06", "Q07", "D08", "D09", "N11", "N12", "N13"],
        "goal": "围绕 Idea → Formula、经验记忆和 Full FSIM 排序。",
    },
    {
        "week": "第 3 周",
        "theme": "神经与自适应搜索",
        "codes": ["N01", "N02", "N07", "N08", "R01", "R02", "R04", "R06", "R07"],
        "goal": "建立 neural / context / bandit 与 DP 的边界。",
    },
    {
        "week": "第 4 周",
        "theme": "Auto Research",
        "codes": ["Q04", "Q08", "Q10", "A02", "A03", "A05", "A06", "A07", "A10", "A12"],
        "goal": "从失败实验回到新假设、最小判别实验与 winner carry-forward。",
    },
    {
        "week": "专题补充",
        "theme": "Formula Evolution / GP Emitter",
        "codes": ["G01", "G02", "G03", "G04", "G05", "G06", "G07", "G08"],
        "goal": "从 Idea → Formula、Grammar / Semantic GP 到离散 emitter，补足 AST 搜索链路。",
    },
]

EXISTING_FILES = {
    "I04": "reports/光大证券/20190804-光大证券-多因子系列报告之二十四：短周期因子的挖掘与组合构建.pdf",
}


def safe_filename(code: str, title: str) -> str:
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")
    title = re.sub(r"\s+", " ", title)
    return f"{code} - {title[:150]}.pdf"


def build_data(results_path: Path, staging_dir: Path) -> list[dict[str, object]]:
    entries = json.loads(results_path.read_text(encoding="utf-8"))
    output = []
    for position, entry in enumerate(entries, start=1):
        prefix = entry["code"][0]
        category = CATEGORIES[prefix]
        item = {
            "position": position,
            "code": entry["code"],
            "priority": entry["priority"],
            "title": entry["title"],
            "citation": entry["citation"],
            "method": entry["method"],
            "system_mapping": entry["system_mapping"],
            "reading_focus": entry["reading_focus"],
            "category": category["label"],
            "category_short": category["short"],
            "category_slug": category["slug"],
            "source_url": entry["url"],
            "availability": "source-only",
            "web_path": "",
            "size_bytes": 0,
        }

        existing_path = EXISTING_FILES.get(entry["code"])
        if existing_path:
            existing_file = REPO_ROOT / existing_path
            if not existing_file.exists():
                raise FileNotFoundError(existing_file)
            item.update({
                "availability": "existing-report",
                "web_path": existing_path,
                "size_bytes": existing_file.stat().st_size,
            })
        elif entry["status"] == "downloaded":
            source = staging_dir / str(entry["local_file"])
            if not source.exists() or source.read_bytes()[:5] != b"%PDF-":
                raise RuntimeError(f"invalid staged PDF for {entry['code']}: {source}")
            category_dir = PAPERS_DIR / category["slug"]
            category_dir.mkdir(parents=True, exist_ok=True)
            destination = category_dir / safe_filename(entry["code"], entry["title"])
            shutil.copy2(source, destination)
            item.update({
                "availability": "local-pdf",
                "web_path": destination.relative_to(REPO_ROOT).as_posix(),
                "size_bytes": destination.stat().st_size,
            })
        output.append(item)
    existing_titles = {normalize_title(str(item["title"])) for item in output}
    existing_urls = {str(item["source_url"]).lower().rstrip("/") for item in output}
    supplements = json.loads(SUPPLEMENTS_PATH.read_text(encoding="utf-8"))
    for entry in supplements:
        title_key = normalize_title(entry["title"])
        url_key = entry["url"].lower().rstrip("/")
        if title_key in existing_titles or url_key in existing_urls:
            raise RuntimeError(f"duplicate supplement: {entry['code']} {entry['title']}")
        category = CATEGORIES[entry["code"][0]]
        web_path = entry.get("web_path", "")
        availability = "source-only"
        size_bytes = 0
        if web_path:
            local_file = REPO_ROOT / web_path
            if not local_file.exists() or local_file.read_bytes()[:5] != b"%PDF-":
                raise RuntimeError(f"missing or invalid supplement PDF: {local_file}")
            availability = "local-pdf"
            size_bytes = local_file.stat().st_size
        output.append({
            "position": len(output) + 1,
            "code": entry["code"],
            "priority": entry["priority"],
            "title": entry["title"],
            "citation": entry["citation"],
            "method": entry["method"],
            "system_mapping": entry["system_mapping"],
            "reading_focus": entry["reading_focus"],
            "category": category["label"],
            "category_short": category["short"],
            "category_slug": category["slug"],
            "source_url": entry["url"],
            "availability": availability,
            "web_path": web_path,
            "size_bytes": size_bytes,
        })
        existing_titles.add(title_key)
        existing_urls.add(url_key)
    return output


def normalize_title(title: str) -> str:
    return "".join(character for character in title.casefold() if character.isalnum())


def write_data(entries: list[dict[str, object]]) -> None:
    payload = {
        "title": "混合架构量化研究系统：论文与研报研读地图",
        "version": "1.1",
        "date": "2026-08-22",
        "categories": list(CATEGORIES.values()),
        "weeks": WEEKS,
        "entries": entries,
    }
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_page() -> None:
    PAGE_PATH.write_text(RESEARCH_MAP_HTML, encoding="utf-8")


def copy_map_assets(docx_path: Path, pdf_path: Path, cover_path: Path) -> None:
    reading_dir = REPO_ROOT / "reading-map"
    assets_dir = REPO_ROOT / "assets"
    reading_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(docx_path, reading_dir / "混合架构量化研究系统_论文与研报研读地图_20260820.docx")
    shutil.copy2(pdf_path, reading_dir / "混合架构量化研究系统_论文与研报研读地图_20260820.pdf")
    shutil.copy2(cover_path, assets_dir / "research-map-cover.png")


def validate(entries: list[dict[str, object]]) -> None:
    expected = 74 + len(json.loads(SUPPLEMENTS_PATH.read_text(encoding="utf-8")))
    if len(entries) != expected:
        raise RuntimeError(f"expected {expected} entries, got {len(entries)}")
    local = [item for item in entries if item["availability"] != "source-only"]
    for item in local:
        path = REPO_ROOT / str(item["web_path"])
        if not path.exists() or path.read_bytes()[:5] != b"%PDF-":
            raise RuntimeError(f"missing or invalid local PDF: {item['code']} {path}")
        if path.stat().st_size >= 100 * 1024 * 1024:
            raise RuntimeError(f"GitHub blocks files >=100MB: {path}")


def main() -> int:
    if len(sys.argv) != 7:
        raise SystemExit(
            "usage: build_research_map.py RESULTS_JSON STAGING_DIR DOCX PDF COVER_PNG --build"
        )
    results_path = Path(sys.argv[1])
    staging_dir = Path(sys.argv[2])
    docx_path = Path(sys.argv[3])
    pdf_path = Path(sys.argv[4])
    cover_path = Path(sys.argv[5])
    if sys.argv[6] != "--build":
        raise SystemExit("final argument must be --build")
    entries = build_data(results_path, staging_dir)
    write_data(entries)
    write_page()
    copy_map_assets(docx_path, pdf_path, cover_path)
    validate(entries)
    local_count = sum(item["availability"] != "source-only" for item in entries)
    print(f"Built research map: {len(entries)} entries, {local_count} local PDFs.")
    return 0


RESEARCH_MAP_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>论文与研报研读地图 · 量化研究知识库</title>
  <style>
    :root { color-scheme: light; --ink: #17212b; --muted: #5f6f7f; --line: #d8e0e7; --navy: #163b5c; --blue: #1f6fae; --green: #24775b; --gold: #9a6b00; --red: #a43c35; --paper: #fff; --wash: #f4f7f9; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif; color: var(--ink); background: var(--wash); }
    a { color: var(--blue); text-decoration: none; }
    a:hover { text-decoration: underline; }
    header { background: var(--navy); color: #fff; }
    .header-inner, main { width: min(1180px, calc(100% - 40px)); margin: 0 auto; }
    .header-inner { padding: 22px 0 26px; }
    .nav { display: flex; flex-wrap: wrap; gap: 18px; align-items: center; margin-bottom: 26px; font-size: 14px; }
    .nav a { color: #dce9f3; }
    .nav strong { margin-right: auto; color: #fff; }
    h1 { margin: 0 0 10px; font-size: clamp(30px, 5vw, 48px); line-height: 1.15; letter-spacing: 0; }
    header p { max-width: 820px; margin: 0; color: #dce9f3; line-height: 1.7; }
    main { padding: 28px 0 56px; }
    .intro { display: grid; grid-template-columns: minmax(0, 1fr) 270px; gap: 30px; align-items: start; padding: 0 0 28px; border-bottom: 1px solid var(--line); }
    .intro h2, .section-title { margin: 0 0 12px; color: var(--navy); font-size: 24px; letter-spacing: 0; }
    .intro p { line-height: 1.75; color: #3f4e5c; }
    .cover { display: block; width: 100%; border: 1px solid var(--line); background: #fff; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }
    .button { display: inline-flex; align-items: center; min-height: 38px; border: 1px solid #9fb1c0; border-radius: 6px; padding: 8px 12px; background: #fff; color: var(--navy); font-weight: 650; }
    .button.primary { background: var(--green); border-color: var(--green); color: #fff; }
    .stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 24px 0 34px; }
    .stat { border-top: 3px solid var(--blue); background: #fff; padding: 14px; }
    .stat:nth-child(2) { border-color: var(--green); }
    .stat:nth-child(3) { border-color: var(--gold); }
    .stat:nth-child(4) { border-color: var(--red); }
    .stat b { display: block; font-size: 26px; color: var(--navy); }
    .stat span { color: var(--muted); font-size: 13px; }
    .guide { margin: 0 0 34px; }
    .week-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); border-top: 1px solid var(--line); border-left: 1px solid var(--line); background: #fff; }
    .week { padding: 16px; border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); }
    .week b { color: var(--green); }
    .week h3 { margin: 7px 0; font-size: 17px; color: var(--navy); }
    .week p { margin: 7px 0 0; color: var(--muted); font-size: 13px; line-height: 1.55; }
    .codes { color: #34495a; font-size: 12px; overflow-wrap: anywhere; }
    .library { border-top: 1px solid var(--line); padding-top: 28px; }
    .toolbar { position: sticky; top: 0; z-index: 5; display: grid; grid-template-columns: minmax(230px, 1fr) 240px 140px 160px; gap: 10px; padding: 12px; margin: 14px 0; background: rgba(244, 247, 249, .96); border: 1px solid var(--line); }
    input, select { width: 100%; min-height: 40px; border: 1px solid #aebcc8; border-radius: 6px; padding: 8px 10px; background: #fff; color: var(--ink); font: inherit; }
    .summary { margin: 10px 0 16px; color: var(--muted); font-size: 14px; }
    .category-heading { display: flex; align-items: baseline; gap: 10px; margin: 28px 0 10px; padding-bottom: 8px; border-bottom: 2px solid #bfd0dd; }
    .category-heading h3 { margin: 0; color: var(--navy); font-size: 20px; }
    .category-heading span { color: var(--muted); font-size: 13px; }
    .entry { display: grid; grid-template-columns: 74px minmax(0, 1fr) 150px; gap: 14px; padding: 18px 0; border-bottom: 1px solid var(--line); }
    .entry-code { font-weight: 750; color: var(--navy); }
    .priority { display: inline-block; margin-top: 7px; padding: 2px 7px; border-radius: 4px; font-size: 12px; font-weight: 700; }
    .priority-A { background: #dff2e9; color: #176245; }
    .priority-B { background: #e6f0f8; color: #185c8c; }
    .priority-C { background: #f6edd3; color: #815b00; }
    .entry h4 { margin: 0 0 6px; color: #1a5078; font-size: 17px; line-height: 1.45; overflow-wrap: anywhere; letter-spacing: 0; }
    .citation { margin: 0 0 10px; color: var(--muted); font-size: 13px; }
    .detail { margin: 5px 0; color: #334454; font-size: 14px; line-height: 1.6; }
    .detail b { color: var(--navy); }
    .entry-actions { display: flex; flex-direction: column; gap: 8px; align-items: stretch; }
    .entry-actions .button { justify-content: center; text-align: center; }
    .read-toggle { display: flex; align-items: center; gap: 7px; padding: 7px 8px; color: var(--muted); font-size: 13px; cursor: pointer; }
    .read-toggle input { width: 16px; min-height: 16px; accent-color: var(--green); }
    .availability { font-size: 12px; color: var(--muted); text-align: center; }
    .entry.is-read { opacity: .66; }
    .empty { padding: 28px 0; color: var(--muted); }
    footer { padding: 24px 0; border-top: 1px solid var(--line); color: var(--muted); font-size: 13px; line-height: 1.6; }
    @media (max-width: 900px) {
      .intro { grid-template-columns: 1fr 190px; }
      .stats, .week-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .toolbar { position: static; grid-template-columns: 1fr 1fr; }
    }
    @media (max-width: 640px) {
      .header-inner, main { width: min(100% - 28px, 1180px); }
      .intro { grid-template-columns: 1fr; }
      .cover { width: min(240px, 100%); }
      .stats, .week-grid, .toolbar { grid-template-columns: 1fr; }
      .entry { grid-template-columns: 58px minmax(0, 1fr); }
      .entry-actions { grid-column: 1 / -1; flex-direction: row; flex-wrap: wrap; }
      .entry-actions .button { flex: 1 1 130px; }
      .read-toggle { flex: 1 1 100%; }
    }
  </style>
</head>
<body>
<header>
  <div class="header-inner">
    <nav class="nav"><strong>量化研究知识库</strong><a href="index.html">首页</a><a href="all-reports.html">历史研报库</a><a href="research_map.json">数据索引</a></nav>
    <h1>论文与研报研读地图</h1>
    <p>围绕混合架构量化研究系统，把论文与券商研报组织成可执行的任务导览：从系统边界、搜索、表示和控制，延伸到 GP / AST 程序进化、Emitter、研究智能体与统计防线。</p>
  </div>
</header>
<main>
  <section class="intro">
    <div>
      <h2>混合架构量化研究系统</h2>
      <p>本库保留原文中的第一代 / 第二代架构映射、A/B/C 阅读优先级、四周主线，以及逐篇“方法、系统映射、研读重点”。新增 GP / AST / Emitter 专题已先与原库去重；本地 PDF 可直接复制链接给网页版 GPT，暂未获得公开全文的条目提供正式来源页。</p>
      <div class="actions">
        <a class="button primary" href="reading-map/混合架构量化研究系统_论文与研报研读地图_20260820.pdf" target="_blank" rel="noopener">打开研读地图 PDF</a>
        <a class="button" href="reading-map/混合架构量化研究系统_论文与研报研读地图_20260820.docx">下载 Word 原稿</a>
        <a class="button" href="reading-map/Quant_Alpha_Search_GP_Emitter_论文补充清单_修正版.pdf" target="_blank" rel="noopener">打开 GP / Emitter 补充清单</a>
      </div>
    </div>
    <a href="reading-map/混合架构量化研究系统_论文与研报研读地图_20260820.pdf" target="_blank" rel="noopener"><img class="cover" src="assets/research-map-cover.png" alt="论文与研报研读地图封面"></a>
  </section>

  <section class="stats" aria-label="收录统计">
    <div class="stat"><b id="stat-total">-</b><span>论文与研报条目</span></div>
    <div class="stat"><b id="stat-local">-</b><span>站内可读 PDF</span></div>
    <div class="stat"><b id="stat-source">-</b><span>仅原始来源页</span></div>
    <div class="stat"><b id="stat-categories">-</b><span>任务导览模块</span></div>
  </section>

  <section class="guide">
    <h2 class="section-title">四周主线与专题补充</h2>
    <div class="week-grid" id="weeks"></div>
  </section>

  <section class="library">
    <h2 class="section-title">论文与研报条目</h2>
    <div class="toolbar">
      <input id="search" type="search" placeholder="搜索标题、编号、方法或系统映射">
      <select id="category"><option value="">全部任务类型</option></select>
      <select id="priority"><option value="">全部优先级</option><option value="A">A · 近期必读</option><option value="B">B · 子系统深入</option><option value="C">C · 前沿融合</option></select>
      <select id="availability"><option value="">全部访问状态</option><option value="local">站内 PDF</option><option value="source-only">原始来源页</option></select>
    </div>
    <p class="summary" id="summary">正在加载索引…</p>
    <div id="entries"></div>
  </section>

  <footer>阅读状态只保存在当前浏览器。站内 PDF 用于个人研究阅读；引用与传播请遵守原出版方和来源站点的许可条款。</footer>
</main>
<script>
const DATA_URL = "research_map.json";
const readPrefix = "quantResearchMap.read.";
let payload = null;

function sizeLabel(bytes) {
  if (!bytes) return "";
  const mb = bytes / 1024 / 1024;
  return mb < 1 ? Math.round(bytes / 1024) + " KB" : mb.toFixed(1) + " MB";
}

function renderWeeks() {
  const container = document.getElementById("weeks");
  container.innerHTML = payload.weeks.map(item => `
    <article class="week">
      <b>${item.week}</b>
      <h3>${item.theme}</h3>
      <div class="codes">${item.codes.join(" · ")}</div>
      <p>${item.goal}</p>
    </article>`).join("");
}

function isLocal(item) {
  return item.availability === "local-pdf" || item.availability === "existing-report";
}

function render() {
  const query = document.getElementById("search").value.trim().toLowerCase();
  const category = document.getElementById("category").value;
  const priority = document.getElementById("priority").value;
  const availability = document.getElementById("availability").value;
  const filtered = payload.entries.filter(item => {
    const haystack = [item.code, item.title, item.citation, item.method, item.system_mapping, item.reading_focus, item.category].join(" ").toLowerCase();
    const availabilityMatch = !availability || (availability === "local" ? isLocal(item) : !isLocal(item));
    return (!query || haystack.includes(query)) && (!category || item.category_slug === category) && (!priority || item.priority === priority) && availabilityMatch;
  });

  document.getElementById("summary").textContent = `显示 ${filtered.length} / ${payload.entries.length} 条 · 已读 ${payload.entries.filter(item => localStorage.getItem(readPrefix + item.code) === "1").length}`;
  const container = document.getElementById("entries");
  if (!filtered.length) {
    container.innerHTML = '<div class="empty">没有匹配的条目。</div>';
    return;
  }
  const groups = new Map();
  filtered.forEach(item => {
    if (!groups.has(item.category_slug)) groups.set(item.category_slug, []);
    groups.get(item.category_slug).push(item);
  });
  container.innerHTML = "";
  payload.categories.forEach(categoryItem => {
    const items = groups.get(categoryItem.slug);
    if (!items) return;
    const section = document.createElement("section");
    section.innerHTML = `<div class="category-heading"><h3>${categoryItem.label}</h3><span>${items.length} 条</span></div>`;
    items.forEach(item => {
      const article = document.createElement("article");
      article.className = "entry" + (localStorage.getItem(readPrefix + item.code) === "1" ? " is-read" : "");
      const local = isLocal(item);
      const primaryHref = local ? encodeURI(item.web_path) : item.source_url;
      const primaryText = local ? "打开 PDF" : "访问来源页";
      const availabilityText = item.availability === "existing-report" ? "复用历史研报库" : (local ? sizeLabel(item.size_bytes) : "站内暂无 PDF");
      article.innerHTML = `
        <div><div class="entry-code">${item.code}</div><span class="priority priority-${item.priority}">${item.priority}</span></div>
        <div>
          <h4>${item.title}</h4>
          <p class="citation">${item.citation}</p>
          <p class="detail"><b>方法：</b>${item.method}</p>
          <p class="detail"><b>系统映射：</b>${item.system_mapping}</p>
          <p class="detail"><b>研读重点：</b>${item.reading_focus}</p>
        </div>
        <div class="entry-actions">
          <a class="button ${local ? "primary" : ""}" href="${primaryHref}" target="_blank" rel="noopener">${primaryText}</a>
          ${local ? `<a class="button" href="${item.source_url}" target="_blank" rel="noopener">原始来源</a>` : ""}
          <span class="availability">${availabilityText}</span>
          <label class="read-toggle"><input type="checkbox" ${localStorage.getItem(readPrefix + item.code) === "1" ? "checked" : ""}><span>已阅读</span></label>
        </div>`;
      article.querySelector("input").addEventListener("change", event => {
        if (event.target.checked) localStorage.setItem(readPrefix + item.code, "1");
        else localStorage.removeItem(readPrefix + item.code);
        article.classList.toggle("is-read", event.target.checked);
        render();
      });
      section.appendChild(article);
    });
    container.appendChild(section);
  });
}

fetch(DATA_URL)
  .then(response => {
    if (!response.ok) throw new Error("索引加载失败");
    return response.json();
  })
  .then(data => {
    payload = data;
    const localCount = payload.entries.filter(isLocal).length;
    document.getElementById("stat-total").textContent = payload.entries.length;
    document.getElementById("stat-local").textContent = localCount;
    document.getElementById("stat-source").textContent = payload.entries.length - localCount;
    document.getElementById("stat-categories").textContent = payload.categories.length;
    const select = document.getElementById("category");
    payload.categories.forEach(item => {
      const option = document.createElement("option");
      option.value = item.slug;
      option.textContent = item.short;
      select.appendChild(option);
    });
    renderWeeks();
    ["search", "category", "priority", "availability"].forEach(id => {
      document.getElementById(id).addEventListener(id === "search" ? "input" : "change", render);
    });
    render();
  })
  .catch(error => {
    document.getElementById("summary").textContent = error.message;
  });
</script>
</body>
</html>
'''


if __name__ == "__main__":
    raise SystemExit(main())
