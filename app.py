"""Streamlit 부동산 전략 어시스턴트 웹앱.

한 화면에서 모드를 선택하고, 모든 결과를 하나의 지도와 상세 테이블로 봅니다.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from typing import Dict, Iterable, List, Tuple

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from real_estate_strategy.budongsanbank import (
    build_list_url,
    fetch_html,
    filter_villas,
    parse_listings,
)
from real_estate_strategy.molit import PROPERTY_TYPES, fetch_transactions
from real_estate_strategy.redevelopment import (
    DISTRICT_CODES,
    INVESTMENT_STAGES,
    STAGES,
    enrich_scores,
    fetch_zones,
)


st.set_page_config(page_title="부동산 전략 어시스턴트", page_icon="🏠", layout="wide")

JAYANG_CENTER = (37.5350, 127.0700)
SEOUL_CENTER = (37.5665, 126.9780)
REGION_OPTIONS = {"서울 광진구 자양동": "1121510500"}
LAWD_OPTIONS = {"서울 광진구": "11215"}
MODE_OPTIONS = ["통합", "매물", "실거래", "재개발"]
GEO_CACHE_VERSION = "v3"

DISTRICT_CENTERS: Dict[str, Tuple[float, float]] = {
    "종로구": (37.5735, 126.9788),
    "중구": (37.5636, 126.9976),
    "용산구": (37.5326, 126.9905),
    "성동구": (37.5634, 127.0369),
    "광진구": (37.5384, 127.0823),
    "동대문구": (37.5744, 127.0396),
    "중랑구": (37.6063, 127.0925),
    "성북구": (37.5894, 127.0167),
    "강북구": (37.6396, 127.0257),
    "도봉구": (37.6688, 127.0471),
    "노원구": (37.6542, 127.0568),
    "은평구": (37.6176, 126.9227),
    "서대문구": (37.5791, 126.9368),
    "마포구": (37.5663, 126.9019),
    "양천구": (37.5169, 126.8664),
    "강서구": (37.5509, 126.8495),
    "구로구": (37.4955, 126.8875),
    "금천구": (37.4569, 126.8955),
    "영등포구": (37.5264, 126.8962),
    "동작구": (37.5124, 126.9393),
    "관악구": (37.4784, 126.9516),
    "서초구": (37.4837, 127.0324),
    "강남구": (37.5172, 127.0473),
    "송파구": (37.5145, 127.1059),
    "강동구": (37.5301, 127.1238),
}

DONG_CENTERS: Dict[str, Tuple[float, float]] = {
    "자양동": (37.5350, 127.0700),
    "화양동": (37.5441, 127.0690),
    "군자동": (37.5550, 127.0750),
    "능동": (37.5530, 127.0810),
    "구의동": (37.5437, 127.0868),
    "광장동": (37.5471, 127.1041),
    "중곡동": (37.5607, 127.0801),
    "성수동1가": (37.5432, 127.0443),
    "성수동2가": (37.5398, 127.0567),
    "송정동": (37.5546, 127.0688),
    "용답동": (37.5638, 127.0548),
    "행당동": (37.5588, 127.0292),
    "금호동1가": (37.5548, 127.0242),
    "금호동2가": (37.5531, 127.0211),
    "금호동3가": (37.5489, 127.0210),
    "금호동4가": (37.5472, 127.0218),
    "옥수동": (37.5434, 127.0139),
    "마장동": (37.5663, 127.0424),
    "사근동": (37.5614, 127.0458),
    "응봉동": (37.5504, 127.0339),
    "하왕십리동": (37.5640, 127.0284),
    "상왕십리동": (37.5693, 127.0246),
    "고덕동": (37.5606, 127.1577),
    "상일동": (37.5515, 127.1708),
    "명일동": (37.5513, 127.1440),
    "암사동": (37.5504, 127.1276),
    "천호동": (37.5444, 127.1246),
    "성내동": (37.5316, 127.1290),
    "길동": (37.5392, 127.1460),
    "둔촌동": (37.5218, 127.1367),
    "강일동": (37.5655, 127.1743),
}


def _get_secret(key: str, default: str = "") -> str:
    """st.secrets -> os.environ 순서로 시크릿을 읽습니다."""
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return os.environ.get(key, default)


def _nominatim_search(address: str):
    params = urllib.parse.urlencode({"q": address, "format": "json", "limit": 1})
    url = "https://nominatim.openstreetmap.org/search?" + params
    req = urllib.request.Request(url, headers={"User-Agent": "RealEstateStrategyApp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if data:
            return (float(data[0]["lat"]), float(data[0]["lon"]))
    except Exception:
        pass
    return None


def _address_anchor(address: str, fallback: Tuple[float, float]) -> Tuple[Tuple[float, float], str, float]:
    """주소에 포함된 동/구 이름으로 근사 좌표의 기준점을 정합니다."""
    for token, center in sorted(DONG_CENTERS.items(), key=lambda item: len(item[0]), reverse=True):
        if token in address:
            return center, "동 기준 근사 위치", 0.0016
    for token, center in sorted(DISTRICT_CENTERS.items(), key=lambda item: len(item[0]), reverse=True):
        if token in address:
            return center, "구 기준 근사 위치", 0.0055
    return fallback, "서울 기준 근사 위치", 0.012


def _approx_coords(seed: str, center: Tuple[float, float], radius: float) -> Tuple[float, float]:
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    lat_offset = (((h % 10000) / 9999) - 0.5) * 2 * radius
    lon_offset = ((((h >> 16) % 10000) / 9999) - 0.5) * 2 * radius
    return (
        center[0] + lat_offset,
        center[1] + lon_offset,
    )


def _geocode(address: str, exact: bool, center: Tuple[float, float]):
    """주소 -> ((lat, lon), precision_label). 기본은 동/구 기준 빠른 근사 좌표."""
    cache_key = f"{GEO_CACHE_VERSION}::{'exact' if exact else 'fast'}::{address}"
    cache = st.session_state.setdefault("_geo_cache", {})
    if cache_key in cache:
        return cache[cache_key]

    if exact:
        coords = _nominatim_search(address)
        if coords:
            cache[cache_key] = (coords, "주소 조회 위치")
            time.sleep(1.1)
            return cache[cache_key]

    anchor, precision, radius = _address_anchor(address, center)
    cache[cache_key] = (_approx_coords(address, anchor, radius), precision)
    return cache[cache_key]


def _listing_rows_and_pins(limit: int, include_all: bool):
    source_url = build_list_url(REGION_OPTIONS["서울 광진구 자양동"])
    html = fetch_html(source_url)
    listings = parse_listings(html, source_url=source_url)
    if not include_all:
        listings = filter_villas(listings)
    listings = listings[:limit]

    rows = []
    pins = []
    for li in listings:
        price_label = f"{li.price_manwon}만원"
        rows.append({
            "구분": "매물",
            "건물명": li.name,
            "동": "자양동",
            "면적": li.area_sqm,
            "층": li.floor,
            "가격": price_label,
            "유형/단계": li.listing_type,
            "비고": li.note[:80],
            "상세": li.detail_url,
        })
        pins.append({
            "kind": "listing",
            "address": "서울특별시 광진구 자양동 " + li.name,
            "label": li.name or "매물",
            "price": price_label,
            "detail": f"{li.listing_type} | {li.area_sqm}㎡ | {li.floor}층<br>{li.note[:80]}",
        })
    return rows, pins


def _transaction_rows_and_pins(api_key: str, deal_ymd: str, property_type: str, limit: int):
    txs = fetch_transactions(
        lawd_cd=LAWD_OPTIONS["서울 광진구"],
        deal_ymd=deal_ymd,
        property_type=property_type,
        api_key=api_key,
    )[:limit]

    rows = []
    pins = []
    for t in txs:
        trade_day = f"{t.deal_year}-{t.deal_month:02d}-{t.deal_day:02d}"
        price_label = f"{t.price_manwon:,}만원"
        rows.append({
            "구분": "실거래",
            "건물명": t.name,
            "동": t.dong,
            "면적": f"{t.area_sqm}㎡",
            "층": t.floor if t.floor is not None else "-",
            "가격": price_label,
            "유형/단계": "연립다세대" if property_type == "villa" else "아파트",
            "비고": f"{trade_day} 거래 | {t.build_year or '-'}년식",
            "상세": "",
        })
        pins.append({
            "kind": "transaction",
            "address": f"서울특별시 광진구 {t.dong} {t.lot_number}",
            "label": t.name or "실거래",
            "price": price_label,
            "detail": f"{trade_day} | {t.area_sqm}㎡ | {t.floor if t.floor is not None else '-'}층",
        })
    return rows, pins


def _redevelopment_rows_and_pins(districts: Iterable[str], stages: Iterable[str], only_redev: bool, limit: int):
    zones = []
    for district in districts:
        fetched, _ = fetch_zones(DISTRICT_CODES[district], page_size=200)
        zones.extend(fetched)

    stage_set = set(stages)
    if stage_set:
        zones = [z for z in zones if z.stage in stage_set]
    if only_redev:
        zones = [z for z in zones if "재개발" in z.biz_type]

    zones = enrich_scores(zones)
    zones.sort(key=lambda z: z.score, reverse=True)
    zones = zones[:limit]

    rows = []
    pins = []
    for z in zones:
        rows.append({
            "구분": "재개발",
            "건물명": z.name,
            "동": z.district,
            "면적": "",
            "층": "",
            "가격": f"{z.score:.0f}점",
            "유형/단계": f"{z.biz_type} / {z.stage}",
            "비고": f"진행률 {z.progress}% | 대표지번 {z.address}",
            "상세": "",
        })
        pins.append({
            "kind": "redevelopment",
            "address": f"서울특별시 {z.district} {z.address}",
            "label": z.name,
            "price": f"추천 {z.score:.0f}점",
            "detail": f"{z.biz_type} | {z.stage} ({z.progress}%)",
            "score": z.score,
        })
    return rows, pins


def _map_center(mode: str) -> Tuple[float, float]:
    return SEOUL_CENTER if mode == "재개발" else JAYANG_CENTER


def _pin_style(pin: Dict) -> Tuple[str, str]:
    if pin["kind"] == "listing":
        return "red", "home"
    if pin["kind"] == "transaction":
        return "blue", "info-sign"
    score = pin.get("score", 0)
    if score >= 80:
        return "darkred", "star"
    if score >= 60:
        return "orange", "star"
    return "green", "star"


def _render_map(pins: List[Dict], exact_geocode: bool, center: Tuple[float, float]) -> None:
    m = folium.Map(location=list(center), zoom_start=13 if center == JAYANG_CENTER else 11)

    if not pins:
        folium.Marker(
            list(center),
            tooltip="조회 결과 없음",
            popup="상단 조건을 선택하고 조회하세요.",
        ).add_to(m)
        st_folium(m, height=560, width=None)
        return

    unique_addresses = sorted(set(pin["address"] for pin in pins))
    coords_map = {}
    progress = st.progress(0, text="지도 위치 매핑 중...")
    for i, address in enumerate(unique_addresses):
        progress.progress((i + 1) / len(unique_addresses), text=f"지도 위치 매핑 {i+1}/{len(unique_addresses)}")
        coords_map[address] = _geocode(address, exact=exact_geocode, center=center)
    progress.empty()

    lookup_count = 0
    mapped_coords: List[Tuple[float, float]] = []
    for pin in pins:
        (lat, lon), precision = coords_map[pin["address"]]
        mapped_coords.append((lat, lon))
        lookup_count += int(precision == "주소 조회 위치")
        color, icon = _pin_style(pin)
        popup_html = f"<b>{pin['label']}</b><br>{pin['price']}<br>{pin['detail']}"
        if precision != "주소 조회 위치":
            popup_html += f"<br><i>{precision}</i>"
        folium.Marker(
            [lat, lon],
            tooltip=pin["label"],
            popup=folium.Popup(popup_html, max_width=280),
            icon=folium.Icon(color=color, icon=icon),
        ).add_to(m)

    if mapped_coords:
        lats = [lat for lat, _ in mapped_coords]
        lons = [lon for _, lon in mapped_coords]
        if len(mapped_coords) == 1:
            lat, lon = mapped_coords[0]
            bounds = [[lat - 0.003, lon - 0.003], [lat + 0.003, lon + 0.003]]
        else:
            bounds = [[min(lats), min(lons)], [max(lats), max(lons)]]
        m.fit_bounds(bounds, padding=(24, 24))

    st_folium(m, height=560, width=None)
    st.caption(
        f"빨강=매물 | 파랑=실거래 | 별=재개발 — 총 {len(pins)}개 위치, "
        f"주소 조회 {lookup_count}개, 동/구 근사 {len(pins) - lookup_count}개"
    )


def _price_numbers(rows: List[Dict], category: str) -> List[int]:
    values = []
    for row in rows:
        if row["구분"] != category:
            continue
        digits = "".join(ch for ch in str(row["가격"]) if ch.isdigit())
        if digits:
            values.append(int(digits))
    return values


def _render_summary(rows: List[Dict], pins: List[Dict]) -> None:
    listing_prices = _price_numbers(rows, "매물")
    transaction_prices = _price_numbers(rows, "실거래")
    redev_scores = [
        int(float(row["가격"].replace("점", "")))
        for row in rows
        if row["구분"] == "재개발" and str(row["가격"]).endswith("점")
    ]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("지도 위치", f"{len(pins)}개")
    c2.metric("매물", f"{len(listing_prices)}건")
    c3.metric("실거래", f"{len(transaction_prices)}건")
    c4.metric("재개발", f"{len(redev_scores)}건")

    if listing_prices or transaction_prices or redev_scores:
        s1, s2, s3 = st.columns(3)
        if listing_prices:
            s1.metric("매물 평균 호가", f"{sum(listing_prices) / len(listing_prices):,.0f}만원")
        if transaction_prices:
            s2.metric("실거래 평균가", f"{sum(transaction_prices) / len(transaction_prices):,.0f}만원")
        if redev_scores:
            s3.metric("재개발 평균점수", f"{sum(redev_scores) / len(redev_scores):.1f}점")


def _render_table(rows: List[Dict]) -> None:
    if not rows:
        st.info("표시할 데이터가 없습니다.")
        return
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        width="stretch",
        height=420,
        column_config={"상세": st.column_config.LinkColumn("상세")},
    )


st.title("부동산 전략 어시스턴트")
st.caption("모드만 바꾸면 지도와 데이터가 같이 갱신됩니다.")

with st.sidebar:
    st.markdown("### 데이터 출처")
    st.markdown(
        "- 부동산뱅크: 현재 매물 호가\n"
        "- 국토교통부: 신고 실거래가\n"
        "- 서울시 정보몽땅: 정비사업"
    )
    st.divider()
    st.markdown("### 지도 색상")
    st.markdown("빨강=매물, 파랑=실거래, 별=재개발")

mode = st.radio("모드", MODE_OPTIONS, horizontal=True, index=0)

control_cols = st.columns([1.2, 1, 1, 1, 1])
with control_cols[0]:
    exact_geocode = st.checkbox("주소 좌표 조회", value=False, help="느릴 수 있습니다. 기본은 빠른 동/구 기준 근사 위치입니다.")
with control_cols[1]:
    listing_limit = st.number_input("매물 수", min_value=1, max_value=80, value=15)
with control_cols[2]:
    deal_ymd = st.text_input("계약년월", value="202501")
with control_cols[3]:
    property_type = st.selectbox(
        "실거래 유형",
        list(PROPERTY_TYPES),
        format_func=lambda x: "연립다세대" if x == "villa" else "아파트",
    )
with control_cols[4]:
    transaction_limit = st.number_input("실거래 수", min_value=1, max_value=200, value=20)

redev_cols = st.columns([2, 2, 1, 1])
with redev_cols[0]:
    districts = st.multiselect(
        "재개발 자치구",
        list(DISTRICT_CODES.keys()),
        default=["광진구", "성동구", "강동구"],
    )
with redev_cols[1]:
    stages = st.multiselect("진행단계", STAGES, default=INVESTMENT_STAGES)
with redev_cols[2]:
    only_redev = st.checkbox("재개발만", value=False)
with redev_cols[3]:
    redev_limit = st.number_input("구역 수", min_value=1, max_value=100, value=25)

api_key = _get_secret("MOLIT_API_KEY")
if mode in ("통합", "실거래") and not api_key:
    api_key = st.text_input("MOLIT API KEY", type="password", help="실거래가 조회에 필요합니다.")

if st.button("조회하고 지도에 표시", type="primary", width="stretch"):
    rows: List[Dict] = []
    pins: List[Dict] = []
    errors: List[str] = []

    if mode in ("통합", "매물"):
        with st.spinner("매물 호가 조회 중..."):
            try:
                listing_rows, listing_pins = _listing_rows_and_pins(listing_limit, include_all=False)
                rows.extend(listing_rows)
                pins.extend(listing_pins)
            except Exception as exc:
                errors.append(f"매물 조회 실패: {exc}")

    if mode in ("통합", "실거래"):
        if not api_key:
            errors.append("실거래가 조회에는 MOLIT API KEY가 필요합니다.")
        else:
            with st.spinner("실거래가 조회 중..."):
                try:
                    tx_rows, tx_pins = _transaction_rows_and_pins(
                        api_key=api_key,
                        deal_ymd=deal_ymd,
                        property_type=property_type,
                        limit=transaction_limit,
                    )
                    rows.extend(tx_rows)
                    pins.extend(tx_pins)
                except Exception as exc:
                    errors.append(f"실거래가 조회 실패: {exc}")

    if mode in ("통합", "재개발"):
        if not districts:
            errors.append("재개발 자치구를 1개 이상 선택하세요.")
        else:
            with st.spinner("정비사업 데이터 조회 중..."):
                try:
                    zone_rows, zone_pins = _redevelopment_rows_and_pins(
                        districts=districts,
                        stages=stages,
                        only_redev=only_redev,
                        limit=redev_limit,
                    )
                    rows.extend(zone_rows)
                    pins.extend(zone_pins)
                except Exception as exc:
                    errors.append(f"재개발 조회 실패: {exc}")

    st.session_state["map_results"] = {
        "mode": mode,
        "rows": rows,
        "pins": pins,
        "errors": errors,
        "exact_geocode": exact_geocode,
    }

results = st.session_state.get("map_results", {"mode": mode, "rows": [], "pins": [], "errors": [], "exact_geocode": exact_geocode})
for error in results["errors"]:
    st.warning(error)

st.divider()
st.subheader("지도")
_render_map(results["pins"], exact_geocode=results.get("exact_geocode", False), center=_map_center(results["mode"]))

st.subheader("요약")
_render_summary(results["rows"], results["pins"])

st.subheader("상세 데이터")
_render_table(results["rows"])
