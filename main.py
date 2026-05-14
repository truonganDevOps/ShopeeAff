from __future__ import annotations

import json
import os
import sys
from typing import Any

from crawler import crawl_category, setup_session
from exporters import export_csv, export_excel, export_json
from filters import filter_products

CONFIG_FILE = "config.json"


def load_config(path: str = CONFIG_FILE) -> dict[str, Any]:
    if not os.path.exists(path):
        print(f"Config file not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def merge_products(
    existing: list[dict[str, Any]],
    new: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for product in [*existing, *new]:
        link = product.get("product_link", "")
        if link and link in seen:
            continue
        if link:
            seen.add(link)
        merged.append(product)
    return merged


def main() -> None:
    config = load_config()

    categories: list[dict[str, str]] = config.get("categories", [])
    filter_cfg: dict[str, Any] = config.get("filters", {})
    crawl_cfg: dict[str, Any] = config.get("crawl", {})
    export_cfg: dict[str, Any] = config.get("export", {})

    if not categories:
        print("No categories configured in config.json")
        sys.exit(1)

    all_products: list[dict[str, Any]] = []

    for category in categories:
        name = category.get("name", "")
        url = category.get("url", "")
        if not url:
            continue

        print(f"\nCrawling: {name}")
        print(f"URL: {url}")

        products = crawl_category(
            url,
            limit=crawl_cfg.get("limit_per_category", 50),
            headless=crawl_cfg.get("headless", False),
            manual_bypass=crawl_cfg.get("manual_bypass", True),
            max_scrolls=crawl_cfg.get("max_scrolls", 30),
            scroll_pause=crawl_cfg.get("scroll_pause", 1.5),
            timeout_ms=crawl_cfg.get("timeout_ms", 60_000),
        )

        for product in products:
            product["category"] = name

        filtered = filter_products(
            products,
            min_sold=filter_cfg.get("min_sold", 100),
            min_rating=filter_cfg.get("min_rating", 4.5),
            min_price=filter_cfg.get("min_price", 0),
            max_price=filter_cfg.get("max_price", 0),
            trusted_shop_only=filter_cfg.get("trusted_shop_only", False),
        )

        print(f"  Crawled: {len(products)} | Filtered: {len(filtered)}")

        all_products = merge_products(all_products, filtered)

    print(f"\nTotal products after merge: {len(all_products)}")

    if all_products:
        export_json(all_products, export_cfg.get("json", "products.json"))
        export_csv(all_products, export_cfg.get("csv", "products.csv"))
        export_excel(all_products, export_cfg.get("excel", "products.xlsx"))

    print("\nDone.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--setup":
        setup_session()
    else:
        main()
