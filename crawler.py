from __future__ import annotations

import random
import re
from typing import Any

from playwright.sync_api import Page, sync_playwright
from playwright._impl._errors import TargetClosedError
from playwright_stealth import Stealth

_stealth = Stealth()

PRODUCT_LINK_SELECTOR = 'a[href*="-i."], a[href*="/product/"]'
PROFILE_DIR = "shopee_profile"
SHOPEE_HOME = "https://shopee.vn"

_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
]
_CONTEXT_OPTS = {
    "viewport": {"width": 1366, "height": 900},
    "locale": "vi-VN",
    "timezone_id": "Asia/Bangkok",
}
_STEALTH_SCRIPT = (
    "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
)


def _open_persistent_context(p: Any, headless: bool) -> Any:
    context = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=headless,
        args=_LAUNCH_ARGS,
        **_CONTEXT_OPTS,
    )
    context.add_init_script(_STEALTH_SCRIPT)
    return context


def setup_session() -> None:
    """Open browser for user to browse Shopee and build up a real session/cookies."""
    print("Opening browser to set up Shopee session...")
    print("1. Browse shopee.vn normally (scroll, click products, etc.)")
    print("2. You do NOT need to log in — just browse as a normal visitor")
    print("3. When done, press ENTER in this terminal to save and close\n")

    with sync_playwright() as p:
        context = _open_persistent_context(p, headless=False)
        page = context.new_page()
        _stealth.use_sync(page)
        page.goto(SHOPEE_HOME, wait_until="domcontentloaded", timeout=60_000)
        try:
            input(">>> Press ENTER when done browsing to save session and exit...")
        except EOFError:
            pass
        finally:
            try:
                context.close()
            except Exception:
                pass

    print("Session saved to shopee_profile/. You can now run the crawler.")


def crawl_category(
    url: str,
    limit: int = 50,
    *,
    headless: bool = False,
    manual_bypass: bool = True,
    max_scrolls: int = 30,
    scroll_pause: float = 1.5,
    timeout_ms: int = 60_000,
) -> list[dict[str, Any]]:
    if limit < 1:
        return []

    with sync_playwright() as p:
        context = _open_persistent_context(p, headless=headless)
        page = context.new_page()
        _stealth.use_sync(page)
        try:
            if not _load_page(page, url, timeout_ms, manual_bypass=manual_bypass):
                return []

            _wait_for_load_idle(page)
            _close_popups(page)
            _wait_for_products(page)

            products = _scroll_and_extract(
                page, limit, max_scrolls, scroll_pause, manual_bypass=manual_bypass
            )
            _enrich_missing_details(context, products)
            return products[:limit]
        except TargetClosedError:
            print("\n[ERROR] Browser closed during crawl. Returning collected products.")
            return []
        finally:
            try:
                context.close()
            except Exception:
                pass


def _load_page(
    page: Page,
    url: str,
    timeout_ms: int,
    *,
    manual_bypass: bool = True,
) -> bool:
    for attempt in range(3):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(random.randint(2000, 4000))
            if not _is_blocked(page):
                return True
        except Exception:
            pass

        if _is_blocked(page) and manual_bypass:
            print(
                f"\n[CAPTCHA] Shopee block detected (attempt {attempt + 1}/3)."
                "\nSolve the CAPTCHA in the browser window, then press ENTER here to continue..."
            )
            try:
                input()
            except EOFError:
                pass
            page.wait_for_timeout(2000)
            if not _is_blocked(page):
                return True

        page.wait_for_timeout(random.randint(3000, 6000))
    return False


def _is_blocked(page: Page) -> bool:
    blocked = ["/verify/traffic/", "captcha", "robot"]
    return any(k in page.url.lower() for k in blocked)


def _scroll_and_extract(
    page: Page,
    limit: int,
    max_scrolls: int,
    scroll_pause: float,
    *,
    manual_bypass: bool = True,
) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    seen_links: set[str] = set()
    previous_count = 0
    stalled_rounds = 0

    for scroll_num in range(max_scrolls + 1):
        # Check for mid-scroll CAPTCHA
        if _is_blocked(page):
            if manual_bypass:
                print(
                    f"\n[CAPTCHA] Block detected during scroll {scroll_num}."
                    "\nSolve the CAPTCHA in the browser, then press ENTER to continue..."
                    "\n(or type 'stop' to save what was collected so far)"
                )
                try:
                    answer = input().strip().lower()
                except EOFError:
                    answer = ""
                if answer == "stop":
                    break
                page.wait_for_timeout(2000)
                if _is_blocked(page):
                    print("[CAPTCHA] Still blocked, stopping crawl.")
                    break
            else:
                break

        _wait_for_products(page, timeout_ms=8000)

        for item in _extract_products(page):
            link = item.get("product_link", "")
            if not link or link in seen_links:
                continue
            seen_links.add(link)
            products.append(item)
            if len(products) >= limit:
                return products

        if len(products) == previous_count:
            stalled_rounds += 1
        else:
            stalled_rounds = 0
            previous_count = len(products)

        if stalled_rounds >= 5:
            break

        before_count = _product_link_count(page)
        _scroll_page(page)
        _wait_for_count_to_grow(page, before_count, scroll_pause)
        _wait_for_load_idle(page, timeout_ms=5000)

    return products


def _extract_products(page: Page) -> list[dict[str, Any]]:
    try:
        raw: list[dict[str, Any]] = page.evaluate("""
            () => {
                const anchors = Array.from(document.querySelectorAll('a[href]'));
                const results = [];

                for (const anchor of anchors) {
                    const href = anchor.href || '';
                    if (!href.includes('-i.') && !href.includes('/product/')) continue;

                    const card =
                        anchor.closest('[data-sqe="item"]')
                        || anchor.closest('li')
                        || anchor.parentElement;
                    if (!card) continue;

                    const text = card.innerText || '';
                    const lines = text.split('\\n').map(x => x.trim()).filter(Boolean);

                    let name = '', price = '', sold = '', rating = '', shopType = 'normal';

                    for (const line of lines) {
                        if (!name && line.length > 10 && !line.includes('₫')) name = line;
                        if (!price && (line.includes('₫') || line.includes('đ'))) price = line;
                        if (!sold && (line.toLowerCase().includes('đã bán') || line.toLowerCase().includes('sold'))) sold = line;
                        const rMatch = line.match(/([0-5](?:\\.[0-9])?)/);
                        if (!rating && rMatch) rating = rMatch[1];
                    }

                    if (!name) continue;

                    const mallBadge = card.querySelector('[class*="mall"], [class*="Mall"]');
                    const preferredBadge = card.querySelector('[class*="preferred"], [class*="Preferred"]');
                    if (mallBadge) shopType = 'mall';
                    else if (preferredBadge) shopType = 'preferred';

                    results.push({ name, price, sold_count: sold, rating, product_link: href, shop_type: shopType });
                }

                return results;
            }
        """)
    except Exception:
        return []

    return [
        {
            "name": str(item.get("name", "")),
            "price": str(item.get("price", "")),
            "sold_count": str(item.get("sold_count", "")),
            "rating": str(item.get("rating", "")),
            "product_link": str(item.get("product_link", "")),
            "shop_type": str(item.get("shop_type", "normal")),
        }
        for item in raw
    ]


def _enrich_missing_details(context: Any, products: list[dict[str, Any]]) -> None:
    detail_page = context.new_page()
    try:
        for product in products:
            if product.get("sold_count") and product.get("rating"):
                continue
            link = product.get("product_link", "")
            if not link:
                continue
            details = _crawl_detail(detail_page, link)
            if details.get("sold_count") and not product.get("sold_count"):
                product["sold_count"] = details["sold_count"]
            if details.get("rating") and not product.get("rating"):
                product["rating"] = details["rating"]
    finally:
        detail_page.close()


def _crawl_detail(page: Page, url: str) -> dict[str, str]:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(random.randint(1500, 3000))
        text = page.locator("body").inner_text(timeout=5000)
    except Exception:
        return {}
    return {
        "sold_count": _extract_sold(text),
        "rating": _extract_rating(text),
    }


def _extract_sold(text: str) -> str:
    patterns = [
        r"(?:Đã\s*Bán|Sold)\s*([0-9.,]+\s*[kKmM]?\+?)",
        r"([0-9.,]+\s*[kKmM]?\+?)\s*(?:đã\s*bán|sold)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return ""


def _extract_rating(text: str) -> str:
    match = re.search(r"([0-5](?:[.,][0-9]+)?)", text or "")
    if not match:
        return ""
    return match.group(1).replace(",", ".")


def _wait_for_products(page: Page, timeout_ms: int = 15000) -> None:
    try:
        page.wait_for_selector(PRODUCT_LINK_SELECTOR, timeout=timeout_ms, state="attached")
    except Exception:
        pass


def _wait_for_load_idle(page: Page, timeout_ms: int = 15000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass


def _product_link_count(page: Page) -> int:
    try:
        return int(page.locator(PRODUCT_LINK_SELECTOR).count())
    except Exception:
        return 0


def _scroll_page(page: Page) -> None:
    try:
        page.mouse.wheel(0, random.randint(1200, 2200))
        page.wait_for_timeout(random.randint(1000, 2500))
    except Exception:
        try:
            page.evaluate("window.scrollBy(0, Math.floor(window.innerHeight * 1.8))")
        except Exception:
            pass


def _wait_for_count_to_grow(page: Page, before_count: int, scroll_pause: float) -> None:
    timeout_ms = max(int(scroll_pause * 1000), 1000)
    try:
        page.wait_for_function(
            """
            (before) => {
                const sel = 'a[href*="-i."], a[href*="/product/"]';
                return document.querySelectorAll(sel).length > before;
            }
            """,
            arg=before_count,
            timeout=timeout_ms,
        )
    except Exception:
        page.wait_for_timeout(timeout_ms)


def _close_popups(page: Page) -> None:
    selectors = [
        'button:has-text("OK")',
        'button:has-text("Accept")',
        'button[aria-label="Close"]',
        '.shopee-popup__close-btn',
        '.shopee-modal__close',
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=800):
                locator.click(timeout=1000)
                page.wait_for_timeout(500)
        except Exception:
            continue
