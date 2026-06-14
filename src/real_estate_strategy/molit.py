"""MOLIT (국토교통부) 매매 실거래가 조회 모듈.

환경변수 MOLIT_API_KEY 에 공공데이터포털 일반 인증키를 설정하고 사용합니다.

지원 유형:
  villa  → 연립다세대  RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade
  apt    → 아파트      RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

_BASE = "https://apis.data.go.kr/1613000"

_ENDPOINTS = {
    "villa": f"{_BASE}/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade",
    "apt":   f"{_BASE}/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
}

# 각 유형별로 건물명이 담긴 XML 태그가 다름
_NAME_TAG = {
    "villa": ("mhouseNm", "연립다세대"),
    "apt":   ("aptNm", "아파트"),
}

PROPERTY_TYPES = tuple(_ENDPOINTS.keys())
_RETRYABLE_HTTP_STATUS = {403, 429, 500, 502, 503, 504}


@dataclass
class Transaction:
    """국토부 신고 실거래 1건."""

    data_type: str          # "actual_transaction"
    property_type: str      # "villa" | "apt"
    deal_year: int
    deal_month: int
    deal_day: int
    name: str               # 건물명
    dong: str               # 법정동
    lot_number: str         # 지번
    area_sqm: float         # 전용면적 (㎡)
    floor: Optional[int]    # 층
    build_year: Optional[int]
    price_manwon: int       # 거래금액 (만원)
    price_krw: int          # 거래금액 (원)
    fetched_at: str         # 조회 시각 ISO 8601 UTC


def _text(elem: Optional[ET.Element]) -> str:
    if elem is None:
        return ""
    return (elem.text or "").strip()


def _first_text(item: ET.Element, *names: str) -> str:
    for name in names:
        value = _text(item.find(name))
        if value:
            return value
    return ""


def _price_to_manwon(raw: str) -> int:
    return int(raw.replace(",", "").strip())


def _resolve_key(api_key: Optional[str]) -> str:
    key = api_key or os.environ.get("MOLIT_API_KEY", "")
    if not key:
        raise ValueError(
            "API 키가 없습니다. 환경변수 MOLIT_API_KEY를 설정하거나 api_key 인자를 전달하세요."
        )
    return key


def _fetch_raw(
    endpoint: str,
    key: str,
    lawd_cd: str,
    deal_ymd: str,
    num_of_rows: int,
    attempts: int = 5,
    initial_delay_seconds: float = 0.5,
) -> bytes:
    other = urllib.parse.urlencode({
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "numOfRows": num_of_rows,
        "pageNo": 1,
    })
    # serviceKey는 포털에서 발급된 값 그대로 사용 (urlencode 시 이중인코딩 방지)
    url = f"{endpoint}?serviceKey={key}&{other}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last_error: Optional[Exception] = None

    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in _RETRYABLE_HTTP_STATUS or attempt == attempts:
                raise _sanitize_http_error(exc, endpoint, lawd_cd, deal_ymd)
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == attempts:
                raise RuntimeError(_safe_fetch_error(endpoint, lawd_cd, deal_ymd, exc))

        time.sleep(initial_delay_seconds * (2 ** (attempt - 1)))

    raise RuntimeError(_safe_fetch_error(endpoint, lawd_cd, deal_ymd, last_error))


def _sanitize_http_error(
    error: urllib.error.HTTPError,
    endpoint: str,
    lawd_cd: str,
    deal_ymd: str,
) -> RuntimeError:
    return RuntimeError(
        "MOLIT API HTTP {status}: endpoint={endpoint} LAWD_CD={lawd_cd} DEAL_YMD={deal_ymd}".format(
            status=error.code,
            endpoint=endpoint,
            lawd_cd=lawd_cd,
            deal_ymd=deal_ymd,
        )
    )


def _safe_fetch_error(
    endpoint: str,
    lawd_cd: str,
    deal_ymd: str,
    error: Optional[Exception],
) -> str:
    return "MOLIT API request failed: endpoint={endpoint} LAWD_CD={lawd_cd} DEAL_YMD={deal_ymd} error={error}".format(
        endpoint=endpoint,
        lawd_cd=lawd_cd,
        deal_ymd=deal_ymd,
        error=error,
    )


def _parse_items(raw: bytes, property_type: str, fetched_at: str) -> List[Transaction]:
    root = ET.fromstring(raw)

    result_code = _text(root.find(".//resultCode"))
    result_msg  = _text(root.find(".//resultMsg"))
    if result_code not in ("00", "000", "0000", ""):
        raise RuntimeError(f"API 오류 [{result_code}]: {result_msg}")

    name_tags = _NAME_TAG[property_type]
    transactions: List[Transaction] = []

    for item in root.findall(".//item"):
        raw_price = _first_text(item, "dealAmount", "거래금액")
        if not raw_price:
            continue

        price_manwon = _price_to_manwon(raw_price)

        raw_area  = _first_text(item, "excluUseAr", "전용면적")
        area_sqm  = float(raw_area) if raw_area else 0.0

        raw_floor = _first_text(item, "floor", "층")
        floor     = int(raw_floor) if raw_floor.lstrip("-").isdigit() else None

        raw_build  = _first_text(item, "buildYear", "건축년도")
        build_year = int(raw_build) if raw_build.isdigit() else None

        transactions.append(Transaction(
            data_type="actual_transaction",
            property_type=property_type,
            deal_year=int(_first_text(item, "dealYear", "년") or "0"),
            deal_month=int(_first_text(item, "dealMonth", "월") or "0"),
            deal_day=int(_first_text(item, "dealDay", "일") or "0"),
            name=_first_text(item, *name_tags),
            dong=_first_text(item, "umdNm", "법정동"),
            lot_number=_first_text(item, "jibun", "지번"),
            area_sqm=area_sqm,
            floor=floor,
            build_year=build_year,
            price_manwon=price_manwon,
            price_krw=price_manwon * 10_000,
            fetched_at=fetched_at,
        ))

    return transactions


def fetch_transactions(
    lawd_cd: str,
    deal_ymd: str,
    property_type: str = "villa",
    api_key: Optional[str] = None,
    num_of_rows: int = 100,
) -> List[Transaction]:
    """매매 실거래 목록을 반환합니다.

    Args:
        lawd_cd:       법정동코드 앞 5자리 (예: '11215' → 서울 광진구)
        deal_ymd:      계약년월 6자리 (예: '202605')
        property_type: 'villa' (연립다세대) 또는 'apt' (아파트)
        api_key:       공공데이터포털 일반 인증키. None이면 환경변수 MOLIT_API_KEY 사용.
        num_of_rows:   한 번에 가져올 최대 건수 (기본 100, 최대 1000)
    """
    if property_type not in _ENDPOINTS:
        raise ValueError(f"property_type은 {PROPERTY_TYPES} 중 하나여야 합니다.")

    key      = _resolve_key(api_key)
    endpoint = _ENDPOINTS[property_type]
    fetched_at = datetime.now(timezone.utc).isoformat()

    raw = _fetch_raw(endpoint, key, lawd_cd, deal_ymd, num_of_rows)
    return _parse_items(raw, property_type, fetched_at)
