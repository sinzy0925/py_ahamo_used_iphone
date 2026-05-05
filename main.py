"""
ahamo.com 製品ページへ Playwright でアクセスするCLI。

- used: リユース製品一覧から申込フローへ進み、リユース端末選択ページをスクレイプ
- new-iphone: 新品 iPhone 紹介ページから同様の申込フローへ進み、新品 iPhone 一覧の在庫フラグを取得
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

USED_PRODUCTS_URL = "https://ahamo.com/products/used/"
NEW_IPHONE_PRODUCTS_URL = "https://ahamo.com/products/iphone/"
# 申込導線の各画面遷移後の待機（ミリ秒）— new-iphone フロー用
NEW_FLOW_NAV_POST_WAIT_MS = 2000
NEW_FLOW_START_WAIT_MS = 2000
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
NEW_IPHONE_LIST_SCREENSHOT_DEFAULT = Path(__file__).resolve().parent / "new_iphone_list_full.png"
NEW_IPHONE_INVENTORY_LINES_DEFAULT = Path(__file__).resolve().parent / "new_iphone_inventory_lines.txt"

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


def _used_term_storage_to_gb(value_txt: str, unit_txt: str) -> int:
    """比較用に GB 換算（TB は 1024GB とみなす）。"""
    digits = re.sub(r"[^\d]", "", value_txt)
    v = int(digits) if digits else 0
    u = unit_txt.strip().upper()
    if u == "TB":
        return v * 1024
    return v


def _used_term_price_to_int(amount_inner_text: str) -> int:
    """「137,500」形式から整数円。"""
    digits = re.sub(r"[^\d]", "", amount_inner_text)
    return int(digits) if digits else 0


def _pick_min_storage_min_price_option(
    card, *, timeout_ms: int
) -> tuple[str, str]:
    """
    カード内の a-device-price-thumbnail-radio から、
    ストレージ容量が最小のSKUを選び、同容量で価格が最安のものを採用。
    返り値: (「128GB」表示, 「137,500円～」表示)
    """
    to = int(timeout_ms)
    labels = card.locator(".m-phone-thumbnail-card__body label.a-device-price-thumbnail-radio")
    n = labels.count()
    options: list[tuple[int, int, str, str]] = []
    for j in range(n):
        lab = labels.nth(j)
        sv_loc = lab.locator(".a-device-price-thumbnail__storage-value")
        if sv_loc.count() == 0:
            continue
        value_txt = sv_loc.first.inner_text(timeout=to).strip()
        su_loc = lab.locator(".a-device-price-thumbnail__storage-unit")
        unit_txt = su_loc.first.inner_text(timeout=to).strip() if su_loc.count() else "GB"
        gb = _used_term_storage_to_gb(value_txt, unit_txt)
        amt_loc = lab.locator(".a-device-price-thumbnail__price .a-price-amount span")
        if amt_loc.count() == 0:
            continue
        price_raw = amt_loc.first.inner_text(timeout=to).strip()
        price_i = _used_term_price_to_int(price_raw)
        storage_disp = f"{value_txt}{unit_txt}"
        price_disp = f"{price_raw}円～"
        options.append((gb, price_i, storage_disp, price_disp))

    if not options:
        return "", ""

    min_gb = min(o[0] for o in options)
    tier = [o for o in options if o[0] == min_gb]
    best = min(tier, key=lambda o: o[1])
    return best[2], best[3]


def scrape_used_term_inventory_summary(page: Page, *, timeout_ms: float) -> list[str]:
    """m-phone-thumbnail-card 単位で【機種】【ランク】【在庫】【最小ストレージ】【最安支払総額～】の一覧行を組み立てる。"""
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

        storage_disp, price_disp = _pick_min_storage_min_price_option(c, timeout_ms=to)
        lines.append(f"{title}、{rank_part}、{stock}、{storage_disp}、{price_disp}")

    return lines


def _stock_label_from_sale_flags(
    flag_str: str | None,
    variants_str: str | None,
) -> str:
    """data-sale-stock-flag / variants から在庫ラベル（1・2=あり、3=なし）。"""
    if variants_str:
        parts = [p.strip() for p in variants_str.split(",") if p.strip()]
        if parts:
            if all(p == "3" for p in parts):
                return "在庫なし"
            if any(p in ("1", "2") for p in parts):
                return "在庫あり"
    if flag_str == "3":
        return "在庫なし"
    if flag_str in ("1", "2"):
        return "在庫あり"
    return "不明"


def _new_iphone_price_label_to_gb_and_disp(label_text: str) -> tuple[int, str]:
    """「256GBの場合」→ (比較用GB, 「256GB」表示)。パース不能なら大きいGBと原文。"""
    t = re.sub(r"の場合\s*$", "", label_text.strip())
    m = re.match(r"^(\d+)\s*(GB|TB)$", t.replace(" ", ""), re.I)
    if m:
        v = int(m.group(1))
        u = m.group(2).upper()
        gb = v * 1024 if u == "TB" else v
        return gb, f"{v}{u}"
    return 10**9, t


def _pick_min_storage_price_from_new_iphone_card(card, *, timeout_ms: int) -> tuple[str, str]:
    """
    カード内の m-product-card-list__price-content ごとに容量・支払総額を拾い、
    最小容量のうえで最安価の1件の (ストレージ表記, 価格表記) を返す。
    """
    to = int(timeout_ms)
    blocks = card.locator(".m-product-card-list__figure .m-product-card-list__price-content")
    n = blocks.count()
    options: list[tuple[int, int, str, str]] = []
    for i in range(n):
        b = blocks.nth(i)
        lbl_loc = b.locator(".m-product-card-list__price-label")
        amt_loc = b.locator(".m-product-card-list__price .a-price-amount span").first
        if lbl_loc.count() == 0 or amt_loc.count() == 0:
            continue
        raw_lbl = lbl_loc.first.inner_text(timeout=to).strip()
        gb, storage_disp = _new_iphone_price_label_to_gb_and_disp(raw_lbl)
        num_txt = amt_loc.inner_text(timeout=to).strip()
        price_i = _used_term_price_to_int(num_txt)
        price_disp = f"{num_txt}円"
        options.append((gb, price_i, storage_disp, price_disp))

    if not options:
        return "", ""

    min_gb = min(o[0] for o in options)
    tier = [o for o in options if o[0] == min_gb]
    best = min(tier, key=lambda o: o[1])
    return best[2], best[3]


def scrape_new_iphone_product_list_inventory(page: Page, *, timeout_ms: float) -> list[str]:
    """m-product-card-list のカード単位で機種・在庫・代表ストレージ・価格を一覧化（タブ区切り4列）。"""
    to = int(timeout_ms)
    lines: list[str] = []

    wrappers = page.locator("div.m-product-card-list__item-wrapper")
    count = wrappers.count()
    if count == 0:
        print(
            "[新品iPhone一覧] div.m-product-card-list__item-wrapper が 0 件です",
            file=sys.stderr,
        )
        return lines

    for i in range(count):
        w = wrappers.nth(i)
        flag = w.get_attribute("data-sale-stock-flag")
        variants = w.get_attribute("data-sale-stock-flag-variants")
        name_loc = w.locator("p.m-product-card-list__name").first
        name = name_loc.inner_text(timeout=to).strip()
        stock = _stock_label_from_sale_flags(flag, variants)
        storage_disp, price_disp = _pick_min_storage_price_from_new_iphone_card(w, timeout_ms=to)
        lines.append(f"{name}\t{stock}\t{storage_disp}\t{price_disp}")

    return lines


def _apply_link_and_contract_wizard(
    page: Page,
    *,
    timeout_ms: float,
    pre_apply_wait_ms: int = 0,
    phone_option_delay_ms: int = 0,
    post_navigation_wait_ms: int = 0,
) -> None:
    """製品ページの「申し込み」から iPhone カテゴリカード Click まで（共通）。"""
    to = float(timeout_ms)
    if pre_apply_wait_ms:
        page.wait_for_timeout(pre_apply_wait_ms)

    apply_link = page.locator(APPLY_SELECTOR)
    apply_link.wait_for(state="visible", timeout=to)
    apply_link.click(timeout=to)
    page.wait_for_load_state("domcontentloaded", timeout=to)
    if post_navigation_wait_ms:
        page.wait_for_timeout(post_navigation_wait_ms)

    print(f"[申込画面] title: {page.title()}")
    print(f"[申込画面] url: {page.url}")

    phone_radio = page.locator(".a-radio__body").filter(has_text=KEEP_PHONE_LABEL)
    phone_radio.wait_for(state="visible", timeout=to)
    if phone_option_delay_ms:
        page.wait_for_timeout(phone_option_delay_ms)
    phone_radio.click(timeout=to)

    print(f"[電話番号の使い方] 「{KEEP_PHONE_LABEL}」を選択しました")

    non_docomo = page.locator(NON_DOCOMO_CONTRACT_LABEL_SELECTOR)
    non_docomo.wait_for(state="visible", timeout=to)
    non_docomo.click(timeout=to)

    print('[契約タイプ] 「docomo以外」を選択しました')

    buy_terminal = page.locator(TERMINAL_BUY_LABEL_SELECTOR)
    buy_terminal.wait_for(state="visible", timeout=to)
    buy_terminal.click(timeout=to)

    print('[端末] 「買う」を選択しました')

    next_btn = page.locator(NEXT_STEP_BUTTON_SELECTOR).filter(has_text="次へ")
    next_btn.wait_for(state="visible", timeout=to)
    next_btn.click(timeout=to)
    page.wait_for_load_state("domcontentloaded", timeout=to)
    if post_navigation_wait_ms:
        page.wait_for_timeout(post_navigation_wait_ms)

    print(f"[次へ後] title: {page.title()}")
    print(f"[次へ後] url: {page.url}")

    ready_ok = page.locator(READY_OK_SELECTOR).filter(has_text="準備OK")
    ready_ok.scroll_into_view_if_needed(timeout=to)
    ready_ok.wait_for(state="visible", timeout=to)
    ready_ok.click(timeout=to)
    page.wait_for_load_state("domcontentloaded", timeout=to)
    if post_navigation_wait_ms:
        page.wait_for_timeout(post_navigation_wait_ms)

    print(f"[準備OK後] title: {page.title()}")
    print(f"[準備OK後] url: {page.url}")

    iphone_card = page.locator(IPHONE_TERMINAL_SELECTOR)
    iphone_card.scroll_into_view_if_needed(timeout=to)
    iphone_card.wait_for(state="visible", timeout=to)
    iphone_card.click(timeout=to)
    page.wait_for_load_state("domcontentloaded", timeout=to)
    if post_navigation_wait_ms:
        page.wait_for_timeout(post_navigation_wait_ms)

    print(f"[iPhone選択後] title: {page.title()}")
    print(f"[iPhone選択後] url: {page.url}")


def _ensure_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="Playwright で ahamo 製品ページから申込フローを開き在庫を取得します"
    )
    parser.add_argument(
        "--flow",
        choices=("used", "new-iphone"),
        default="used",
        help=(
            "used: リユース一覧からリユース端末選択まで。"
            " new-iphone: 新品iPhone紹介ページから新品iPhone一覧（data-sale-stock-flag）まで"
        ),
    )
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
        default=None,
        metavar="PATH",
        help=(
            "ページ全体スクショのPNGパス。"
            " 省略時はフローに応じて used_term_select_full.png または new_iphone_list_full.png"
        ),
    )
    parser.add_argument(
        "--inventory-lines-file",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "在庫サマリー行テキストの出力パス。"
            " 省略時は used_term_inventory_lines.txt または new_iphone_inventory_lines.txt"
        ),
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

    if args.screenshot is None:
        args.screenshot = (
            USED_TERM_SCREENSHOT_DEFAULT
            if args.flow == "used"
            else NEW_IPHONE_LIST_SCREENSHOT_DEFAULT
        )
    if args.inventory_lines_file is None:
        args.inventory_lines_file = (
            USED_TERM_INVENTORY_LINES_DEFAULT
            if args.flow == "used"
            else NEW_IPHONE_INVENTORY_LINES_DEFAULT
        )

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
            start = USED_PRODUCTS_URL if args.flow == "used" else NEW_IPHONE_PRODUCTS_URL
            page.goto(start, wait_until="domcontentloaded", timeout=args.timeout)

            print(f"[一覧] title: {page.title()}")
            print(f"[一覧] url: {page.url}")

            if args.flow == "used":
                _apply_link_and_contract_wizard(
                    page,
                    timeout_ms=args.timeout,
                    pre_apply_wait_ms=APPLY_CLICK_DELAY_MS,
                    phone_option_delay_ms=KEEP_PHONE_OPTION_DELAY_MS,
                    post_navigation_wait_ms=0,
                )
            else:
                page.wait_for_timeout(NEW_FLOW_START_WAIT_MS)
                _apply_link_and_contract_wizard(
                    page,
                    timeout_ms=args.timeout,
                    pre_apply_wait_ms=0,
                    phone_option_delay_ms=0,
                    post_navigation_wait_ms=NEW_FLOW_NAV_POST_WAIT_MS,
                )

            if args.flow == "used":
                view_reused = page.locator(VIEW_REUSED_SELECTOR).filter(
                    has_text="リユース品を見る"
                )
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
                log_tag = "[在庫一覧]"
            else:
                page.wait_for_timeout(NEW_FLOW_NAV_POST_WAIT_MS)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(700)
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(400)

                inv_lines = scrape_new_iphone_product_list_inventory(
                    page, timeout_ms=args.timeout
                )
                log_tag = "[新品iPhone一覧]"

            args.inventory_lines_file.parent.mkdir(parents=True, exist_ok=True)
            args.inventory_lines_file.write_text(
                "\n".join(inv_lines) + ("\n" if inv_lines else ""),
                encoding="utf-8",
            )
            print(f"{log_tag} {len(inv_lines)} 件 → {args.inventory_lines_file.resolve()}")
            for line in inv_lines:
                print(f"    {line}")

            print("[スクショを撮る]")

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
