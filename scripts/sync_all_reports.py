from __future__ import annotations

import csv
import base64
import hashlib
import html
import json
import os
import shutil
import subprocess
import sys
import tarfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


REMOTE = "alexnas805"
REMOTE_PARENT = "/mnt/research"
REMOTE_DIR_NAME = "研报"
REMOTE_ROOT = f"{REMOTE_PARENT}/{REMOTE_DIR_NAME}"

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGING_ROOT = REPO_ROOT.parent / "_quant_reports_staging"
STAGING_PAYLOAD = STAGING_ROOT / "payload"
STAGING_MANIFEST = STAGING_ROOT / "remote_manifest.json"
REPORTS_DIR = REPO_ROOT / "reports"

MANIFEST_JSON = REPO_ROOT / "reports_manifest.json"
MANIFEST_CSV = REPO_ROOT / "reports_manifest.csv"
ALL_REPORTS_HTML = REPO_ROOT / "all-reports.html"
INDEX_HTML = REPO_ROOT / "index.html"

WINDOWS_FORBIDDEN = set('<>:"\\|?*')
RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

REMOTE_PACK_SCRIPT = r"""
import io
import json
import os
import sys
import tarfile

root = "/mnt/research/研报"
files = []
for dirpath, dirnames, filenames in os.walk(root):
    dirnames.sort()
    for filename in sorted(filenames):
        path = os.path.join(dirpath, filename)
        if os.path.isfile(path):
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            files.append((rel, path))

files.sort(key=lambda item: item[0].casefold())
entries = []
with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tf:
    for index, (rel, path) in enumerate(files, start=1):
        name, ext = os.path.splitext(rel)
        ext = ext.lower()
        if not ext or len(ext) > 16 or any(ord(ch) > 127 or ch in "/\\" for ch in ext):
            ext = ".bin"
        payload = f"payload/{index:06d}{ext}"
        st = os.stat(path)
        entries.append(
            {
                "id": index,
                "source_relative_path": rel,
                "payload_path": payload,
                "size_bytes": st.st_size,
                "mtime_epoch": st.st_mtime,
            }
        )
        info = tf.gettarinfo(path, arcname=payload)
        with open(path, "rb") as f:
            tf.addfile(info, f)

    data = json.dumps(entries, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    info = tarfile.TarInfo("remote_manifest.json")
    info.size = len(data)
    tf.addfile(info, io.BytesIO(data))
"""


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def download_remote_tree() -> None:
    if STAGING_ROOT.exists():
        shutil.rmtree(STAGING_ROOT)
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)

    encoded = base64.b64encode(REMOTE_PACK_SCRIPT.encode("utf-8")).decode("ascii")
    remote_cmd = f"python3 -c \"import base64; exec(base64.b64decode('{encoded}'))\""
    print(f"Downloading {REMOTE}:{REMOTE_ROOT} to {STAGING_ROOT}", flush=True)
    ssh = subprocess.Popen(["ssh", REMOTE, remote_cmd], stdout=subprocess.PIPE)
    assert ssh.stdout is not None
    with tarfile.open(fileobj=ssh.stdout, mode="r|*") as tf:
        staging_resolved = STAGING_ROOT.resolve()
        for member in tf:
            if not member.isfile():
                continue
            target = (STAGING_ROOT / member.name).resolve()
            if not str(target).startswith(str(staging_resolved)):
                raise RuntimeError(f"unsafe tar member path: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tf.extractfile(member)
            if source is None:
                raise RuntimeError(f"could not extract tar member: {member.name}")
            with target.open("wb") as f:
                shutil.copyfileobj(source, f)
    ssh.stdout.close()
    ssh_code = ssh.wait()
    if ssh_code != 0:
        raise RuntimeError(f"remote pack failed with exit code {ssh_code}")
    if not STAGING_MANIFEST.exists():
        raise RuntimeError(f"expected remote manifest missing: {STAGING_MANIFEST}")


def sanitize_part(part: str) -> str:
    part = unicodedata.normalize("NFC", part)
    cleaned = "".join(
        "_" if ch in WINDOWS_FORBIDDEN or ord(ch) < 32 else ch
        for ch in part
    )
    cleaned = cleaned.rstrip(" .")
    if not cleaned:
        cleaned = "_"
    stem = cleaned.split(".", 1)[0].upper()
    if stem in RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned


def unique_target(rel: Path, used: dict[str, str]) -> Path:
    parts = [sanitize_part(part) for part in rel.parts]
    candidate = Path(*parts)
    key = candidate.as_posix().casefold()
    original = rel.as_posix()
    if key not in used:
        used[key] = original
        return candidate
    if used[key] == original:
        return candidate

    digest = hashlib.sha1(original.encode("utf-8")).hexdigest()[:10]
    parent = candidate.parent
    name = candidate.name
    suffix = "".join(Path(name).suffixes)
    stem = name[: -len(suffix)] if suffix else name
    candidate = parent / f"{stem}__{digest}{suffix}"
    used[candidate.as_posix().casefold()] = original
    return candidate


def copy_reports() -> list[dict[str, object]]:
    if REPORTS_DIR.exists():
        shutil.rmtree(REPORTS_DIR)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    used: dict[str, str] = {}
    entries: list[dict[str, object]] = []
    remote_entries = json.loads(STAGING_MANIFEST.read_text(encoding="utf-8"))

    for entry in remote_entries:
        index = int(entry["id"])
        src = STAGING_ROOT / str(entry["payload_path"])
        source_rel = Path(str(entry["source_relative_path"]))
        target_rel = unique_target(source_rel, used)
        dst = REPORTS_DIR / target_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

        ext = src.suffix.lower().lstrip(".") or "none"
        source_rel_posix = source_rel.as_posix()
        web_path = (Path("reports") / target_rel).as_posix()
        folder = source_rel.parts[0] if len(source_rel.parts) > 1 else "根目录"
        entries.append(
            {
                "id": index,
                "source_folder": folder,
                "source_relative_path": source_rel_posix,
                "remote_path": f"{REMOTE_ROOT}/{source_rel_posix}",
                "web_path": web_path,
                "file_name": source_rel.name,
                "display_name": source_rel.stem,
                "extension": ext,
                "size_bytes": int(entry["size_bytes"]),
                "mtime": datetime.fromtimestamp(float(entry["mtime_epoch"]), timezone.utc).isoformat(),
            }
        )

    return entries


def write_manifest(entries: list[dict[str, object]]) -> None:
    MANIFEST_JSON.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    fieldnames = [
        "id",
        "source_folder",
        "source_relative_path",
        "remote_path",
        "web_path",
        "file_name",
        "display_name",
        "extension",
        "size_bytes",
        "mtime",
    ]
    with MANIFEST_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(entries)


def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def write_all_reports_html(entries: list[dict[str, object]]) -> None:
    total = len(entries)
    pdf_count = sum(1 for e in entries if e["extension"] == "pdf")
    non_pdf_count = total - pdf_count
    total_size = sum(int(e["size_bytes"]) for e in entries)
    folder_count = len({str(e["source_folder"]) for e in entries})
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>全量研报库</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif; color: #1f2933; background: #f7f8fa; }}
    header {{ background: #102a43; color: #fff; padding: 24px 32px; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    a {{ color: #0b65c2; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .panel, .report {{ background: #fff; border: 1px solid #d9e2ec; border-radius: 8px; }}
    .panel {{ padding: 16px; margin-bottom: 18px; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin: 16px 0; }}
    .stat {{ background: #fff; border: 1px solid #d9e2ec; border-radius: 8px; padding: 12px; }}
    .stat b {{ display: block; font-size: 22px; color: #102a43; }}
    .toolbar {{ display: grid; grid-template-columns: minmax(220px, 1fr) 180px 180px; gap: 10px; align-items: center; }}
    input, select {{ width: 100%; box-sizing: border-box; border: 1px solid #b6c2cf; border-radius: 6px; padding: 9px 10px; font: inherit; background: #fff; color: #1f2933; }}
    .meta {{ color: #627d98; font-size: 13px; }}
    .report {{ padding: 13px 15px; margin: 10px 0; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px 16px; }}
    .report-title {{ font-weight: 650; overflow-wrap: anywhere; }}
    .badge {{ display: inline-block; background: #e0f2fe; color: #075985; border-radius: 999px; padding: 2px 8px; font-size: 12px; margin-right: 6px; }}
    .actions {{ white-space: nowrap; }}
    .empty {{ padding: 18px; color: #627d98; }}
    @media (max-width: 760px) {{
      header {{ padding: 20px; }}
      main {{ padding: 18px; }}
      .toolbar {{ grid-template-columns: 1fr; }}
      .report {{ grid-template-columns: 1fr; }}
      .actions {{ white-space: normal; }}
    }}
  </style>
</head>
<body>
<header>
  <h1>全量研报库</h1>
  <p>从服务器 /mnt/research/研报/ 同步，生成时间：{html.escape(generated_at)}</p>
</header>
<main>
  <section class="panel">
    <p><a href="index.html">返回精选阅读计划</a> · <a href="reports_manifest.json">JSON 索引</a> · <a href="reports_manifest.csv">CSV 索引</a></p>
    <div class="stats">
      <div class="stat"><b>{total}</b><span>全部文件</span></div>
      <div class="stat"><b>{pdf_count}</b><span>PDF</span></div>
      <div class="stat"><b>{non_pdf_count}</b><span>其他文件</span></div>
      <div class="stat"><b>{folder_count}</b><span>来源目录</span></div>
      <div class="stat"><b>{html.escape(format_bytes(total_size))}</b><span>总大小</span></div>
    </div>
    <div class="toolbar">
      <input id="search" type="search" placeholder="搜索标题、券商、路径">
      <select id="folder"><option value="">全部来源</option></select>
      <select id="extension"><option value="">全部类型</option></select>
    </div>
    <p class="meta" id="summary"></p>
  </section>
  <section id="reports"></section>
</main>
<script>
const reports = [];
const source = "reports_manifest.json";

function sizeLabel(bytes) {{
  const units = ["B", "KB", "MB", "GB"];
  let value = Number(bytes);
  for (const unit of units) {{
    if (value < 1024 || unit === units[units.length - 1]) {{
      return unit === "B" ? Math.round(value) + " B" : value.toFixed(1) + " " + unit;
    }}
    value /= 1024;
  }}
}}

function optionList(select, values) {{
  for (const value of values) {{
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  }}
}}

function render() {{
  const q = document.getElementById("search").value.trim().toLowerCase();
  const folder = document.getElementById("folder").value;
  const extension = document.getElementById("extension").value;
  const list = reports.filter(item => {{
    const haystack = [item.display_name, item.file_name, item.source_folder, item.source_relative_path].join(" ").toLowerCase();
    return (!q || haystack.includes(q)) && (!folder || item.source_folder === folder) && (!extension || item.extension === extension);
  }});

  const container = document.getElementById("reports");
  document.getElementById("summary").textContent = "显示 " + list.length + " / " + reports.length + " 个文件";
  container.innerHTML = "";
  if (!list.length) {{
    container.innerHTML = '<div class="panel empty">没有匹配的研报。</div>';
    return;
  }}
  const frag = document.createDocumentFragment();
  for (const item of list) {{
    const row = document.createElement("article");
    row.className = "report";
    const actionText = item.extension === "pdf" ? "打开 PDF" : "下载";
    row.innerHTML = `
      <div>
        <div class="report-title">${{item.display_name}}</div>
        <div class="meta"><span class="badge">${{item.source_folder || "未分类"}}</span><span class="badge">${{item.extension}}</span>${{sizeLabel(item.size_bytes)}} · ${{item.source_relative_path}}</div>
      </div>
      <div class="actions"><a href="${{encodeURI(item.web_path)}}" target="_blank" rel="noopener">${{actionText}}</a></div>
    `;
    frag.appendChild(row);
  }}
  container.appendChild(frag);
}}

fetch(source)
  .then(r => r.json())
  .then(data => {{
    reports.push(...data);
    optionList(document.getElementById("folder"), [...new Set(reports.map(r => r.source_folder || "未分类"))].sort((a, b) => a.localeCompare(b, "zh-Hans-CN")));
    optionList(document.getElementById("extension"), [...new Set(reports.map(r => r.extension))].sort());
    document.getElementById("search").addEventListener("input", render);
    document.getElementById("folder").addEventListener("change", render);
    document.getElementById("extension").addEventListener("change", render);
    render();
  }})
  .catch(() => {{
    document.getElementById("reports").innerHTML = '<div class="panel empty">索引加载失败，请检查 reports_manifest.json。</div>';
  }});
</script>
</body>
</html>
"""
    ALL_REPORTS_HTML.write_text(page, encoding="utf-8")


def update_index_html(entries: list[dict[str, object]]) -> None:
    text = INDEX_HTML.read_text(encoding="utf-8")
    total = len(entries)
    pdf_count = sum(1 for e in entries if e["extension"] == "pdf")
    non_pdf_count = total - pdf_count
    total_size = sum(int(e["size_bytes"]) for e in entries)
    card = f"""
<section class="card" id="all-reports">
  <h2>全量研报库</h2>
  <p>服务器 <code>/mnt/research/研报/</code> 已同步为 GitHub Pages 可访问的在线研报库。</p>
  <p><b>全部文件：</b>{total} · <b>PDF：</b>{pdf_count} · <b>其他文件：</b>{non_pdf_count} · <b>总大小：</b>{html.escape(format_bytes(total_size))}</p>
  <p><a href="all-reports.html">打开全量研报库</a> · <a href="reports_manifest.json">JSON 索引</a> · <a href="reports_manifest.csv">CSV 索引</a></p>
</section>
"""
    start_marker = '<section class="card" id="all-reports">'
    if start_marker in text:
        start = text.index(start_marker)
        end = text.index("</section>", start) + len("</section>")
        text = text[:start] + card.strip() + text[end:]
    else:
        insert_after = "</section>"
        first_end = text.index(insert_after) + len(insert_after)
        text = text[:first_end] + "\n" + card + text[first_end:]
    INDEX_HTML.write_text(text, encoding="utf-8")


def validate(entries: list[dict[str, object]]) -> None:
    copied = [p for p in REPORTS_DIR.rglob("*") if p.is_file()]
    if len(copied) != len(entries):
        raise RuntimeError(f"copied file count mismatch: {len(copied)} != {len(entries)}")
    oversized = [e for e in entries if int(e["size_bytes"]) >= 100 * 1024 * 1024]
    if oversized:
        names = ", ".join(str(e["source_relative_path"]) for e in oversized[:5])
        raise RuntimeError(f"GitHub blocks files >=100MB: {names}")
    missing = [e for e in entries if not (REPO_ROOT / str(e["web_path"])).exists()]
    if missing:
        raise RuntimeError(f"manifest references missing files, first: {missing[0]['web_path']}")


def main() -> int:
    download_remote_tree()
    entries = copy_reports()
    write_manifest(entries)
    write_all_reports_html(entries)
    update_index_html(entries)
    validate(entries)
    print(
        f"Synced {len(entries)} files, "
        f"{sum(1 for e in entries if e['extension'] == 'pdf')} PDFs, "
        f"{format_bytes(sum(int(e['size_bytes']) for e in entries))}.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
