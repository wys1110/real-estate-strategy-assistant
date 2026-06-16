#!/usr/bin/env python3
"""SQLite DB -> GitHub Pages JSON 익스포터.

수집 후 실행: python3 scripts/export_json.py
출력: docs/data/{summary,listings,transactions,zones,analysis,recommendations}.json
"""
from __future__ import annotations

import json
import math
import os
import re
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


def _parse_price_manwon(v) -> int | None:
    """부동산뱅크 호가 문자열 파싱. 월세 '보증금/월' 형식은 보증금만 취함."""
    if v in (None, "", "None", "협의", "면담"):
        return None
    s = str(v).split("/")[0].replace(",", "").strip()
    digits = re.sub(r"[^0-9]", "", s)
    return int(digits) if digits else None


def _parse_area_sqm(v) -> float | None:
    """'전용/공급' 형식 파싱 — 전용 우선, 없으면 공급."""
    if v in (None, "", "None"):
        return None
    for p in str(v).split("/"):
        try:
            val = float(p.strip())
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass
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


def compute_recommendations(listings: list, transactions: list, zones: list) -> dict:
    """매매 매물에 투자 점수를 부여해 내림차순 정렬로 반환.

    점수 구성:
      가격갭(50%) + 재개발(30%) + 유동성(20%)
    """
    # 구별 실거래 통계
    tx_by_district: dict[str, list[float]] = defaultdict(list)
    for t in transactions:
        try:
            p = int(t["price_manwon"]) if t.get("price_manwon") is not None else None
            a = float(t["area_sqm"]) if t.get("area_sqm") is not None else None
            if p and a and a > 0:
                tx_by_district[t["district"]].append(p / a)
        except (ValueError, TypeError):
            pass

    dist_tx: dict[str, dict] = {
        d: {"avg": sum(v) / len(v), "count": len(v)}
        for d, v in tx_by_district.items()
    }

    # 구별 최고 재개발 점수 + 구역 정보
    dist_zone: dict[str, dict] = {}
    for z in zones:
        d = z["district"]
        score = float(z.get("score") or 0)
        if d not in dist_zone or score > dist_zone[d]["score"]:
            dist_zone[d] = {
                "score": score,
                "name": z.get("name", ""),
                "stage": z.get("stage", ""),
            }

    items = []
    for li in listings:
        if li.get("trade_type") != "매매":
            continue

        d = li["district"]
        price = _parse_price_manwon(li.get("price_manwon"))
        area = _parse_area_sqm(li.get("area_sqm"))
        price_per_sqm = round(price / area, 1) if price and area and area > 0 else None

        tx_stats = dist_tx.get(d)
        has_tx_data = bool(tx_stats and price_per_sqm is not None)
        district_avg_tx = round(tx_stats["avg"], 1) if tx_stats else None
        tx_count = tx_stats["count"] if tx_stats else 0

        if has_tx_data:
            raw_gap = (tx_stats["avg"] - price_per_sqm) / tx_stats["avg"] * 100
            gap_pct = round(raw_gap, 1)
            score_gap = round(max(-50.0, min(50.0, raw_gap)) + 50.0, 1)
        else:
            gap_pct = None
            score_gap = 50.0

        zone_info = dist_zone.get(d)
        has_zone_data = zone_info is not None
        score_zone = round(zone_info["score"], 1) if zone_info else 0.0

        score_liquidity = round(
            min(100.0, math.log1p(tx_count) / math.log1p(50) * 100), 1
        )

        total_score = round(
            0.50 * score_gap + 0.30 * score_zone + 0.20 * score_liquidity, 1
        )

        items.append({
            "listing_id": li.get("listing_id", ""),
            "district": d,
            "trade_type": li.get("trade_type", ""),
            "listing_type": li.get("listing_type", ""),
            "name": li.get("name", ""),
            "area_sqm": area,
            "area_sqm_raw": li.get("area_sqm", ""),
            "floor": li.get("floor", ""),
            "price_manwon": price,
            "price_manwon_raw": li.get("price_manwon", ""),
            "price_per_sqm": price_per_sqm,
            "agency": li.get("agency", ""),
            "note": li.get("note", ""),
            "detail_url": li.get("detail_url", ""),
            "district_avg_tx_per_sqm": district_avg_tx,
            "district_tx_count": tx_count,
            "district_zone_score": score_zone,
            "district_zone_name": zone_info["name"] if zone_info else "",
            "district_zone_stage": zone_info["stage"] if zone_info else "",
            "score_gap": score_gap,
            "score_zone": score_zone,
            "score_liquidity": score_liquidity,
            "total_score": total_score,
            "gap_pct": gap_pct,
            "has_tx_data": has_tx_data,
            "has_zone_data": has_zone_data,
        })

    items.sort(key=lambda x: x["total_score"], reverse=True)
    scored = sum(1 for x in items if x["has_tx_data"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_count": len(items),
        "scored_count": scored,
        "unscored_count": len(items) - scored,
        "items": items,
    }


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
    write("recommendations.json", compute_recommendations(listings, transactions, zones))
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
