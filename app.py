"""Streamlit 부동산 전략 어시스턴트 — 조회(읽기) 전용 앱.

구조: 수집(배치 CLI) → SQLite 스냅샷 → 이 앱(읽기 전용).
앱은 조회 시 네트워크를 사용하지 않고 DB만 읽어 즉시 응답합니다.
지도는 입력이 아니라 결과 표시 전용입니다.

데이터 갱신:
    PYTHONPATH=src python3 -m real_estate_strategy.cli collect --all --deal-ymd 202501
"""
from __future__ import annotations

import hashlib
import os
import sys
from typing import Dict, List, Tuple

import folium
from folium import JsCode
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from real_estate_strategy import collect as collect_mod
from real_estate_strategy import store
from real_estate_strategy.molit import PROPERTY_TYPES
from real_estate_strategy.redevelopment import DISTRICT_CODES
from real_estate_strategy.poi import ELEMENTARY_SCHOOLS, SHUTTLE_STOPS, SUBWAY_STATIONS


st.set_page_config(page_title="부동산 전략 어시스턴트", page_icon="🏠", layout="wide")
st.markdown("<style>.block-container{padding-top:1.5rem}</style>", unsafe_allow_html=True)

SEOUL_CENTER = (37.5665, 126.9780)
MODE_OPTIONS = ["통합", "매물", "실거래", "재개발"]
GEO_CACHE_VERSION = "v7"
DISTRICTS = list(DISTRICT_CODES.keys())

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

_C = {
    "listing": "#dc3232", "transaction": "#1e78dc",
    "redev_high": "#b40000", "redev_mid": "#ff8c00", "redev_low": "#00b450",
    "subway": "#ffa500", "school": "#00a050", "hynix": "#9400d3", "samsung": "#0050b4",
}


def _get_secret(key: str, default: str = "") -> str:
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return os.environ.get(key, default)


# ── 근사 지오코딩 (지도 표시 전용, 결정적) ───────────────────────────────────
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
    anchor, radius = _address_anchor(address, center)
    return _approx_coords(f"{GEO_CACHE_VERSION}::{address}", anchor, radius)


def _make_row(lat, lng, label, name, info1="", info2="", info3="", color="#666", radius=7):
    return dict(lat=lat, lng=lng, label=label, name=name,
                info1=info1, info2=info2, info3=info3, color=color, radius=radius)


# ── DB 레코드 → 지도/테이블 행 ────────────────────────────────────────────────
def _listing_rows(district: str, recs: List[dict]) -> List[dict]:
    center = DISTRICT_CENTERS.get(district, SEOUL_CENTER)
    rows = []
    for li in recs:
        lat, lng = _geocode(f"서울특별시 {district} {li['name']}", center)
        rows.append(_make_row(
            lat, lng, "매물 (호가)", li["name"],
            info1=f"{li['area_sqm']}㎡ | {li['floor']}층",
            info2=f"호가 {li['price_manwon']}만원",
            info3=(li["note"] or "")[:60], color=_C["listing"],
        ))
    return rows


def _transaction_rows(district: str, recs: List[dict]) -> List[dict]:
    center = DISTRICT_CENTERS.get(district, SEOUL_CENTER)
    rows = []
    for t in recs:
        addr = f"서울특별시 {district} {t['dong']} {t['lot_number']}"
        lat, lng = _geocode(addr, center)
        price = t["price_manwon"]
        rows.append(_make_row(
            lat, lng, "실거래", t["name"],
            info1=f"{t['area_sqm']}㎡ | {t['floor']}층",
            info2=f"거래가 {price:,}만원" if isinstance(price, int) else f"거래가 {price}만원",
            info3=f"{t['deal_year']}-{t['deal_month']:02d}-{t['deal_day']:02d} | {t['build_year'] or '-'}년식",
            color=_C["transaction"],
        ))
    return rows


def _zone_rows(district: str, recs: List[dict]) -> List[dict]:
    center = DISTRICT_CENTERS.get(district, SEOUL_CENTER)
    rows = []
    for z in recs:
        lat, lng = _geocode(f"서울특별시 {district} {z['address']}", center)
        score = z["score"] or 0
        color = _C["redev_high"] if score >= 80 else (_C["redev_mid"] if score >= 60 else _C["redev_low"])
        rows.append(_make_row(
            lat, lng, "재개발", z["name"],
            info1=f"{z['biz_type']} | {z['stage']}",
            info2=f"추천 {score:.0f}점 | 진행률 {z['progress']}%",
            info3=z["address"], color=color, radius=9,
        ))
    return rows


def _poi_rows(show_subway, show_school, show_hynix, show_samsung) -> List[dict]:
    rows = []
    if show_subway:
        for s in SUBWAY_STATIONS:
            rows.append(_make_row(s["lat"], s["lng"], "지하철역", s["name"],
                                  info1=s["line"], color=_C["subway"], radius=5))
    if show_school:
        for s in ELEMENTARY_SCHOOLS:
            rows.append(_make_row(s["lat"], s["lng"], "초등학교", s["name"],
                                  color=_C["school"], radius=5))
    if show_hynix:
        for s in [x for x in SHUTTLE_STOPS if x["company"] == "SK하이닉스"]:
            rows.append(_make_row(s["lat"], s["lng"], "SK하이닉스 셔틀", s["name"],
                                  color=_C["hynix"], radius=6))
    if show_samsung:
        for s in [x for x in SHUTTLE_STOPS if x["company"] == "삼성전자"]:
            rows.append(_make_row(s["lat"], s["lng"], "삼성전자 셔틀", s["name"],
                                  color=_C["samsung"], radius=6))
    return rows


# ── folium 지도 (출력 전용) ───────────────────────────────────────────────────
_PTL = JsCode("""
function(feature, latlng) {
    var p = feature.properties;
    return L.circleMarker(latlng, {
        radius: p.radius, fillColor: p.color,
        color: '#ffffff', weight: 1, fillOpacity: 0.85
    });
}
""")


def _build_map(center: Tuple[float, float], rows: List[dict]) -> folium.Map:
    m = folium.Map(location=list(center), zoom_start=14,
                   tiles="CartoDB positron", control_scale=True, prefer_canvas=True)
    if not rows:
        return m
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["lng"], r["lat"]]},
            "properties": {"label": r["label"], "name": r["name"],
                           "info1": r["info1"], "info2": r["info2"],
                           "color": r["color"], "radius": r["radius"]},
        }
        for r in rows
    ]
    folium.GeoJson(
        {"type": "FeatureCollection", "features": features},
        point_to_layer=_PTL,
        tooltip=folium.GeoJsonTooltip(
            fields=["label", "name", "info1", "info2"],
            aliases=["유형", "이름", "상세", "가격/점수"],
            sticky=True, labels=True, style="font-size:13px;padding:4px;",
        ),
    ).add_to(m)
    return m


@st.cache_resource
def _conn():
    return store.connect()


# ── UI ───────────────────────────────────────────────────────────────────────
st.title("🏠 부동산 전략 어시스턴트")
st.caption("스냅샷 DB에서 매물·실거래·재개발을 즉시 조회합니다. 지도는 결과 표시 전용입니다.")

conn = _conn()

with st.sidebar:
    st.markdown("### 🔍 조회")
    district = st.selectbox("자치구", DISTRICTS, index=DISTRICTS.index("광진구"))
    mode = st.radio("모드", MODE_OPTIONS, index=0, horizontal=True)
    deal_ymd = st.text_input("계약년월", value="202501")
    property_type = st.selectbox(
        "실거래 유형", list(PROPERTY_TYPES),
        format_func=lambda x: "연립다세대" if x == "villa" else "아파트",
    )
    st.divider()
    st.markdown("### 📍 지도 레이어")
    show_subway = st.checkbox("🚇 역세권 (지하철역)", value=True)
    show_school = st.checkbox("🏫 초품아 (초등학교)", value=True)
    show_hynix = st.checkbox("🚌 SK하이닉스 셔틀", value=True)
    show_samsung = st.checkbox("🚌 삼성전자 셔틀", value=True)
    st.divider()
    st.markdown("### 🔄 데이터 수집 (네트워크)")
    st.caption("외부 소스에서 가져와 DB에 저장합니다. 평소엔 불필요하며, 갱신이 필요할 때만 누르세요.")
    api_key = _get_secret("MOLIT_API_KEY")
    if not api_key:
        api_key = st.text_input("MOLIT API KEY", type="password",
                                help="실거래 수집에만 필요합니다.")
    if st.button("이 구 수집", use_container_width=True):
        with st.spinner(f"{district} 수집 중..."):
            kinds = ["매물", "재개발"] + (["실거래"] if api_key else [])
            results = collect_mod.collect_district(
                conn, district, deal_ymd=deal_ymd, property_type=property_type,
                api_key=api_key, kinds=kinds,
            )
        for r in results:
            (st.success if r.ok else st.warning)(f"{r.kind}: {r.count}건 {r.symptom}".strip())
        st.rerun()

# ── 조회 (DB 읽기, 네트워크 없음) ─────────────────────────────────────────────
map_rows: List[dict] = []
table_rows: List[Dict] = []
notes: List[str] = []

if mode in ("통합", "매물"):
    recs = store.load_listings(conn, district)
    rows = _listing_rows(district, recs)
    map_rows += rows
    table_rows += [{"구분": "매물", "건물명": r["name"], "면적/층": r["info1"],
                    "가격": r["info2"], "비고": r["info3"]} for r in rows]
    if not recs:
        notes.append("매물 스냅샷이 없습니다 — 사이드바 '이 구 수집'을 실행하세요.")

if mode in ("통합", "실거래"):
    recs = store.load_transactions(conn, district, deal_ymd, property_type)
    rows = _transaction_rows(district, recs)
    map_rows += rows
    table_rows += [{"구분": "실거래", "건물명": r["name"], "면적/층": r["info1"],
                    "가격": r["info2"], "비고": r["info3"]} for r in rows]
    if not recs:
        notes.append(f"실거래 스냅샷이 없습니다 ({deal_ymd}/{property_type}).")

if mode in ("통합", "재개발"):
    recs = store.load_zones(conn, district)
    rows = _zone_rows(district, recs)
    map_rows += rows
    table_rows += [{"구분": "재개발", "건물명": r["name"], "면적/층": r["info1"],
                    "가격": r["info2"], "비고": r["info3"]} for r in rows]
    if not recs:
        notes.append("재개발 스냅샷이 없습니다.")

for n in notes:
    st.info(n)

# ── 수집 현황 (출처 인식) ─────────────────────────────────────────────────────
status = store.collection_status(conn, district)
if status:
    chips = " · ".join(
        f"{s['kind']} {s['count']}건 ({s['collected_at'][:16].replace('T', ' ')})"
        for s in status
    )
    st.caption(f"📦 {district} 스냅샷: {chips}")

# ── 지도 (결과 표시 전용, 패닝해도 rerun 없음) ───────────────────────────────
poi_rows = _poi_rows(show_subway, show_school, show_hynix, show_samsung)
all_rows = map_rows + poi_rows
center = DISTRICT_CENTERS.get(district, SEOUL_CENTER)

map_sig = hash((district, tuple((round(r["lat"], 5), round(r["lng"], 5), r["color"]) for r in all_rows)))
cache = st.session_state.get("_map_cache")
if not cache or cache["sig"] != map_sig:
    fmap = _build_map(center, all_rows)
    st.session_state["_map_cache"] = {"sig": map_sig, "map": fmap}
else:
    fmap = cache["map"]

# returned_objects=[] → 지도 인터랙션이 rerun을 유발하지 않습니다 (출력 전용).
st_folium(fmap, key="map", height=560, use_container_width=True, returned_objects=[])

# ── 요약 + 테이블 ─────────────────────────────────────────────────────────────
if table_rows:
    counts: Dict[str, int] = {}
    for r in table_rows:
        counts[r["구분"]] = counts.get(r["구분"], 0) + 1
    cols = st.columns(len(counts))
    for col, (k, v) in zip(cols, counts.items()):
        col.metric(k, f"{v}건")
    st.divider()
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True, height=360)
elif not notes:
    st.info("사이드바에서 자치구와 모드를 선택하세요. 데이터가 없으면 '이 구 수집'을 실행하세요.")
