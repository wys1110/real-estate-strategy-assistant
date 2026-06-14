"""MOLIT (국토교통부) 연립다세대 매매 실거래가 조회 모듈.

환경변수 MOLIT_API_KEY 에 공공데이터포털 일반 인증키를 설정하고 사용합니다.
End Point: https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade
"""

from __future__ import annotations

import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

_ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade"


@dataclass
class Transaction:
    """국토부 신고 실거래 1건."""

    data_type: str                  # 항상 "actual_transaction"
    deal_year: int
    deal_month: int
    deal_day: int
    name: str                       # 연립다세대 건물명
    dong: str                       # 법정동
    lot_number: str                 # 지번
    area_sqm: float                 # 전용면적 (㎡)
    floor: Optional[int]            # 층
    build_year: Optional[int]       # 건축년도
    price_manwon: int               # 거래금액 (만원)
    price_krw: int                  # 거래금액 (원)
    fetched_at: str                 # 조회 시각 ISO 8601 UTC


def _text(elem: Optional[ET.Element]) -> str:
    if elem is None:
        return ""
    return (elem.text or "").strip()


def _price_to_manwon(raw: str) -> int:
    return int(raw.replace(",", "").strip())


def fetch_transactions(
    lawd_cd: str,
    deal_ymd: str,
    api_key: Optional[str] = None,
    num_of_rows: int = 100,
) -> list[Transaction]:
    """연립다세대 매매 실거래 목록을 반환합니다.

    Args:
        lawd_cd:     법정동코드 앞 5자리 (예: '11215' → 서울 광진구)
        deal_ymd:    계약년월 6자리 (예: '202605')
        api_key:     공공데이터포털 일반 인증키. None이면 환경변수 MOLIT_API_KEY 사용.
        num_of_rows: 한 번에 가져올 최대 건수 (기본 100, 최대 1000)
    """
    key = api_key or os.environ.get("MOLIT_API_KEY", "")
    if not key:
        raise ValueError(
            "API 키가 없습니다. 환경변수 MOLIT_API_KEY를 설정하거나 api_key 인자를 전달하세요."
        )

    # serviceKey는 이미 인코딩된 값이므로 quote_via=str 로 재인코딩 방지
    other_params = urllib.parse.urlencode({
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "numOfRows": num_of_rows,
        "pageNo": 1,
    })
    url = f"{_ENDPOINT}?serviceKey={key}&{other_params}"

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()

    fetched_at = datetime.now(timezone.utc).isoformat()

    root = ET.fromstring(raw)

    result_code = _text(root.find(".//resultCode"))
    result_msg = _text(root.find(".//resultMsg"))
    if result_code not in ("00", "0000", ""):
        raise RuntimeError(f"API 오류 [{result_code}]: {result_msg}")

    items = root.findall(".//item")
    transactions: list[Transaction] = []

    for item in items:
        raw_price = _text(item.find("거래금액"))
        if not raw_price:
            continue

        price_manwon = _price_to_manwon(raw_price)

        raw_area = _text(item.find("전용면적"))
        area_sqm = float(raw_area) if raw_area else 0.0

        raw_floor = _text(item.find("층"))
        floor = int(raw_floor) if raw_floor.lstrip("-").isdigit() else None

        raw_build = _text(item.find("건축년도"))
        build_year = int(raw_build) if raw_build.isdigit() else None

        transactions.append(Transaction(
            data_type="actual_transaction",
            deal_year=int(_text(item.find("년")) or "0"),
            deal_month=int(_text(item.find("월")) or "0"),
            deal_day=int(_text(item.find("일")) or "0"),
            name=_text(item.find("연립다세대")),
            dong=_text(item.find("법정동")),
            lot_number=_text(item.find("지번")),
            area_sqm=area_sqm,
            floor=floor,
            build_year=build_year,
            price_manwon=price_manwon,
            price_krw=price_manwon * 10_000,
            fetched_at=fetched_at,
        ))

    return transactions
