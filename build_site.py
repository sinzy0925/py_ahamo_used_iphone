"""
used_term_select_full.png から GitHub Pages 用の index.html を生成する。
CI では main.py 成功後にこのスクリプトを実行する。
"""

from __future__ import annotations

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

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1rem auto; max-width: 1200px; padding: 0 0.75rem; line-height: 1.5; }}
    .time-main {{ font-size: 1.15rem; font-weight: 600; color: #111; margin: 0.5rem 0 1rem; }}
    .note {{ font-size: 0.88rem; color: #555; margin: 0.85rem 0 1.25rem; line-height: 1.6; max-width: 42em; }}
    img {{ max-width: 100%; height: auto; border: 1px solid #ddd; }}
    .btn {{
      font-size: 1rem;
      padding: 0.55rem 1.35rem;
      border: none;
      border-radius: 6px;
      background: #0d9488;
      color: #fff;
      cursor: pointer;
      font-weight: 600;
    }}
    .btn:hover {{ background: #0f766e; }}
    .btn:focus-visible {{ outline: 2px solid #115e59; outline-offset: 2px; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="time-main">スクショ取得日時（日本時間・JST）: {time_jst}</p>
  <p><button type="button" class="btn" id="check-stock">在庫状況確認</button></p>
  <p class="note">
    このボタンは<strong>ページを再読み込みし、現在デプロイされている最新のスクショを表示し直します</strong>（キャッシュを避けるクエリパラメータを付けることがあります）。
    「新しくスクショを撮って公開する」処理はサーバー側の GitHub Actions で動きます。その API をすべての閲覧者から無条件に叩けるようにするとトークンの漏えいや不正実行のおそれがあるので、このような静的サイトだけでは<strong>閲覧者のボタンから Actions は起動しません</strong>。再取得には定期実行や、リポジトリで権限のある方の Actions による手動実行が必要になります。
  </p>
  <script>
    document.getElementById("check-stock").addEventListener("click", function () {{
      var u = new URL(window.location.href);
      u.searchParams.set("v", String(Date.now()));
      window.location.replace(u.toString());
    }});
  </script>
  <p><img src="{IMAGE_NAME}?v={now_jst.timestamp():.0f}" alt="リユース品の選択 ページ全体"></p>
</body>
</html>
"""
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"site -> {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
