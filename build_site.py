"""
used_term_select_full.png から GitHub Pages 用の index.html を生成する。

index.html の並び:
  見出し〜注記 → 新品iPhone在庫表 → リユース在庫表 → スクリプト → new_iphone_list_full.png → used_term_select_full.png

new_iphone_inventory_lines.txt / new_iphone_list_full.png があれば site/ にコピーし、
new-iphone.html（単体ページ）も従来どおり出力する。

CI では main.py 成功後にこのスクリプトを実行する。

環境変数:
  GAS_TRIGGER_URL … GAS ウェブアプリの実行 URL（?token= 付き完全 URL）。
                    設定時のみ「スクショの再取得を依頼」ボタンを出力する。
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import sys
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path

IMAGE_NAME = "used_term_select_full.png"
NEW_IPHONE_IMAGE_NAME = "new_iphone_list_full.png"
SCREENSHOT_CAPTION_NEW_IPHONE = "ahamo 新品iPhone 一覧ページのスクショ"
SCREENSHOT_CAPTION_REUSED     = "ahamo リユース品 一覧ページのスクショ"
INVENTORY_LINES_NAME = "used_term_inventory_lines.txt"
NEW_IPHONE_LINES_NAME = "new_iphone_inventory_lines.txt"
NEW_IPHONE_HTML_NAME = "new-iphone.html"
JST = timezone(timedelta(hours=9))

# 列は main.py が出力する「ランク：A+」「ランク：A」「ランク：B」に対応
_RANK_KEYS = ("A+", "A", "B")
RANK_COLUMNS: tuple[tuple[str, str], ...] = (
    ("A+", "ランクA+"),
    ("A", "ランクA"),
    ("B", "ランクB"),
)
MISSING_STOCK_CELL = "—"
# 新品 iPhone 表: 空セルはユーザ指定どおり「---」
NEW_IPHONE_EMPTY_CELL = "---"
NEW_IPHONE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("norm", "ノーマル"),
    ("e", "e"),
    ("pro", "Pro"),
    ("pro_max", "Pro Max"),
)
# 新品表の行を並べる優先順（数値は世代キー文字列）
_NEW_IPHONE_ROW_PREFERRED_ORDER = (
    "17",
    "air",
    "16",
    "15",
    "14",
    "13",
    "12",
    "11",
    "10",
    "se3",
)


def inventory_stock_td_class(display_val: str) -> str:
    """データセル用クラス（在庫ありを目立たせ、その他も区別しやすくする）。"""
    if display_val == "在庫あり":
        return "stock-in"
    if display_val == "在庫なし":
        return "stock-out"
    if display_val in (MISSING_STOCK_CELL, NEW_IPHONE_EMPTY_CELL):
        return "stock-dash"
    return "stock-other"


def new_iphone_row_label(row_key: str) -> str:
    if row_key == "air":
        return "iPhone Air"
    if row_key == "se3":
        return "SE(第３世代)"
    if row_key.isdigit():
        return f"iPhone {row_key}"
    return row_key


def parse_new_iphone_inventory_line(line: str) -> tuple[str, str] | None:
    """「iPhone xxx 在庫あり」形式から (機種名, 在庫) を取り出す。"""
    s = line.strip()
    if not s:
        return None
    for suffix in ("在庫あり", "在庫なし", "不明"):
        if s.endswith(suffix):
            model = s[: -len(suffix)].strip()
            if model:
                return model, suffix
    return None


def classify_new_iphone_model(model: str) -> tuple[str, str] | None:
    """
    (表の行キー, 列キー) を返す。
    行キー: 世代の数字文字列 / air / se3
    列キー: norm / e / pro / pro_max
    """
    m = model.strip()
    if m in ("iPhone SE(第3世代)", "iPhone SE（第3世代）"):
        return ("se3", "norm")
    if m == "iPhone Air":
        return ("air", "norm")

    mm = re.match(r"^iPhone (\d+) Pro Max$", m)
    if mm:
        return (mm.group(1), "pro_max")
    mm = re.match(r"^iPhone (\d+) Pro$", m)
    if mm:
        return (mm.group(1), "pro")
    mm = re.match(r"^iPhone (\d+)e$", m)
    if mm:
        return (mm.group(1), "e")
    mm = re.match(r"^iPhone (\d+)$", m)
    if mm:
        return (mm.group(1), "norm")
    return None


def ordered_new_iphone_row_keys(keys: set[str]) -> list[str]:
    out: list[str] = [k for k in _NEW_IPHONE_ROW_PREFERRED_ORDER if k in keys]
    numeric_left = sorted(
        (k for k in keys if k not in out and k.isdigit()),
        key=int,
        reverse=True,
    )
    out.extend(numeric_left)
    out.extend(sorted(k for k in keys if k not in out))
    return out


def new_iphone_table_from_txt(raw: str) -> str | None:
    """新品 iPhone 用 pivot テーブル HTML。解釈できる行が無ければ None。"""
    grid: dict[str, dict[str, str]] = {}
    for line in raw.splitlines():
        parsed = parse_new_iphone_inventory_line(line.strip())
        if not parsed:
            continue
        model, stock = parsed
        place = classify_new_iphone_model(model)
        if not place:
            continue
        row_k, col_k = place
        if row_k not in grid:
            grid[row_k] = {c: "" for c, _ in NEW_IPHONE_COLUMNS}
        grid[row_k][col_k] = stock

    if not grid:
        return None

    head_cells = "".join(
        f'<th scope="col">{html.escape(label)}</th>' for _key, label in NEW_IPHONE_COLUMNS
    )
    header_row = f'<tr><th scope="col">機種</th>{head_cells}</tr>'

    body_rows: list[str] = []
    for row_k in ordered_new_iphone_row_keys(set(grid.keys())):
        cells = grid[row_k]
        row_title = new_iphone_row_label(row_k)
        td_parts: list[str] = []
        for col_k, _lbl in NEW_IPHONE_COLUMNS:
            v = cells.get(col_k, "").strip()
            disp = v if v else NEW_IPHONE_EMPTY_CELL
            css = inventory_stock_td_class(disp)
            td_parts.append(f'<td class="{css}">{html.escape(disp)}</td>')
        body_rows.append(
            "<tr>"
            f'<th scope="row">{html.escape(row_title)}</th>'
            f'{"".join(td_parts)}'
            "</tr>"
        )

    tbody = "\n".join(f"      {row}" for row in body_rows)
    return (
        '    <table class="inventory-table">\n'
        "      <thead>\n"
        f"        {header_row}\n"
        "      </thead>\n"
        "      <tbody>\n"
        f"{tbody}\n"
        "      </tbody>\n"
        "    </table>"
    )


def new_iphone_inventory_section_html(repo_root: Path) -> str:
    """new_iphone_inventory_lines.txt から新品在庫セクション HTML。無ければ空文字。"""
    path = repo_root / NEW_IPHONE_LINES_NAME
    if not path.is_file():
        return ""
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return ""
    table_inner = new_iphone_table_from_txt(raw)
    if not table_inner:
        return ""
    return (
        '  <section class="inventory-summary" aria-labelledby="newiphone-inv">\n'
        '    <h2 id="newiphone-inv">新品iPhoneの在庫状況（機種別）</h2>\n'
        '    <div class="inventory-table-wrap">\n'
        f"{table_inner}\n"
        "    </div>\n"
        "  </section>\n"
    )


def iphone_label_cell(full_title: str) -> str:
    """表の「iPhone」列。先頭が「iPhone 」ならそれを除いた機種名を表示する。"""
    t = full_title.strip()
    if t.startswith("iPhone "):
        return t[len("iPhone ") :].strip()
    return t


def parse_inventory_record_line(line: str) -> tuple[str, str, str] | None:
    """1 行から (機種名, ランク, 在庫) を取り出す。形式: iPhone xxx、ランク：A+、在庫あり"""
    sep = "、ランク："
    if sep not in line:
        return None
    title, tail = line.split(sep, 1)
    title = title.strip()
    parts = tail.split("、", 1)
    if len(parts) != 2:
        return None
    rank_txt = parts[0].strip()
    stock = parts[1].strip()
    if not title or not rank_txt or not stock:
        return None
    return title, rank_txt, stock


def inventory_table_from_txt(raw: str) -> str | None:
    """
    pivot 済みテーブル HTML を返す。
    pivot できる行が 1 件も無いときは None。
    """
    grouped: OrderedDict[str, dict[str, str]] = OrderedDict()

    for line in raw.splitlines():
        t = line.strip()
        if not t:
            continue
        parsed = parse_inventory_record_line(t)
        if not parsed:
            continue
        title, rank_txt, stock = parsed
        if rank_txt not in _RANK_KEYS:
            continue
        if title not in grouped:
            grouped[title] = {k: "" for k in _RANK_KEYS}
        grouped[title][rank_txt] = stock

    if not grouped:
        return None

    head_cells = ''.join(
        f'<th scope="col">{html.escape(label)}</th>'
        for _key, label in RANK_COLUMNS
    )
    header_row = (
        f'<tr><th scope="col">iPhone</th>{head_cells}</tr>'
    )

    body_rows = []
    for full_title in grouped:
        cells = grouped[full_title]
        row_label = iphone_label_cell(full_title)
        vals = []
        for key, _lbl in RANK_COLUMNS:
            v = cells.get(key, "").strip()
            vals.append(v if v else MISSING_STOCK_CELL)
        td_parts = []
        for val in vals:
            css = inventory_stock_td_class(val)
            td_parts.append(f'<td class="{css}">{html.escape(val)}</td>')
        td_stock = "".join(td_parts)
        body_rows.append(
            '<tr>'
            f'<th scope="row">{html.escape(row_label)}</th>'
            f"{td_stock}"
            '</tr>'
        )

    tbody = "\n".join(f"      {row}" for row in body_rows)
    table_inner = (
        f'    <table class="inventory-table">\n'
        f"      <thead>\n"
        f"        {header_row}\n"
        f"      </thead>\n"
        f"      <tbody>\n"
        f"{tbody}\n"
        f"      </tbody>\n"
        f"    </table>"
    )
    return table_inner


def inventory_summary_html(repo_root: Path) -> str:
    """used_term_inventory_lines.txt があれば、スクショ直上に表（または一覧）ブロック HTML を返す。"""
    path = repo_root / INVENTORY_LINES_NAME
    if not path.is_file():
        return ""
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return ""

    table_inner = inventory_table_from_txt(raw)
    if table_inner is not None:
        return (
            '  <section class="inventory-summary" aria-labelledby="inv-h">\n'
            '    <h2 id="inv-h">リユース品の在庫状況（機種・ランク別）</h2>\n'
            '    <div class="inventory-table-wrap">\n'
            f"{table_inner}\n"
            "    </div>\n"
            "  </section>\n"
        )

    # 想定と違う行形式のときは従来の箇条書きにフォールバック
    lis = []
    for line in raw.splitlines():
        t = line.strip()
        if not t:
            continue
        lis.append(f"    <li>{html.escape(t)}</li>")
    if not lis:
        return ""
    return (
        '  <section class="inventory-summary" aria-labelledby="inv-h">'
        f"\n    <h2 id=\"inv-h\">リユース品の在庫状況（機種・ランク別）</h2>\n"
        f"    <ul>\n{chr(10).join(lis)}\n    </ul>\n"
        f"  </section>\n"
    )


def shared_site_styles() -> str:
    """index / new-iphone 共通のレイアウト・在庫表スタイル。"""
    return """    *, *::before, *::after { box-sizing: border-box; }
    body {
      font-family: system-ui, sans-serif;
      margin: 1rem auto;
      width: 100%;
      max-width: 1400px;
      padding: 0 clamp(0.5rem, 2.5vw, 0.75rem);
      line-height: 1.5;
    }
    .time-main { font-size: 1.15rem; font-weight: 600; color: #111; margin: 0.5rem 0 1rem; }
    .note { font-size: 0.88rem; color: #555; margin: 0.85rem 0 1.25rem; line-height: 1.6; max-width: 46em; }
    img { max-width: 100%; height: auto; border: 1px solid #ddd; }
    .btn {
      font-size: 1rem;
      padding: 0.55rem 1.25rem;
      border: none;
      border-radius: 6px;
      color: #fff;
      cursor: pointer;
      font-weight: 600;
      margin-right: 0.5rem;
      margin-bottom: 0.35rem;
    }
    .btn-primary { background: #0d9488; }
    .btn-primary:hover { background: #0f766e; }
    .btn-secondary { background: #64748b; }
    .btn-secondary:hover { background: #475569; }
    .btn:focus-visible { outline: 2px solid #115e59; outline-offset: 2px; }
    .inventory-summary {
      margin: 0.5rem 0 1.25rem;
      padding: 0.75rem 1rem;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      font-size: 0.93rem;
      line-height: 1.55;
    }
    .inventory-summary h2 { font-size: 1rem; margin: 0 0 0.5rem 0; }
    .inventory-summary .inventory-table-wrap {
      width: 100%;
      max-width: 100%;
      margin-top: 0.25rem;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      overscroll-behavior-x: contain;
      scrollbar-gutter: stable;
      border-radius: 8px;
      border: 1px solid #e2e8f0;
      background: #fff;
    }
    .inventory-summary .inventory-table-wrap .inventory-table {
      width: max-content;
      border-collapse: collapse;
      font-size: clamp(0.78rem, 2.85vw, 0.93rem);
    }
    .inventory-summary .inventory-table-wrap .inventory-table th,
    .inventory-summary .inventory-table-wrap .inventory-table td {
      border: 1px solid #cbd5e1;
      padding: 0.35rem 0.5rem;
      text-align: left;
      vertical-align: middle;
      white-space: nowrap;
    }
    @media (min-width: 768px) {
      .inventory-summary .inventory-table-wrap .inventory-table {
        width: 100%;
        font-size: 0.93rem;
        table-layout: fixed;
      }
    }
    .inventory-table th { background: #e2e8f0; font-weight: 600; }
    .inventory-table tbody th[scope="row"] { background: #f1f5f9; font-weight: 600; }
    .inventory-table tbody tr:nth-child(even) th[scope="row"] { background: #e8eef5; }
    .inventory-table td.stock-in {
      background: #ccfbf1;
      color: #0f766e;
      font-weight: 600;
      box-shadow: inset 0 0 0 1px rgba(13,148,136,0.35);
      border-radius: 4px;
    }
    .inventory-table td.stock-out {
      background: #fce7f3;
      color: #9d174d;
    }
    .inventory-table td.stock-dash {
      background: #f3f4f6;
      color: #6b7280;
    }
    .inventory-table td.stock-other {
      background: #fef9c3;
      color: #854d0e;
    }
    .inventory-summary ul { margin: 0; padding-left: 1.35rem; }
    .inventory-summary li { margin-bottom: 0.2rem; }
    .screenshot-block { margin: 1.15rem 0 0; }
    .screenshot-heading {
      font-size: 1rem;
      font-weight: 600;
      margin: 0 0 0.45rem 0;
      color: #111;
    }
    .screenshot-block p { margin: 0; }
"""


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    img = repo_root / IMAGE_NAME
    if not img.is_file():
        print(f"error: {img} が見つかりません", file=sys.stderr)
        return 1

    out_dir = repo_root / "site"
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(img, out_dir / IMAGE_NAME)

    inv_src = repo_root / INVENTORY_LINES_NAME
    if inv_src.is_file():
        shutil.copy2(inv_src, out_dir / INVENTORY_LINES_NAME)

    new_inv_path = repo_root / NEW_IPHONE_LINES_NAME
    if new_inv_path.is_file():
        shutil.copy2(new_inv_path, out_dir / NEW_IPHONE_LINES_NAME)

    new_img_path = repo_root / NEW_IPHONE_IMAGE_NAME
    if new_img_path.is_file():
        shutil.copy2(new_img_path, out_dir / NEW_IPHONE_IMAGE_NAME)

    now_jst = datetime.now(timezone.utc).astimezone(JST)

    new_inv_block = new_iphone_inventory_section_html(repo_root)
    reused_inv_block = inventory_summary_html(repo_root)

    title = "ahamo iPhone 在庫状況(新品・リユース品)"

    time_jst = now_jst.strftime("%Y-%m-%d %H:%M:%S")

    gas_trigger_url = os.environ.get("GAS_TRIGGER_URL", "").strip()
    gas_url_json = json.dumps(gas_trigger_url)

    reload_btn = '<button type="button" class="btn btn-secondary" id="reload-page">表示を更新</button>'
    if gas_trigger_url:
        workflow_btn = (
            '<button type="button" class="btn btn-primary" id="request-workflow">'
            "在庫状況の再取得を依頼</button>"
        )
        buttons_block = (
            f"<p>{reload_btn} {workflow_btn}</p>"
        )
        note_block = """  <p class="note">
    <strong>表示を更新</strong> はこのページだけ再読み込みします。<br>
    <strong>在庫状況の再取得を依頼</strong> は別タブで ahamo のサイトのリユース品一覧ページの在庫状況を取得します。<br>
    取得が始まったら、およそ数分〜5分ほどで反映されます（キューにより前後します）。<br>
    しばらくしてから <strong>表示を更新</strong> を押すと、在庫表が最新になります。
  </p>
"""
        script_handlers = """  <script>
    (function () {
      document.getElementById("reload-page").addEventListener("click", function () {
        var u = new URL(window.location.href);
        u.searchParams.set("v", String(Date.now()));
        window.location.replace(u.toString());
      });
      var gasUrl = """ + gas_url_json + """;
      var req = document.getElementById("request-workflow");
      if (req && gasUrl) {
        req.addEventListener("click", function () {
          window.open(gasUrl, "_blank", "noopener,noreferrer");
        });
      }
    })();
  </script>
"""
    else:
        buttons_block = f'<p><button type="button" class="btn btn-primary" id="reload-page">在庫状況確認</button></p>'
        note_block = """  <p class="note">
    このボタンは<strong>ページと画像 URL を読み込みなおします</strong>（キャッシュ対策）。
    「新しくスクショを撮って公開する」には GitHub Actions が必要です。リポジトリに <code>GAS_TRIGGER_URL</code> シークレットを設定すると、
    「スクショの再取得を依頼」ボタンが追加されます（手順は <code>docs/GAS_TRIGGER_SETUP.md</code>）。
  </p>
"""
        script_handlers = """  <script>
    (function () {
      document.getElementById("reload-page").addEventListener("click", function () {
        var u = new URL(window.location.href);
        u.searchParams.set("v", String(Date.now()));
        window.location.replace(u.toString());
      });
    })();
  </script>
"""

    cache_bust = f"{now_jst.timestamp():.0f}"

    new_img_html = ""
    if (out_dir / NEW_IPHONE_IMAGE_NAME).is_file():
        cap_new = html.escape(SCREENSHOT_CAPTION_NEW_IPHONE)
        new_img_html = (
            '  <div class="screenshot-block">\n'
            f'    <h2 class="screenshot-heading">{cap_new}</h2>\n'
            f'    <p><img src="{NEW_IPHONE_IMAGE_NAME}?v={cache_bust}" '
            'alt="新品iPhone 一覧ページのスクリーンショット"></p>\n'
            "  </div>\n"
        )

    cap_used = html.escape(SCREENSHOT_CAPTION_REUSED)
    used_img_html = (
        '  <div class="screenshot-block">\n'
        f'    <h2 class="screenshot-heading">{cap_used}</h2>\n'
        f'    <p><img src="{IMAGE_NAME}?v={cache_bust}" '
        'alt="リユース品の選択 ページ全体"></p>\n'
        "  </div>\n"
    )

    index_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
{shared_site_styles()}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="time-main">データ更新日時(JST): {time_jst} (30分に一度更新)</p>
{buttons_block}
{note_block}
{new_inv_block}{reused_inv_block}{script_handlers}
{new_img_html}{used_img_html}</body>
</html>
"""
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")

    if new_inv_block:
        title_new_iphone = "ahamo 新品iPhone在庫状況"
        esc_new = html.escape(title_new_iphone)
        new_page = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc_new}</title>
  <style>
{shared_site_styles()}
  </style>
</head>
<body>
  <h1>{esc_new}</h1>
  <p class="time-main">データ更新日時（日本時間・JST）: <br>{time_jst}</p>
{buttons_block}
{note_block}
{new_inv_block}{script_handlers}
</body>
</html>
"""
        (out_dir / NEW_IPHONE_HTML_NAME).write_text(new_page, encoding="utf-8")
        print(f"new-iphone page -> {(out_dir / NEW_IPHONE_HTML_NAME).resolve()}")

    print(f"site -> {out_dir.resolve()}")
    if gas_trigger_url:
        print("build_site: GAS_TRIGGER_URL is set（再取得ボタンを出力）")
    else:
        print("build_site: GAS_TRIGGER_URL は未設定（再取得ボタンなし）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
