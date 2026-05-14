from __future__ import annotations

import json
import os
import sys

from flask import Flask, jsonify, request

sys.path.insert(0, os.path.dirname(__file__))

from exporters import export_csv, export_excel, export_json
from filters import filter_products, top_overall, top_per_category

app = Flask(__name__)
_products: list[dict] = []


# ─── CORS ─────────────────────────────────────────────────────────────────────

@app.after_request
def _cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/<path:path>", methods=["OPTIONS"])
def _options(path):
    return "", 204


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/status")
def status():
    return jsonify({"ok": True, "buffered": len(_products)})


@app.route("/categories", methods=["GET"])
def categories():
    cfg = _load_config()
    return jsonify(cfg.get("categories", []))


@app.route("/start", methods=["POST"])
def start():
    _products.clear()
    print("\n[START] Buffer cleared. Waiting for products...")
    return jsonify({"ok": True})


@app.route("/products", methods=["POST"])
def receive():
    items = request.get_json(silent=True) or []
    if isinstance(items, list) and items:
        _products.extend(items)
        print(f"  +{len(items)} products  (total: {len(_products)})")
    return jsonify({"ok": True, "total": len(_products)})


@app.route("/export", methods=["POST"])
def export():
    if not _products:
        print("[EXPORT] Buffer empty — skipping (files not overwritten)")
        return jsonify({"ok": True, "crawled": 0, "scored": 0, "filtered": 0})

    cfg         = _load_config()
    scoring_cfg = cfg.get("scoring", {})
    export_cfg  = cfg.get("export", {})

    crawled             = len(_products)
    top_n_per_category  = scoring_cfg.get("top_n_per_category", 5)
    top_n_overall_val   = scoring_cfg.get("top_n_overall", 10)

    # Score + hard-filter all products (returns list sorted by score desc)
    scored = filter_products(
        _products,
        min_sold=scoring_cfg.get("min_sold", 50),
        min_rating=scoring_cfg.get("min_rating", 3.8),
        min_price=scoring_cfg.get("min_price", 0),
        max_price=scoring_cfg.get("max_price", 0),
    )

    overall = top_overall(scored, top_n_overall_val)
    per_cat = top_per_category(scored, top_n_per_category)

    # Print summary
    print(f"\n[EXPORT] Crawled: {crawled} | Scored: {len(scored)}")
    print(f"  Overall top {top_n_overall_val}: {len(overall)} products")
    print(f"  Per-category top {top_n_per_category}: {len(per_cat)} products")

    # Per-category breakdown
    cat_counts: dict[str, int] = {}
    for p in per_cat:
        cat = p.get("category", "(unknown)")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    for cat, n in sorted(cat_counts.items()):
        print(f"    {cat}: {n}")

    # Top 5 preview
    print("  Preview overall top 5:")
    for p in overall[:5]:
        print(f"    [{p['score']:3d}] {p['name'][:38]} | {p['sold_count']} | {p['rating']} | {p['shop_type']}")

    export_json(scored,              export_cfg.get("json",  "products.json"))
    export_csv(per_cat,              export_cfg.get("csv",   "products.csv"))
    export_excel(overall, per_cat,   export_cfg.get("excel", "products.xlsx"))

    _products.clear()

    return jsonify({
        "ok":      True,
        "crawled": crawled,
        "scored":  len(scored),
        "filtered": len(per_cat),   # used by popup to show "exported X products"
    })


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    try:
        with open("config.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


if __name__ == "__main__":
    print("=" * 45)
    print("  Shopee Crawler Server - localhost:7979")
    print("=" * 45)
    print("1. Load extension into Chrome (chrome://extensions)")
    print("2. Open a Shopee category page")
    print("3. Click extension icon -> Start")
    print("4. Extension auto-crawls all categories")
    print("5. Auto-exports when done (or click Stop)")
    print("=" * 45)
    app.run(host="127.0.0.1", port=7979, debug=False)
