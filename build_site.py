"""
used_term_select_full.png から GitHub Pages 用の index.html を生成する。
CI では main.py 成功後にこのスクリプトを実行する。

環境変数:
  GAS_TRIGGER_URL … GAS ウェブアプリの実行 URL（?token= 付き完全 URL）。
                    設定時のみ「スクショの再取得を依頼」ボタンを出力する。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

IMAGE_NAME = "used_term_select_full.png"
JST = timezone(timedelta(hours=9))


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    img = repo_root / IMAGE_NAME
    if not img.is_file():
        print(f"error: {img} が見つかりません", file=sys.stderr)
        return 1

    out_dir = repo_root / "site"
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(img, out_dir / IMAGE_NAME)

    now_jst = datetime.now(timezone.utc).astimezone(JST)

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
    <strong>表示を更新</strong> はこのページだけ再読み込みします。<strong>スクショの再取得を依頼</strong> は別タブで Google Apps Script に接続し、
    （トークンと間隔チェックが通れば）このリポジトリの GitHub Actions を起動します。同じ処理は<strong>およそ 10 分に 1 回まで</strong>に制限しています。
    トークン付き URL はページの HTML に埋め込まれるため、「URL を共有した時点である程度は再現されます」ので、問題があれば GAS と GitHub の両方でトークンを更新してください。
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
    body {{ font-family: system-ui, sans-serif; margin: 1rem auto; max-width: 1200px; padding: 0 0.75rem; line-height: 1.5; }}
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
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="time-main">スクショ取得日時（日本時間・JST）: {time_jst}</p>
{buttons_block}
{note_block}
{script_handlers}
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
