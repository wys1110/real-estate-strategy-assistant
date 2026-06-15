"""배치 수집 오케스트레이션.

각 자치구의 매물·실거래·정비사업을 외부 소스에서 가져와 SQLite 스냅샷에
기록합니다. 실패 시 조용히 폴백하지 않고 증상(상태코드/본문)을 기록합니다.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional

from . import store
from .budongsanbank import build_list_url, fetch_html, filter_villas, parse_listings
from .molit import fetch_transactions
from .redevelopment import DISTRICT_CODES, enrich_scores, fetch_zones

# BudongsanBank region_cd (10자리 법정동코드). 광진구 자양동만 실제 동작 확인됨.
BBANK_CODES: Dict[str, str] = {
    "종로구": "1111010100", "중구": "1114010100", "용산구": "1117010100",
    "성동구": "1120010100", "광진구": "1121510500", "동대문구": "1123010100",
    "중랑구": "1126010100", "성북구": "1129010100", "강북구": "1130510100",
    "도봉구": "1132010100", "노원구": "1135010100", "은평구": "1138010100",
    "서대문구": "1141010100", "마포구": "1144010100", "양천구": "1147010100",
    "강서구": "1150010100", "구로구": "1153010100", "금천구": "1154510100",
    "영등포구": "1156010100", "동작구": "1159010100", "관악구": "1162010100",
    "서초구": "1165010100", "강남구": "1168010100", "송파구": "1171010100",
    "강동구": "1174010100",
}

DISTRICTS = list(DISTRICT_CODES.keys())


@dataclass
class CollectResult:
    district: str
    kind: str
    count: int
    ok: bool
    symptom: str = ""

    def line(self) -> str:
        mark = "✓" if self.ok else "✗"
        tail = f" ({self.symptom})" if self.symptom else ""
        return f"  {mark} {self.kind:6s} {self.count:4d}건{tail}"


def collect_listings(conn: sqlite3.Connection, district: str, limit: int = 100) -> CollectResult:
    region_code = BBANK_CODES.get(district)
    if not region_code:
        store.record_failure(conn, district, "매물", "", "region code 미등록")
        return CollectResult(district, "매물", 0, False, "region code 미등록")
    try:
        url = build_list_url(region_code)
        all_listings = parse_listings(fetch_html(url), source_url=url)
        listings = filter_villas(all_listings)[:limit] or all_listings[:limit]
        n = store.save_listings(conn, district, listings)
        return CollectResult(district, "매물", n, True)
    except Exception as e:  # noqa: BLE001 - 증상 보존이 목적
        store.record_failure(conn, district, "매물", "", str(e)[:120])
        return CollectResult(district, "매물", 0, False, str(e)[:80])


def collect_transactions(
    conn: sqlite3.Connection,
    district: str,
    deal_ymd: str,
    property_type: str = "villa",
    api_key: Optional[str] = None,
    limit: int = 1000,
) -> CollectResult:
    lawd_cd = DISTRICT_CODES.get(district, "11215")
    try:
        txs = fetch_transactions(
            lawd_cd=lawd_cd, deal_ymd=deal_ymd, property_type=property_type,
            api_key=api_key, num_of_rows=min(1000, max(limit, 100)),
        )[:limit]
        n = store.save_transactions(conn, district, deal_ymd, property_type, txs)
        return CollectResult(district, "실거래", n, True)
    except Exception as e:  # noqa: BLE001
        store.record_failure(conn, district, "실거래", f"{deal_ymd}/{property_type}", str(e)[:120])
        return CollectResult(district, "실거래", 0, False, str(e)[:80])


def collect_zones(conn: sqlite3.Connection, district: str) -> CollectResult:
    code = DISTRICT_CODES.get(district)
    if not code:
        store.record_failure(conn, district, "재개발", "", "district code 미등록")
        return CollectResult(district, "재개발", 0, False, "district code 미등록")
    try:
        zones, _ = fetch_zones(code, page=1, page_size=200)
        zones = enrich_scores(zones)
        n = store.save_zones(conn, district, zones)
        return CollectResult(district, "재개발", n, True)
    except Exception as e:  # noqa: BLE001
        store.record_failure(conn, district, "재개발", "", str(e)[:120])
        return CollectResult(district, "재개발", 0, False, str(e)[:80])


def collect_district(
    conn: sqlite3.Connection,
    district: str,
    *,
    deal_ymd: str,
    property_type: str = "villa",
    api_key: Optional[str] = None,
    listing_limit: int = 100,
    tx_limit: int = 1000,
    kinds: Optional[List[str]] = None,
) -> List[CollectResult]:
    """한 자치구의 선택된 종류를 수집합니다. kinds 기본값은 매물·실거래·재개발 전부."""
    kinds = kinds or ["매물", "실거래", "재개발"]
    results: List[CollectResult] = []
    if "매물" in kinds:
        results.append(collect_listings(conn, district, listing_limit))
    if "실거래" in kinds and api_key:
        results.append(collect_transactions(conn, district, deal_ymd, property_type, api_key, tx_limit))
    if "재개발" in kinds:
        results.append(collect_zones(conn, district))
    return results
