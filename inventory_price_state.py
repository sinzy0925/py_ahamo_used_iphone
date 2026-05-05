"""
スクレイプ結果の価格を永続化し、前回からの変動日を記録する。

単純に1個前の txt と比較だけだと価格が安定した次回で変動が消えるため、
JSON で「最後に価格が変わった日」をセル単位で保持する。

main.py 成功後に update_state_after_scrape を呼ぶ。
build_site.py は load_state で読み、表の「価格変動」行と緑表示に使う。

CI などリポジトリにコミットしない場合は、inventory_price_state.json を
GitHub Actions の cache で保持すると実行間で引き継げる。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

STATE_FILENAME = "inventory_price_state.json"
JST = timezone(timedelta(hours=9))


def price_display_to_int(s: str) -> int | None:
    """「137,500円～」「164,197円」などから整数円を取り出す。取れなければ None。"""
    if not s:
        return None
    t = str(s).strip()
    if t in ("---", "—"):
        return None
    digits = re.sub(r"[^\d]", "", t)
    if not digits:
        return None
    return int(digits)


def jst_today_slash() -> str:
    d = datetime.now(JST).date()
    return f"{d.year}/{d.month}/{d.day}"


def default_state() -> dict[str, Any]:
    return {"version": 1, "used": {}, "new_iphone": {}}


def state_path(repo_root: Path) -> Path:
    return repo_root / STATE_FILENAME


def load_state(repo_root: Path) -> dict[str, Any]:
    p = state_path(repo_root)
    if not p.is_file():
        return default_state()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_state()
    if not isinstance(raw, dict):
        return default_state()
    data = default_state()
    data["version"] = raw.get("version", 1)
    u = raw.get("used")
    n = raw.get("new_iphone")
    if isinstance(u, dict):
        data["used"] = u
    if isinstance(n, dict):
        data["new_iphone"] = n
    return data


def save_state(repo_root: Path, data: dict[str, Any]) -> None:
    p = state_path(repo_root)
    p.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def used_cell_changed_at(state: dict[str, Any], title: str, rank: str) -> str | None:
    key = f"{title}\t{rank}"
    cell = (state.get("used") or {}).get(key)
    if not isinstance(cell, dict):
        return None
    d = cell.get("changed_at")
    return d if isinstance(d, str) and d.strip() else None


def new_iphone_cell_changed_at(
    state: dict[str, Any], row_k: str, col_k: str
) -> str | None:
    key = f"{row_k}\t{col_k}"
    cell = (state.get("new_iphone") or {}).get(key)
    if not isinstance(cell, dict):
        return None
    d = cell.get("changed_at")
    return d if isinstance(d, str) and d.strip() else None


def _rebuild_used_section(raw: str, prev: dict[str, Any], today: str) -> dict[str, Any]:
    from build_site import _RANK_KEYS, parse_inventory_record_line

    out: dict[str, Any] = {}
    for line in raw.splitlines():
        t = line.strip()
        if not t:
            continue
        parsed = parse_inventory_record_line(t)
        if not parsed:
            continue
        title, rank_txt, _stock, _storage, price = parsed
        if rank_txt not in _RANK_KEYS:
            continue
        pi = price_display_to_int(price)
        if pi is None:
            continue
        key = f"{title}\t{rank_txt}"
        old = prev.get(key) if isinstance(prev.get(key), dict) else None
        old_p = old.get("price") if old else None
        old_at = old.get("changed_at") if old else None
        if old is None or old_p is None:
            out[key] = {"price": pi, "changed_at": None}
        elif old_p != pi:
            out[key] = {"price": pi, "changed_at": today}
        else:
            out[key] = {"price": pi, "changed_at": old_at}
    return out


def _rebuild_new_section(raw: str, prev: dict[str, Any], today: str) -> dict[str, Any]:
    from build_site import classify_new_iphone_model, parse_new_iphone_inventory_line

    out: dict[str, Any] = {}
    for line in raw.splitlines():
        t = line.strip()
        if not t:
            continue
        parsed = parse_new_iphone_inventory_line(t)
        if not parsed:
            continue
        model, _stock, _storage, price = parsed
        place = classify_new_iphone_model(model)
        if not place:
            continue
        row_k, col_k = place
        pi = price_display_to_int(price)
        if pi is None:
            continue
        key = f"{row_k}\t{col_k}"
        old = prev.get(key) if isinstance(prev.get(key), dict) else None
        old_p = old.get("price") if old else None
        old_at = old.get("changed_at") if old else None
        if old is None or old_p is None:
            out[key] = {"price": pi, "changed_at": None}
        elif old_p != pi:
            out[key] = {"price": pi, "changed_at": today}
        else:
            out[key] = {"price": pi, "changed_at": old_at}
    return out


def update_state_after_scrape(
    flow: Literal["used", "new-iphone"],
    lines_text: str,
    repo_root: Path,
) -> None:
    data = load_state(repo_root)
    today = jst_today_slash()
    if flow == "used":
        data["used"] = _rebuild_used_section(lines_text, data.get("used") or {}, today)
    else:
        data["new_iphone"] = _rebuild_new_section(
            lines_text, data.get("new_iphone") or {}, today
        )
    save_state(repo_root, data)
