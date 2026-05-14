from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


def filter_products(
    products: list[dict[str, Any]],
    min_sold: float = 50,
    min_rating: float = 3.8,
    min_price: float = 0,
    max_price: float = 0,
) -> list[dict[str, Any]]:
    """Score all products and return sorted by score desc (no top-N cut yet)."""
    result = []
    for product in products:
        sold   = _parse_sold(product.get("sold_count", ""))
        rating = _parse_rating(product.get("rating", ""))

        # Hard filters — eliminate obvious junk before scoring
        if sold < min_sold:
            continue
        if 0 < rating < min_rating:
            continue
        if rating == 0 and sold < 200:       # no rating + low sales = unproven
            continue
        price = _parse_price(product.get("price", ""))
        if min_price > 0 and price < min_price:
            continue
        if max_price > 0 and price > max_price:
            continue

        product["score"] = _score(sold, rating, product.get("shop_type", "normal"))
        result.append(product)

    result.sort(key=lambda p: p["score"], reverse=True)
    return result


def top_overall(products: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Top N across all categories (products must already be scored+sorted)."""
    return products[:n] if n > 0 else products


def top_per_category(products: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Top N from each category, then sort result by category name + score desc."""
    counts: dict[str, int] = defaultdict(int)
    picked = []
    for p in products:                       # already sorted by score desc
        cat = p.get("category", "")
        if counts[cat] < n:
            picked.append(p)
            counts[cat] += 1

    picked.sort(key=lambda p: (p.get("category", ""), -p.get("score", 0)))
    return picked


def _score(sold: float, rating: float, shop_type: str) -> int:
    score = 0

    # Sold count: 40 pts — proven demand
    if sold >= 10_000:   score += 40
    elif sold >= 5_000:  score += 32
    elif sold >= 1_000:  score += 24
    elif sold >= 500:    score += 16
    elif sold >= 100:    score += 8

    # Rating: 35 pts — product quality
    if rating >= 4.8:    score += 35
    elif rating >= 4.5:  score += 25
    elif rating >= 4.0:  score += 10

    # Shop type: 25 pts — seller trust
    if shop_type == "mall":        score += 25
    elif shop_type == "preferred": score += 15
    else:                          score += 5

    return score


def _parse_sold(value: str) -> float:
    text = str(value or "").strip().lower().replace(",", "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([km]?)", text)
    if not match:
        return 0.0
    amount = float(match.group(1))
    suffix = match.group(2)
    if suffix == "k":
        return amount * 1_000
    if suffix == "m":
        return amount * 1_000_000
    return amount


def _parse_rating(value: str) -> float:
    text = str(value or "").strip().replace(",", ".")
    match = re.search(r"([0-5](?:\.[0-9]+)?)", text)
    if not match:
        return 0.0
    return float(match.group(1))


def _parse_price(value: str) -> float:
    text = re.sub(r"[^\d]", "", str(value or ""))
    return float(text) if text else 0.0
