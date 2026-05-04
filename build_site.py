"""
used_term_select_full.png から GitHub Pages 用の index.html を生成する。
CI では main.py 成功後にこのスクリプトを実行する。

環境変数:
  GAS_TRIGGER_URL … GAS ウェブアプリの実行 URL（?token= 付き完全 URL）。
                    設定時のみ「スクショの再取得を依頼」ボタンを出力する。
"""

from __future__ import annotations

import html
import json
import os
import shutil
import sys
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path

IMAGE_NAME = "used_term_select_full.png"
INVENTORY_LINES_NAME = "used_term_inventory_lines.txt"
JST = timezone(timedelta(hours=9))

# 列は main.py が出力する「ランク：A+」「ランク：A」「ランク：B」に対応
_RANK_KEYS = ("A+", "A", "B")
RANK_COLUMNS: tuple[tuple[str, str], ...] = (
    ("A+", "ランクA+在庫"),
    ("A", "ランクA在庫"),
    ("B", "ランクB"),
)
MISSING_STOCK_CELL = "—"


def inventory_stock_td_class(display_val: str) -> str:
    """データセル用クラス（在庫ありを目立たせ、その他も区別しやすくする）。"""
    if display_val == "在庫あり":
        return "stock-in"
    if display_val == "在庫なし":
        return "stock-out"
    if display_val == MISSING_STOCK_CELL:
        return "stock-dash"
    return "stock-other"


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
            '    <h2 id="inv-h">機種・ランク別の在庫</h2>\n'
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
        f"\n    <h2 id=\"inv-h\">機種・ランク別の在庫</h2>\n"
        f"    <ul>\n{chr(10).join(lis)}\n    </ul>\n"
        f"  </section>\n"
    )


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

    now_jst = datetime.now(timezone.utc).astimezone(JST)

    inv_block = inventory_summary_html(repo_root)

    title = "ahamo リユース品の選択（スクショ）"

    time_jst = now_jst.strftime("%Y-%m-%d %H:%M:%S")

    gas_trigger_url = os.environ.get("GAS_TRIGGER_URL", "").strip()
    gas_url_json = json.dumps(gas_trigger_url)

    reload_btn = '<button type="button" class="btn btn-secondary" id="reload-page">表示を更新</button>'
    if gas_trigger_url:
        workflow_btn = (
            '<button type="button" class="btn btn-primary" id="request-workflow">'
            "スクショの再取得を依頼</button>"
        )
        buttons_block = (
            f"<p>{reload_btn} {workflow_btn}</p>"
        )
        note_block = """  <p class="note">
    <strong>表示を更新</strong> はこのページだけ再読み込みします。<strong>スクショの再取得を依頼</strong> は別タブで ahamo のサイトのリユース品一覧ページのスクショを取得します。
    取得が始まったら、およそ数分〜5分ほどで反映されます（キューにより前後します）。しばらくしてから <strong>表示を更新</strong> を押すと、スクショと在庫表が最新になります。
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

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      font-family: system-ui, sans-serif;
      margin: 1rem auto;
      width: 100%;
      max-width: 1400px;
      padding: 0 clamp(0.5rem, 2.5vw, 0.75rem);
      line-height: 1.5;
    }}
    .time-main {{ font-size: 1.15rem; font-weight: 600; color: #111; margin: 0.5rem 0 1rem; }}
    .note {{ font-size: 0.88rem; color: #555; margin: 0.85rem 0 1.25rem; line-height: 1.6; max-width: 46em; }}
    img {{ max-width: 100%; height: auto; border: 1px solid #ddd; }}
    .btn {{
      font-size: 1rem;
      padding: 0.55rem 1.25rem;
      border: none;
      border-radius: 6px;
      color: #fff;
      cursor: pointer;
      font-weight: 600;
      margin-right: 0.5rem;
      margin-bottom: 0.35rem;
    }}
    .btn-primary {{ background: #0d9488; }}
    .btn-primary:hover {{ background: #0f766e; }}
    .btn-secondary {{ background: #64748b; }}
    .btn-secondary:hover {{ background: #475569; }}
    .btn:focus-visible {{ outline: 2px solid #115e59; outline-offset: 2px; }}
    .inventory-summary {{
      margin: 0.5rem 0 1.25rem;
      padding: 0.75rem 1rem;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      font-size: 0.93rem;
      line-height: 1.55;
    }}
    .inventory-summary h2 {{ font-size: 1rem; margin: 0 0 0.5rem 0; }}
    .inventory-summary .inventory-table-wrap {{
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
    }}
    /* スマホ: コンテンツ実幅で横スクロール（一覧全体が指で見渡せる） */
    .inventory-summary .inventory-table-wrap .inventory-table {{
      width: max-content;
      border-collapse: collapse;
      font-size: clamp(0.78rem, 2.85vw, 0.93rem);
    }}
    .inventory-summary .inventory-table-wrap .inventory-table th,
    .inventory-summary .inventory-table-wrap .inventory-table td {{
      border: 1px solid #cbd5e1;
      padding: 0.35rem 0.5rem;
      text-align: left;
      vertical-align: middle;
      white-space: nowrap;
    }}
    /* PC〜タブレット: コンテナ幅いっぱいに広げる */
    @media (min-width: 768px) {{
      .inventory-summary .inventory-table-wrap .inventory-table {{
        width: 100%;
        font-size: 0.93rem;
        table-layout: fixed;
      }}
    }}
    .inventory-table th {{ background: #e2e8f0; font-weight: 600; }}
    .inventory-table tbody th[scope="row"] {{ background: #f1f5f9; font-weight: 600; }}
    .inventory-table tbody tr:nth-child(even) th[scope="row"] {{ background: #e8eef5; }}
    .inventory-table td.stock-in {{
      background: #ccfbf1;
      color: #0f766e;
      font-weight: 600;
      box-shadow: inset 0 0 0 1px rgba(13,148,136,0.35);
      border-radius: 4px;
    }}
    .inventory-table td.stock-out {{
      background: #fce7f3;
      color: #9d174d;
    }}
    .inventory-table td.stock-dash {{
      background: #f3f4f6;
      color: #6b7280;
    }}
    .inventory-table td.stock-other {{
      background: #fef9c3;
      color: #854d0e;
    }}
    .inventory-summary ul {{ margin: 0; padding-left: 1.35rem; }}
    .inventory-summary li {{ margin-bottom: 0.2rem; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="time-main">スクショ取得日時（日本時間・JST）: {time_jst}</p>
{buttons_block}
{note_block}
{inv_block}{script_handlers}
  <p><img src="{IMAGE_NAME}?v={now_jst.timestamp():.0f}" alt="リユース品の選択 ページ全体"></p>
</body>
</html>
"""
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"site -> {out_dir.resolve()}")
    if gas_trigger_url:
        print("build_site: GAS_TRIGGER_URL is set（再取得ボタンを出力）")
    else:
        print("build_site: GAS_TRIGGER_URL は未設定（再取得ボタンなし）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
