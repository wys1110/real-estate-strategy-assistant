"""Streamlit 부동산 전략 어시스턴트 웹앱.

한 화면에서 모드를 선택하고, 모든 결과를 하나의 Pydeck 지도와 상세 테이블로 봅니다.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import pydeck as pdk
import streamlit as st

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
from real_estate_strategy.poi import ELEMENTARY_SCHOOLS, SHUTTLE_STOPS, SUBWAY_STATIONS


st.set_page_config(page_title="부동산 전략 어시스턴트", page_icon="🏠", layout="wide")
st.markdown("<style>.block-container{padding-top:1.5rem}</style>", unsafe_allow_html=True)

JAYANG_CENTER = (37.5350, 127.0700)
SEOUL_CENTER  = (37.5665, 126.9780)
REGION_OPTIONS = {"서울 광진구 자양동": "1121510500"}
LAWD_OPTIONS   = {"서울 광진구": "11215"}
MODE_OPTIONS   = ["통합", "매물", "실거래", "재개발"]
GEO_CACHE_VERSION = "v4"

DISTRICT_CENTERS: Dict[str, Tuple[float, float]] = {
    "종로구": (37.5735, 126.9788), "중구": (37.5636, 126.9976),
    "용산구": (37.5326, 126.9905), "성동구": (37.5634, 127.0369),
    "광진구": (37.5384, 127.0823), "동대문구": (37.5744, 127.0396),
    "중랑구": (37.6063, 127.0925), "성북구": (37.5894, 127.0167),
    "강북구": (37.6396, 127.0257), "도봉구": (37.6688, 127.0471),
    "노원구": (37.6542, 127.0568), "은평구": (37.6176, 126.9227),
    "서대문구": (37.5791, 126.9368), "마포구": (37.5663, 126.9019),
    "양천구": (37.5169, 126.8664), "강서구": (37.5509, 126.8495),
    "구로구": (37.4955, 126.8875), "금천구": (37.4569, 126.8955),
    "영등포구": (37.5264, 126.8962), "동작구": (37.5124, 126.9393),
    "관악구": (37.4784, 126.9516), "서초구": (37.4837, 127.0324),
    "강남구": (37.5172, 127.0473), "송파구": (37.5145, 127.1059),
    "강동구": (37.5301, 127.1238),
}

DONG_CENTERS: Dict[str, Tuple[float, float]] = {
    "자양동": (37.5350, 127.0700), "화양동": (37.5441, 127.0690),
    "군자동": (37.5550, 127.0750), "능동": (37.5530, 127.0810),
    "구의동": (37.5437, 127.0868), "광장동": (37.5471, 127.1041),
    "중곡동": (37.5607, 127.0801), "성수동1가": (37.5432, 127.0443),
    "성수동2가": (37.5398, 127.0567), "송정동": (37.5546, 127.0688),
    "용답동": (37.5638, 127.0548), "행당동": (37.5588, 127.0292),
    "금호동1가": (37.5548, 127.0242), "금호동2가": (37.5531, 127.0211),
    "금호동3가": (37.5489, 127.0210), "금호동4가": (37.5472, 127.0218),
    "옥수동": (37.5434, 127.0139), "마장동": (37.5663, 127.0424),
    "사근동": (37.5614, 127.0458), "응봉동": (37.5504, 127.0339),
    "하왕십리동": (37.5640, 127.0284), "상왕십리동": (37.5693, 127.0246),
    "고덕동": (37.5606, 127.1577), "상일동": (37.5515, 127.1708),
    "명일동": (37.5513, 127.1440), "암사동": (37.5504, 127.1276),
    "천호동": (37.5444, 127.1246), "성내동": (37.5316, 127.1290),
    "길동": (37.5392, 127.1460), "둔촌동": (37.5218, 127.1367),
    "강일동": (37.5655, 127.1743),
}


def _get_secret(key: str, default: str = "") -> str:
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return os.environ.get(key, default)


def _address_anchor(address: str, fallback: Tuple[float, float]) -> Tuple[Tuple[float, float], float]:
    for token, center in sorted(DONG_CENTERS.items(), key=lambda x: len(x[0]), reverse=True):
        if token in address:
            return center, 0.0016
    for token, center in sorted(DISTRICT_CENTERS.items(), key=lambda x: len(x[0]), reverse=True):
        if token in address:
            return center, 0.0055
    return fallback, 0.012


def _approx_coords(seed: str, center: Tuple[float, float], radius: float) -> Tuple[float, float]:
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    lat_offset = (((h % 10000) / 9999) - 0.5) * 2 * radius
    lon_offset = ((((h >> 16) % 10000) / 9999) - 0.5) * 2 * radius
    return center[0] + lat_offset, center[1] + lon_offset


def _geocode(address: str, center: Tuple[float, float]) -> Tuple[float, float]:
    cache = st.session_state.setdefault("_geo_cache", {})
    cache_key = f"{GEO_CACHE_VERSION}::{address}"
    if cache_key not in cache:
        anchor, radius = _address_anchor(address, center)
        cache[cache_key] = _approx_coords(address, anchor, radius)
    return cache[cache_key]


# ── 색상 상수 ────────────────────────────────────────────────────────────────
_C = {
    "listing":     [220, 50,  50,  220],
    "transaction": [30,  120, 220, 220],
    "redev_high":  [180, 0,   0,   230],
    "redev_mid":   [255, 140, 0,   220],
    "redev_low":   [0,   180, 80,  210],
    "subway":      [255, 165, 0,   200],
    "school":      [0,   160, 80,  200],
    "hynix":       [148, 0,   211, 210],
    "samsung":     [0,   80,  180, 210],
}


def _make_row(lat, lng, label, name, info1="", info2="", info3="", color=None, radius=80):
    r, g, b, a = color or [100, 100, 100, 200]
    return dict(lat=lat, lng=lng, label=label, name=name,
                info1=info1, info2=info2, info3=info3,
                r=r, g=g, b=b, a=a, radius=radius)


def _listing_rows(limit: int) -> List[dict]:
    url = build_list_url(REGION_OPTIONS["서울 광진구 자양동"])
    listings = filter_villas(parse_listings(fetch_html(url), source_url=url))[:limit]
    rows = []
    for li in listings:
        lat, lng = _geocode("서울특별시 광진구 자양동 " + li.name, JAYANG_CENTER)
        rows.append(_make_row(
            lat, lng, "🔴 매물 (호가)", li.name,
            info1=f"{li.area_sqm}㎡ | {li.floor}층",
            info2=f"호가 {li.price_manwon:,}만원",
            info3=li.note[:60],
            color=_C["listing"],
        ))
    return rows


def _transaction_rows(api_key: str, deal_ymd: str, property_type: str, limit: int) -> List[dict]:
    txs = fetch_transactions(
        lawd_cd=LAWD_OPTIONS["서울 광진구"],
        deal_ymd=deal_ymd, property_type=property_type,
        api_key=api_key,
    )[:limit]
    rows = []
    for t in txs:
        addr = f"서울특별시 광진구 {t.dong} {t.lot_number}"
        lat, lng = _geocode(addr, JAYANG_CENTER)
        rows.append(_make_row(
            lat, lng, "🔵 실거래", t.name,
            info1=f"{t.area_sqm}㎡ | {t.floor}층",
            info2=f"거래가 {t.price_manwon:,}만원",
            info3=f"{t.deal_year}-{t.deal_month:02d}-{t.deal_day:02d} | {t.build_year or '-'}년식",
            color=_C["transaction"],
        ))
    return rows


def _redevelopment_rows(districts: Iterable[str], stages: Iterable[str], only_redev: bool, limit: int) -> List[dict]:
    zones = []
    for d in districts:
        fetched, _ = fetch_zones(DISTRICT_CODES[d], page_size=200)
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
    for z in zones:
        addr = f"서울특별시 {z.district} {z.address}"
        lat, lng = _geocode(addr, SEOUL_CENTER)
        color = _C["redev_high"] if z.score >= 80 else (_C["redev_mid"] if z.score >= 60 else _C["redev_low"])
        rows.append(_make_row(
            lat, lng, "⭐ 재개발", z.name,
            info1=f"{z.biz_type} | {z.stage}",
            info2=f"추천 {z.score:.0f}점 | 진행률 {z.progress}%",
            info3=z.address,
            color=color, radius=100,
        ))
    return rows


def _poi_rows(show_subway: bool, show_school: bool, show_hynix: bool, show_samsung: bool) -> List[dict]:
    rows = []
    if show_subway:
        for s in SUBWAY_STATIONS:
            rows.append(_make_row(s["lat"], s["lng"], "🚇 지하철역", s["name"],
                                  info1=s["line"], color=_C["subway"], radius=55))
    if show_school:
        for s in ELEMENTARY_SCHOOLS:
            rows.append(_make_row(s["lat"], s["lng"], "🏫 초등학교", s["name"],
                                  color=_C["school"], radius=55))
    if show_hynix:
        for s in [x for x in SHUTTLE_STOPS if x["company"] == "SK하이닉스"]:
            rows.append(_make_row(s["lat"], s["lng"], "🚌 SK하이닉스 셔틀", s["name"],
                                  color=_C["hynix"], radius=65))
    if show_samsung:
        for s in [x for x in SHUTTLE_STOPS if x["company"] == "삼성전자"]:
            rows.append(_make_row(s["lat"], s["lng"], "🚌 삼성전자 셔틀", s["name"],
                                  color=_C["samsung"], radius=65))
    return rows


# ── UI ───────────────────────────────────────────────────────────────────────
st.title("부동산 전략 어시스턴트")
st.caption("모드를 바꾸면 지도와 데이터가 함께 갱신됩니다.")

with st.sidebar:
    st.markdown("### 데이터 출처")
    st.markdown(
        "- 🔴 부동산뱅크: 현재 매물 호가\n"
        "- 🔵 국토교통부: 신고 실거래가\n"
        "- ⭐ 서울시 정보몽땅: 정비사업"
    )
    st.divider()
    st.markdown("### 📍 지도 레이어")
    show_subway  = st.checkbox("🚇 역세권 (지하철역)", value=True)
    show_school  = st.checkbox("🏫 초품아 (초등학교)", value=False)
    show_hynix   = st.checkbox("🚌 SK하이닉스 셔틀",  value=False)
    show_samsung = st.checkbox("🚌 삼성전자 셔틀",    value=False)

mode = st.radio("모드", MODE_OPTIONS, horizontal=True, index=0)

ctrl = st.columns([1.2, 1, 1, 1, 1])
with ctrl[0]:
    listing_limit = st.number_input("매물 수", 1, 80, 15)
with ctrl[1]:
    deal_ymd = st.text_input("계약년월", value="202501")
with ctrl[2]:
    property_type = st.selectbox(
        "실거래 유형", list(PROPERTY_TYPES),
        format_func=lambda x: "연립다세대" if x == "villa" else "아파트",
    )
with ctrl[3]:
    transaction_limit = st.number_input("실거래 수", 1, 200, 20)
with ctrl[4]:
    redev_limit = st.number_input("구역 수", 1, 100, 25)

redev_cols = st.columns([2, 2, 1])
with redev_cols[0]:
    districts = st.multiselect("재개발 자치구", list(DISTRICT_CODES.keys()),
                               default=["광진구", "성동구", "강동구"])
with redev_cols[1]:
    stages = st.multiselect("진행단계", STAGES, default=INVESTMENT_STAGES)
with redev_cols[2]:
    only_redev = st.checkbox("재개발만", value=False)

api_key = _get_secret("MOLIT_API_KEY")
if mode in ("통합", "실거래") and not api_key:
    api_key = st.text_input("MOLIT API KEY", type="password", help="실거래가 조회에 필요합니다.")

if st.button("조회하고 지도에 표시", type="primary", use_container_width=True):
    map_rows: List[dict] = []
    table_rows: List[Dict] = []
    errors: List[str] = []

    if mode in ("통합", "매물"):
        with st.spinner("매물 호가 조회 중..."):
            try:
                rows = _listing_rows(listing_limit)
                map_rows.extend(rows)
                for r in rows:
                    table_rows.append({"구분": "매물", "건물명": r["name"],
                                       "면적/층": r["info1"], "가격": r["info2"], "비고": r["info3"]})
            except Exception as e:
                errors.append(f"매물 조회 실패: {e}")

    if mode in ("통합", "실거래"):
        if not api_key:
            errors.append("실거래가 조회에는 MOLIT API KEY가 필요합니다.")
        else:
            with st.spinner("실거래가 조회 중..."):
                try:
                    rows = _transaction_rows(api_key, deal_ymd, property_type, transaction_limit)
                    map_rows.extend(rows)
                    for r in rows:
                        table_rows.append({"구분": "실거래", "건물명": r["name"],
                                           "면적/층": r["info1"], "가격": r["info2"], "비고": r["info3"]})
                except Exception as e:
                    errors.append(f"실거래가 조회 실패: {e}")

    if mode in ("통합", "재개발"):
        if not districts:
            errors.append("재개발 자치구를 1개 이상 선택하세요.")
        else:
            with st.spinner("정비사업 데이터 조회 중..."):
                try:
                    rows = _redevelopment_rows(districts, stages, only_redev, redev_limit)
                    map_rows.extend(rows)
                    for r in rows:
                        table_rows.append({"구분": "재개발", "건물명": r["name"],
                                           "면적/층": r["info1"], "가격": r["info2"], "비고": r["info3"]})
                except Exception as e:
                    errors.append(f"재개발 조회 실패: {e}")

    st.session_state["results"] = {"map_rows": map_rows, "table_rows": table_rows,
                                   "errors": errors, "mode": mode}
    st.rerun()

res = st.session_state.get("results", {"map_rows": [], "table_rows": [], "errors": [], "mode": mode})
for err in res["errors"]:
    st.warning(err)

# ── 지도 ─────────────────────────────────────────────────────────────────────
poi_rows = _poi_rows(show_subway, show_school, show_hynix, show_samsung)
all_rows = res["map_rows"] + poi_rows

center = SEOUL_CENTER if res["mode"] == "재개발" else JAYANG_CENTER
zoom   = 11 if res["mode"] == "재개발" else 14

tooltip = {
    "html": """
    <div style='font-size:13px;padding:6px;min-width:150px;max-width:220px'>
      <span style='color:#888;font-size:11px'>{label}</span><br>
      <b style='font-size:14px'>{name}</b><br>
      {info1}<br><b>{info2}</b><br>
      <span style='color:#555'>{info3}</span>
    </div>""",
    "style": {"background": "white", "color": "#333",
              "border": "1px solid #ddd", "borderRadius": "8px", "padding": "6px"},
}

layers = []
if all_rows:
    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame(all_rows),
        get_position=["lng", "lat"],
        get_fill_color=["r", "g", "b", "a"],
        get_radius="radius",
        radius_min_pixels=5,
        radius_max_pixels=22,
        pickable=True,
        stroked=True,
        get_line_color=[255, 255, 255],
        line_width_min_pixels=1,
    ))

st.pydeck_chart(
    pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(latitude=center[0], longitude=center[1], zoom=zoom, pitch=0),
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        tooltip=tooltip,
    ),
    use_container_width=True,
    height=620,
)

# ── 요약 + 테이블 ─────────────────────────────────────────────────────────────
table_rows = res["table_rows"]
if table_rows:
    counts = {}
    for r in table_rows:
        counts[r["구분"]] = counts.get(r["구분"], 0) + 1
    cols = st.columns(len(counts))
    for col, (k, v) in zip(cols, counts.items()):
        col.metric(k, f"{v}건")
    st.divider()
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True, height=360)
elif not res["errors"]:
    st.info("상단 조건을 선택하고 '조회하고 지도에 표시'를 눌러주세요.")
