"""
ahamo.com リユース製品一覧ページへ Playwright でアクセスするCLI。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

USED_PRODUCTS_URL = "https://ahamo.com/products/used/"
# リユース品一覧ページの「申し込み」ボタン
APPLY_SELECTOR = (
    'a.a-button.a-button--primary[href="/store/pub/application/type/"]'
)
APPLY_CLICK_DELAY_MS = 1000
# 「契約タイプ選択」などで電話番号を維持するラジオ
KEEP_PHONE_LABEL = "今の電話番号をそのまま使う"
KEEP_PHONE_OPTION_DELAY_MS = 2000
# 契約者タイプ「docomo以外」（name="contract" value="0"）
NON_DOCOMO_CONTRACT_LABEL_SELECTOR = (
    'label.a-radio.js-change-link:has(input[name="contract"][value="0"])'
)
# 端末区分「買う」（name="terminal" value="1"）
TERMINAL_BUY_LABEL_SELECTOR = (
    'label.a-radio.js-change-link:has(input[name="terminal"][value="1"])'
)
# フォーム送信「次へ」（primary の submit）
NEXT_STEP_BUTTON_SELECTOR = 'button[type="submit"].a-button.a-button--primary'
# 準備チェックリスト完了後「準備OK」
READY_OK_SELECTOR = (
    'a.a-button.a-button--primary[href="/store/pub/application/terminal/term-type-select.html"]'
)
# 「スマホの選択」iPhone カード
IPHONE_TERMINAL_SELECTOR = (
    'a.m-product-category-link-card.m-product-category-link-card--title-en'
    '[href="/store/pub/application/terminal/?iphone=1"]'
)
# iPhone の端末状態「リユース品を見る」
VIEW_REUSED_SELECTOR = (
    'a.a-button.a-button--lightgray'
    '[href="/store/pub/application/terminal/used-term-select.html"]'
)
USED_TERM_SCREENSHOT_DEFAULT = Path(__file__).resolve().parent / "used_term_select_full.png"
USED_TERM_INVENTORY_LINES_DEFAULT = Path(__file__).resolve().parent / "used_term_inventory_lines.txt"

# Windows + Chrome とみなさせる既定 UA（古い UA だとサイトが別レイアウトにすることがある）
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)


def _chrome_stable_version_from_cf_json(data: dict) -> str | None:
    stable = ((data.get("channels") or {}).get("Stable")) or {}
    ver = stable.get("version")
    return ver if isinstance(ver, str) and ver else None


def fetch_latest_stable_chrome_user_agent(timeout_sec: float = 12.0) -> str | None:
    """chrome-for-testing の last-known-good から Stable バージョンを取り Windows Chrome UA にする。"""
    url = (
        "https://googlechromelabs.github.io/chrome-for-testing/"
        "last-known-good-versions.json"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
        return None
    ver = _chrome_stable_version_from_cf_json(data) if isinstance(data, dict) else None
    if not ver:
        return None
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{ver} Safari/537.36"
    )


def _resolve_user_agent(cli_value: str | None) -> str:
    """cli_value が None のとき既定 UA。空文字なら Stable 最新相当を取得。その他はそのまま。"""
    if cli_value is None:
        return DEFAULT_USER_AGENT
    if cli_value == "":
        fetched = fetch_latest_stable_chrome_user_agent()
        if fetched:
            print(f"[UA] Stable 最新を取得しました: {fetched}")
            return fetched
        print("[UA] ネットワーク等で取得できず、埋め込み既定 UA にフォールバックします", file=sys.stderr)
        return DEFAULT_USER_AGENT
    stripped = cli_value.strip()
    return stripped if stripped else DEFAULT_USER_AGENT


def scrape_used_term_inventory_summary(page: Page, *, timeout_ms: float) -> list[str]:
    """m-phone-thumbnail-card 単位で【機種】【ランク】【在庫】の一覧行を組み立てる。"""
    to = int(timeout_ms)
    lines: list[str] = []

    cards = page.locator("div.m-phone-thumbnail-card")
    count = cards.count()
    if count == 0:
        print("[在庫一覧] div.m-phone-thumbnail-card が 0 件です", file=sys.stderr)
        return lines

    for i in range(count):
        c = cards.nth(i)
        title = (
            c.locator("span.m-phone-thumbnail-card__title").first.inner_text(timeout=to).strip()
        )
        rank_txt = ""
        rank_loc = c.locator("span.m-phone-thumbnail-card__rank")
        if rank_loc.count() > 0:
            rank_txt = rank_loc.first.inner_text(timeout=to).strip()
        rank_part = f"ランク：{rank_txt}" if rank_txt else "ランク：（表示なし）"

        footer = c.locator(".m-phone-thumbnail-card__footer")
        footer_text = ""
        label_loc = footer.locator(".a-button__label")
        if label_loc.count() > 0:
            footer_text = label_loc.first.inner_text(timeout=to).strip()

        btn_disabled = footer.locator("a.a-button--disabled").count() > 0

        shipping_tag = c.locator(".m-phone-thumbnail-card__shipping .a-tag")
        shipping_hint = ""
        if shipping_tag.count() > 0:
            shipping_hint = shipping_tag.first.inner_text(timeout=to).strip()

        if footer_text == "在庫なし" or btn_disabled:
            stock = "在庫なし"
        elif "スマホを選ぶ" in footer_text:
            stock = "在庫あり"
        elif "在庫なし" in shipping_hint:
            stock = "在庫なし"
        elif footer_text:
            stock = footer_text
        else:
            stock = "不明"

        lines.append(f"{title}、{rank_part}、{stock}")

    return lines


def _ensure_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Playwright で ahamo リユース製品一覧を開く")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="ヘッドレス（画面非表示）で実行",
    )
    parser.add_argument(
        "--slow-mo",
        type=float,
        default=0,
        metavar="MS",
        help="各操作の間隔ミリ秒（デバッグ用）",
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        default=USED_TERM_SCREENSHOT_DEFAULT,
        metavar="PATH",
        help=(
            "「リユース品の選択」ページの全体スクショをPNGで保存するパス。"
            " 省略時は main.py と同じフォルダへ used_term_select_full.png を書き込みます"
        ),
    )
    parser.add_argument(
        "--inventory-lines-file",
        type=Path,
        default=USED_TERM_INVENTORY_LINES_DEFAULT,
        metavar="PATH",
        help="機種×ランク×在庫のサマリー行テキスト（build_site が HTML に読み込み）を書き込むパス",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60_000,
        metavar="MS",
        help="ナビゲーションのタイムアウト（ミリ秒）",
    )
    parser.add_argument(
        "--user-agent",
        nargs="?",
        const="",
        default=None,
        metavar="STRING",
        help=(
            "User-Agent。"
            " --user-agent のみ書いたときは Chrome Stable の公開バージョンから最新相当の UA を自動取得。"
            " フラグ省略時は埋め込み既定値。"
            " 続けて文字列を書けばそのまま利用"
        ),
    )
    parser.add_argument(
        "--chrome-channel",
        action="store_true",
        help=(
            "同梱の Chromium ではなく、PC にインストールされている Google Chrome で起動"
            " （普段見ている表示に近付けたいとき用）"
        ),
    )
    args = parser.parse_args()

    try:
        with sync_playwright() as p:
            launch_kw: dict[str, object] = {
                "headless": args.headless,
                "slow_mo": args.slow_mo,
            }
            if args.chrome_channel:
                launch_kw["channel"] = "chrome"
            browser = p.chromium.launch(**launch_kw)

            user_agent = _resolve_user_agent(args.user_agent)
            context = browser.new_context(
                locale="ja-JP",
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()
            page.goto(USED_PRODUCTS_URL, wait_until="domcontentloaded", timeout=args.timeout)

            print(f"[一覧] title: {page.title()}")
            print(f"[一覧] url: {page.url}")

            apply_link = page.locator(APPLY_SELECTOR)
            apply_link.wait_for(state="visible", timeout=args.timeout)
            page.wait_for_timeout(APPLY_CLICK_DELAY_MS)
            apply_link.click(timeout=args.timeout)
            page.wait_for_load_state("domcontentloaded", timeout=args.timeout)

            print(f"[申込画面] title: {page.title()}")
            print(f"[申込画面] url: {page.url}")

            phone_radio = page.locator(".a-radio__body").filter(has_text=KEEP_PHONE_LABEL)
            phone_radio.wait_for(state="visible", timeout=args.timeout)
            page.wait_for_timeout(KEEP_PHONE_OPTION_DELAY_MS)
            phone_radio.click(timeout=args.timeout)

            print(f"[電話番号の使い方] 「{KEEP_PHONE_LABEL}」を選択しました")

            non_docomo = page.locator(NON_DOCOMO_CONTRACT_LABEL_SELECTOR)
            non_docomo.wait_for(state="visible", timeout=args.timeout)
            non_docomo.click(timeout=args.timeout)

            print('[契約タイプ] 「docomo以外」を選択しました')

            buy_terminal = page.locator(TERMINAL_BUY_LABEL_SELECTOR)
            buy_terminal.wait_for(state="visible", timeout=args.timeout)
            buy_terminal.click(timeout=args.timeout)

            print('[端末] 「買う」を選択しました')

            next_btn = page.locator(NEXT_STEP_BUTTON_SELECTOR).filter(has_text="次へ")
            next_btn.wait_for(state="visible", timeout=args.timeout)
            next_btn.click(timeout=args.timeout)
            page.wait_for_load_state("domcontentloaded", timeout=args.timeout)

            print(f"[次へ後] title: {page.title()}")
            print(f"[次へ後] url: {page.url}")

            ready_ok = page.locator(READY_OK_SELECTOR).filter(has_text="準備OK")
            ready_ok.scroll_into_view_if_needed(timeout=args.timeout)
            ready_ok.wait_for(state="visible", timeout=args.timeout)
            ready_ok.click(timeout=args.timeout)
            page.wait_for_load_state("domcontentloaded", timeout=args.timeout)

            print(f"[準備OK後] title: {page.title()}")
            print(f"[準備OK後] url: {page.url}")

            iphone_card = page.locator(IPHONE_TERMINAL_SELECTOR)
            iphone_card.scroll_into_view_if_needed(timeout=args.timeout)
            iphone_card.wait_for(state="visible", timeout=args.timeout)
            iphone_card.click(timeout=args.timeout)
            page.wait_for_load_state("domcontentloaded", timeout=args.timeout)

            print(f"[iPhone選択後] title: {page.title()}")
            print(f"[iPhone選択後] url: {page.url}")

            view_reused = page.locator(VIEW_REUSED_SELECTOR).filter(has_text="リユース品を見る")
            view_reused.scroll_into_view_if_needed(timeout=args.timeout)
            view_reused.wait_for(state="visible", timeout=args.timeout)
            view_reused.click(timeout=args.timeout)
            page.wait_for_load_state("domcontentloaded", timeout=args.timeout)

            print(f"[リユース品を見る後] title: {page.title()}")
            print(f"[リユース品を見る後] url: {page.url}")

            page.wait_for_timeout(2000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(700)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(400)

            inv_lines = scrape_used_term_inventory_summary(page, timeout_ms=args.timeout)
            args.inventory_lines_file.parent.mkdir(parents=True, exist_ok=True)
            args.inventory_lines_file.write_text(
                "\n".join(inv_lines) + ("\n" if inv_lines else ""),
                encoding="utf-8",
            )
            print(f"[在庫一覧] {len(inv_lines)} 件 → {args.inventory_lines_file.resolve()}")
            for line in inv_lines:
                print(f"    {line}")

            print("[ここでスクショを撮る]")

            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(args.screenshot), full_page=True)
            print(f"[スクショ] ページ全体 → {args.screenshot.resolve()}")

            #if not args.headless:
            #    input("ブラウザを確認したら Enter で終了: ")

            context.close()
            browser.close()
    except KeyboardInterrupt:
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())
