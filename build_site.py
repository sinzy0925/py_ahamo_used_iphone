"""
used_term_select_full.png から GitHub Pages 用の index.html を生成する。
CI では main.py 成功後にこのスクリプトを実行する。
"""

from __future__ import annotations

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

    event = os.environ.get("GITHUB_EVENT_NAME", "local")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_url = f"{server_url}/{repo}/actions/runs/{run_id}" if repo and run_id else ""

    title = "ahamo リユース品の選択（スクショ）"

    trigger_ja = {
        "workflow_dispatch": "手動実行",
        "schedule": "スケジュール（定期）",
        "local": "ローカル",
    }.get(event, event)

    run_link = (
        f'<p><a href="{run_url}" rel="noopener">GitHub Actions 実行ログ</a></p>'
        if run_url
        else ""
    )

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
    .meta {{ color: #444; font-size: 0.95rem; }}
    img {{ max-width: 100%; height: auto; border: 1px solid #ddd; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="time-main">スクショ取得日時（日本時間・JST）: {time_jst}</p>
  <p class="meta">実行のしかた: {trigger_ja}</p>
  {run_link}
  <p><img src="{IMAGE_NAME}" alt="リユース品の選択 ページ全体"></p>
</body>
</html>
"""
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"site -> {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
