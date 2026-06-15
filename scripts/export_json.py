#!/usr/bin/env python3
"""SQLite DB -> GitHub Pages JSON 익스포터.

수집 후 실행: python3 scripts/export_json.py
출력: docs/data/{summary,listings,transactions,zones,analysis}.json
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from real_estate_strategy import store  # noqa: E402

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "data")


def _safe_float(v) -> float | None:
    try:
        return float(v) if v not in (None, "", "None") else None
    except (ValueError, TypeError):
        return None


def _safe_int(v) -> int | None:
    try:
        return int(str(v).replace(",", "")) if v not in (None, "", "None") else None
    except (ValueError, TypeError):
        return None


def compute_gap(listings: list, transactions: list) -> list:
    listing_prices: dict[str, list[float]] = defaultdict(list)
    for li in listings:
        price = _safe_int(li.get("price_manwon"))
        area = _safe_float(li.get("area_sqm"))
        if price and area and area > 0:
            listing_prices[li["district"]].append(price / area)

    tx_prices: dict[str, list[float]] = defaultdict(list)
    for t in transactions:
        price = _safe_int(t.get("price_manwon"))
        area = _safe_float(t.get("area_sqm"))
        if price and area and area > 0:
            tx_prices[t["district"]].append(price / area)

    all_districts = set(listing_prices) | set(tx_prices)
    result = []
    for d in sorted(all_districts):
        lp = listing_prices[d]
        tp = tx_prices[d]
        avg_l = sum(lp) / len(lp) if lp else None
        avg_t = sum(tp) / len(tp) if tp else None
        gap_pct = round((avg_l - avg_t) / avg_t * 100, 1) if avg_l and avg_t else None
        result.append({
            "district": d,
            "avg_listing_per_sqm": round(avg_l, 1) if avg_l else None,
            "avg_tx_per_sqm": round(avg_t, 1) if avg_t else None,
            "gap_pct": gap_pct,
            "listing_count": len(lp),
            "tx_count": len(tp),
        })
    return sorted(result, key=lambda x: (x["gap_pct"] or -9999), reverse=True)


def compute_trend(transactions: list) -> list:
    bucket: dict[tuple, list[float]] = defaultdict(list)
    for t in transactions:
        price = _safe_int(t.get("price_manwon"))
        area = _safe_float(t.get("area_sqm"))
        if price and area and area > 0:
            bucket[(t["district"], t["deal_ymd"])].append(price / area)

    return [
        {
            "district": d,
            "deal_ymd": ym,
            "avg_price_per_sqm": round(sum(v) / len(v), 1),
            "count": len(v),
        }
        for (d, ym), v in sorted(bucket.items())
    ]


def export() -> None:
    conn = store.connect()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    districts = store.collected_districts(conn)
    s = store.summary(conn)

    listings: list[dict] = []
    transactions: list[dict] = []
    zones: list[dict] = []
    for d in districts:
        listings.extend(store.load_listings(conn, d))
        transactions.extend(store.load_transactions(conn, d))
        zones.extend(store.load_zones(conn, d))

    def write(name: str, data: object) -> None:
        path = os.path.join(OUTPUT_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        print(f"  {path} ({os.path.getsize(path):,} bytes)")

    write("listings.json", listings)
    write("transactions.json", transactions)
    write("zones.json", zones)
    write("analysis.json", {
        "gap": compute_gap(listings, transactions),
        "trend": compute_trend(transactions),
    })
    write("summary.json", {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "districts": districts,
        **s,
    })

    print(
        f"완료: 매물 {len(listings)}건 / 실거래 {len(transactions)}건 / "
        f"재개발 {len(zones)}건 / {len(districts)}개 구"
    )


if __name__ == "__main__":
    export()
