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

from inventory_price_state import (
    load_state,
    new_iphone_cell_changed_at,
    used_cell_changed_at,
)

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


def parse_new_iphone_inventory_line(line: str) -> tuple[str, str, str, str] | None:
    """
    1行から (機種名, 在庫, ストレージ表記, 価格表記) を取り出す。
    新形式: タブ区切り4列。旧形式: 「iPhone xxx 在庫あり」（storage/price は空）。
    """
    s = line.strip()
    if not s:
        return None
    if "\t" in s:
        parts = s.split("\t")
        if len(parts) >= 4:
            return (
                parts[0].strip(),
                parts[1].strip(),
                parts[2].strip(),
                parts[3].strip(),
            )
        if len(parts) >= 2:
            return parts[0].strip(), parts[1].strip(), "", ""
    for suffix in ("在庫あり", "在庫なし", "不明"):
        if s.endswith(suffix):
            model = s[: -len(suffix)].strip()
            if model:
                return model, suffix, "", ""
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


def _meta_td(value: str, *, extra_class: str = "") -> str:
    cls = "inventory-meta" + (f" {extra_class}" if extra_class else "")
    return f'<td class="{cls}">{html.escape(value)}</td>'


def new_iphone_table_from_txt(raw: str, state: dict | None = None) -> str | None:
    """新品 iPhone 用 pivot テーブル HTML（在庫・ストレージ・価格・価格変動の4段）。"""
    grid: dict[str, dict[str, dict[str, str]]] = {}
    for line in raw.splitlines():
        parsed = parse_new_iphone_inventory_line(line.strip())
        if not parsed:
            continue
        model, stock, storage, price = parsed
        place = classify_new_iphone_model(model)
        if not place:
            continue
        row_k, col_k = place
        if row_k not in grid:
            grid[row_k] = {
                c: {"stock": "", "storage": "", "price": ""}
                for c, _ in NEW_IPHONE_COLUMNS
            }
        grid[row_k][col_k] = {
            "stock": stock,
            "storage": storage,
            "price": price,
        }

    if not grid:
        return None

    head_cells = "".join(
        f'<th scope="col">{html.escape(label)}</th>' for _key, label in NEW_IPHONE_COLUMNS
    )
    header_row = f'<tr><th scope="col">機種</th>{head_cells}</tr>'

    body_rows: list[str] = []
    for row_k in ordered_new_iphone_row_keys(set(grid.keys())):
        rank_cells = grid[row_k]
        row_title = new_iphone_row_label(row_k)
        vals_stock: list[str] = []
        vals_storage: list[str] = []
        vals_price: list[str] = []
        for col_k, _lbl in NEW_IPHONE_COLUMNS:
            cell = rank_cells.get(col_k) or {}
            st = (cell.get("stock") or "").strip()
            su = (cell.get("storage") or "").strip()
            pr = (cell.get("price") or "").strip()
            vals_stock.append(st if st else NEW_IPHONE_EMPTY_CELL)
            vals_storage.append(su if su else NEW_IPHONE_EMPTY_CELL)
            vals_price.append(pr if pr else NEW_IPHONE_EMPTY_CELL)
        td_stock = "".join(
            f'<td class="{inventory_stock_td_class(v)}">{html.escape(v)}</td>'
            for v in vals_stock
        )
        td_storage = "".join(
            f'<td class="inventory-meta">{html.escape(v)}</td>' for v in vals_storage
        )
        td_price_parts: list[str] = []
        td_change_parts: list[str] = []
        for j, col_k in enumerate(c for c, _ in NEW_IPHONE_COLUMNS):
            pr = vals_price[j]
            ch_at = (
                new_iphone_cell_changed_at(state or {}, row_k, col_k)
                if state
                else None
            )
            p_extra = "price-change-highlight" if ch_at else ""
            td_price_parts.append(_meta_td(pr, extra_class=p_extra))
            d_extra = "price-change-date" if ch_at else ""
            d_val = ch_at if ch_at else NEW_IPHONE_EMPTY_CELL
            td_change_parts.append(_meta_td(d_val, extra_class=d_extra))
        td_price = "".join(td_price_parts)
        td_change = "".join(td_change_parts)
        body_rows.append(
            "<tr>"
            f'<th scope="row" rowspan="3">{html.escape(row_title)}</th>'
            f"{td_stock}</tr>"
        )
        body_rows.append(f"<tr>{td_storage}</tr>")
        body_rows.append(f"<tr>{td_price}</tr>")
        body_rows.append(
            f'<tr><th scope="row">{html.escape("価格変動")}</th>{td_change}</tr>'
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
    st = load_state(repo_root)
    table_inner = new_iphone_table_from_txt(raw, st)
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


def parse_inventory_record_line(line: str) -> tuple[str, str, str, str, str] | None:
    """1 行から (機種名, ランク, 在庫, 最小ストレージ表記, 価格表記) を取り出す。
    旧形式 …、ランク：A+、在庫のみ も可（storage/price は空）。"""
    sep = "、ランク："
    if sep not in line:
        return None
    title, tail = line.split(sep, 1)
    title = title.strip()
    parts = tail.split("、")
    if len(parts) < 2:
        return None
    rank_txt = parts[0].strip()
    stock = parts[1].strip()
    storage = parts[2].strip() if len(parts) > 2 else ""
    price = parts[3].strip() if len(parts) > 3 else ""
    if not title or not rank_txt or not stock:
        return None
    return title, rank_txt, stock, storage, price


def inventory_table_from_txt(raw: str, state: dict | None = None) -> str | None:
    """
    pivot 済みテーブル HTML を返す（機種ごとに在庫行・ストレージ行・価格行の3段）。
    pivot できる行が 1 件も無いときは None。
    """
    grouped: OrderedDict[str, dict[str, dict[str, str]]] = OrderedDict()

    for line in raw.splitlines():
        t = line.strip()
        if not t:
            continue
        parsed = parse_inventory_record_line(t)
        if not parsed:
            continue
        title, rank_txt, stock, storage, price = parsed
        if rank_txt not in _RANK_KEYS:
            continue
        if title not in grouped:
            grouped[title] = {
                k: {"stock": "", "storage": "", "price": ""} for k in _RANK_KEYS
            }
        grouped[title][rank_txt] = {
            "stock": stock,
            "storage": storage,
            "price": price,
        }

    if not grouped:
        return None

    head_cells = ''.join(
        f'<th scope="col">{html.escape(label)}</th>'
        for _key, label in RANK_COLUMNS
    )
    header_row = (
        f'<tr><th scope="col">iPhone</th>{head_cells}</tr>'
    )

    body_rows: list[str] = []
    for full_title in grouped:
        rank_cells = grouped[full_title]
        row_label = iphone_label_cell(full_title)
        vals_stock: list[str] = []
        vals_storage: list[str] = []
        vals_price: list[str] = []
        for key, _lbl in RANK_COLUMNS:
            cell = rank_cells.get(key) or {}
            st = (cell.get("stock") or "").strip()
            su = (cell.get("storage") or "").strip()
            pr = (cell.get("price") or "").strip()
            vals_stock.append(st if st else MISSING_STOCK_CELL)
            vals_storage.append(su if su else MISSING_STOCK_CELL)
            vals_price.append(pr if pr else MISSING_STOCK_CELL)
        td_stock = "".join(
            f'<td class="{inventory_stock_td_class(v)}">{html.escape(v)}</td>'
            for v in vals_stock
        )
        td_storage = "".join(
            f'<td class="inventory-meta">{html.escape(v)}</td>' for v in vals_storage
        )
        td_price_parts: list[str] = []
        td_change_parts: list[str] = []
        for j, rk in enumerate(c for c, _ in RANK_COLUMNS):
            pr = vals_price[j]
            ch_at = (
                used_cell_changed_at(state or {}, full_title, rk) if state else None
            )
            p_extra = "price-change-highlight" if ch_at else ""
            td_price_parts.append(_meta_td(pr, extra_class=p_extra))
            d_extra = "price-change-date" if ch_at else ""
            d_val = ch_at if ch_at else MISSING_STOCK_CELL
            td_change_parts.append(_meta_td(d_val, extra_class=d_extra))
        td_price = "".join(td_price_parts)
        td_change = "".join(td_change_parts)
        body_rows.append(
            "<tr>"
            f'<th scope="row" rowspan="3">{html.escape(row_label)}</th>'
            f"{td_stock}</tr>"
        )
        body_rows.append(f"<tr>{td_storage}</tr>")
        body_rows.append(f"<tr>{td_price}</tr>")
        body_rows.append(
            f'<tr><th scope="row">{html.escape("価格変動")}</th>{td_change}</tr>'
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

    st = load_state(repo_root)
    table_inner = inventory_table_from_txt(raw, st)
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
    .inventory-table td.inventory-meta {
      background: #f8fafc;
      color: #334155;
      font-size: 0.92em;
      font-weight: 500;
    }
    .inventory-table td.inventory-meta.price-change-highlight {
      background: #ecfdf5;
      color: #15803d;
      font-weight: 700;
      box-shadow: inset 0 0 0 1px rgba(22,163,74,0.35);
    }
    .inventory-table td.inventory-meta.price-change-date {
      background: #ecfdf5;
      color: #15803d;
      font-weight: 700;
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
    <strong>在庫状況の再取得を依頼</strong> は別タブで ahamo のサイトの在庫状況を取得します。<br>
    取得が始まったら、およそ数分〜5分ほどで反映されます（キューにより前後します）。<br>
    しばらくしてから <strong>表示を更新</strong> を押すと、在庫表が最新になります。<br>
    情報は約30分に一度自動的に更新されます。
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
  <p class="time-main">データ更新日時(JST): {time_jst} (30分に一度自動更新)</p>
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
