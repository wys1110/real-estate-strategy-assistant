"""Streamlit 부동산 전략 어시스턴트 웹앱.

지도를 움직여 검색 위치(자치구)를 정하고, 사이드바에서 레이어
(역세권·초품아·SK하이닉스/삼성전자 셔틀)를 켜서 비교합니다.
"""
from __future__ import annotations

import concurrent.futures as cf
import functools
import hashlib
import os
import sys
import threading
import time
from typing import Callable, Dict, List, Sequence, Tuple

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
from real_estate_strategy.poi import ELEMENTARY_SCHOOLS, SHUTTLE_STOPS, SUBWAY_STATIONS


st.set_page_config(page_title="부동산 전략 어시스턴트", page_icon="🏠", layout="wide")
st.markdown("<style>.block-container{padding-top:1.5rem}</style>", unsafe_allow_html=True)

SEOUL_CENTER = (37.5665, 126.9780)
MODE_OPTIONS = ["통합", "매물", "실거래", "재개발"]
GEO_CACHE_VERSION = "v7"

# BudongsanBank region_cd = 시도(2) + 시군구(3) + 읍면동(3) + 리(2) = 10자리 법정동코드
# 읍면동 '101' + 리 '00' → 각 구 첫 번째 법정동으로 추정.
# 광진구 자양동(105)만 실제 동작이 확인됨.
# 결과가 비면 해당 구의 법정동 코드를 확인해 이 dict에 직접 등록하세요.
BBANK_CODES: Dict[str, str] = {
    "종로구":   "1111010100",
    "중구":     "1114010100",
    "용산구":   "1117010100",
    "성동구":   "1120010100",
    "광진구":   "1121510500",   # 자양동 ✓ 확인됨
    "동대문구": "1123010100",
    "중랑구":   "1126010100",
    "성북구":   "1129010100",
    "강북구":   "1130510100",
    "도봉구":   "1132010100",
    "노원구":   "1135010100",
    "은평구":   "1138010100",
    "서대문구": "1141010100",
    "마포구":   "1144010100",
    "양천구":   "1147010100",
    "강서구":   "1150010100",
    "구로구":   "1153010100",
    "금천구":   "1154510100",
    "영등포구": "1156010100",
    "동작구":   "1159010100",
    "관악구":   "1162010100",
    "서초구":   "1165010100",
    "강남구":   "1168010100",   # 압구정동 (URL 패턴 확인)
    "송파구":   "1171010100",
    "강동구":   "1174010100",
}

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

# ── 색상 (folium 마커용 hex) ──────────────────────────────────────────────────
_C = {
    "listing":     "#dc3232",
    "transaction": "#1e78dc",
    "redev_high":  "#b40000",
    "redev_mid":   "#ff8c00",
    "redev_low":   "#00b450",
    "subway":      "#ffa500",
    "school":      "#00a050",
    "hynix":       "#9400d3",
    "samsung":     "#0050b4",
}


def _get_secret(key: str, default: str = "") -> str:
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return os.environ.get(key, default)


# ── 위치 추정 ─────────────────────────────────────────────────────────────────
def _nearest_district(lat: float, lng: float) -> str:
    """지도 중심 좌표에서 가장 가까운 자치구를 찾습니다."""
    best, best_d = "광진구", float("inf")
    for name, (dla, dln) in DISTRICT_CENTERS.items():
        d = (lat - dla) ** 2 + (lng - dln) ** 2
        if d < best_d:
            best_d, best = d, name
    return best


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


# 지오코딩 결과는 결정적(주소→고정 좌표)이라 프로세스 전역 캐시로 둡니다.
# (st.session_state에 의존하지 않으므로 워커 스레드에서도 안전하게 호출 가능)
_GEO_CACHE: Dict[str, Tuple[float, float]] = {}


def _geocode(address: str, center: Tuple[float, float]) -> Tuple[float, float]:
    cache_key = f"{GEO_CACHE_VERSION}::{address}"
    coords = _GEO_CACHE.get(cache_key)
    if coords is None:
        anchor, radius = _address_anchor(address, center)
        coords = _approx_coords(address, anchor, radius)
        _GEO_CACHE[cache_key] = coords
    return coords


# ── 경량 TTL 캐시 ─────────────────────────────────────────────────────────────
# 동일 조건 재조회 시 네트워크 왕복을 건너뜁니다. 스레드에서 호출되므로
# st.cache_data 대신 직접 구현 (st.* 호출은 ScriptRunContext가 없는 스레드에서 실패).
_NET_CACHE: Dict[tuple, Tuple[float, object]] = {}
_NET_CACHE_LOCK = threading.Lock()
_NET_CACHE_TTL = 600  # 초


def _ttl_cache(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(*args):
        key = (fn.__name__, args)
        now = time.time()
        with _NET_CACHE_LOCK:
            hit = _NET_CACHE.get(key)
            if hit and now - hit[0] < _NET_CACHE_TTL:
                return hit[1]
        value = fn(*args)
        with _NET_CACHE_LOCK:
            _NET_CACHE[key] = (now, value)
        return value

    return wrapper


def _make_row(lat, lng, label, name, info1="", info2="", info3="", color="#666", radius=7):
    return dict(lat=lat, lng=lng, label=label, name=name,
                info1=info1, info2=info2, info3=info3, color=color, radius=radius)


# ── 데이터 수집 (TTL 캐시 + 병렬 호출 안전) ──────────────────────────────────
@_ttl_cache
def _listing_rows(district: str, limit: int) -> List[dict]:
    region_code = BBANK_CODES.get(district)
    if not region_code:
        raise ValueError(f"{district} region code 미등록")
    center = DISTRICT_CENTERS.get(district, SEOUL_CENTER)
    url = build_list_url(region_code)
    all_listings = parse_listings(fetch_html(url), source_url=url)
    listings = filter_villas(all_listings)[:limit]
    if not listings and all_listings:
        # 매물은 있지만 빌라/연립만 필터하면 0건 → 전체 포함
        listings = all_listings[:limit]
    rows = []
    for li in listings:
        lat, lng = _geocode(f"서울특별시 {district} {li.name}", center)
        rows.append(_make_row(
            lat, lng, "🔴 매물 (호가)", li.name,
            info1=f"{li.area_sqm}㎡ | {li.floor}층",
            info2=f"호가 {li.price_manwon}만원",
            info3=li.note[:60],
            color=_C["listing"],
        ))
    return rows


@_ttl_cache
def _transaction_rows(district: str, api_key: str, deal_ymd: str, property_type: str, limit: int) -> List[dict]:
    lawd_cd = DISTRICT_CODES.get(district, "11215")
    center = DISTRICT_CENTERS.get(district, SEOUL_CENTER)
    txs = fetch_transactions(
        lawd_cd=lawd_cd,
        deal_ymd=deal_ymd, property_type=property_type,
        api_key=api_key,
        num_of_rows=min(1000, max(limit, 100)),  # API 최대 1000건까지 요청
    )[:limit]
    rows = []
    for t in txs:
        addr = f"서울특별시 {district} {t.dong} {t.lot_number}"
        lat, lng = _geocode(addr, center)
        rows.append(_make_row(
            lat, lng, "🔵 실거래", t.name,
            info1=f"{t.area_sqm}㎡ | {t.floor}층",
            info2=f"거래가 {t.price_manwon:,}만원",
            info3=f"{t.deal_year}-{t.deal_month:02d}-{t.deal_day:02d} | {t.build_year or '-'}년식",
            color=_C["transaction"],
        ))
    return rows


@_ttl_cache
def _redevelopment_rows(districts: Sequence[str], stages: Sequence[str], only_redev: bool, limit: int) -> List[dict]:
    # 구별 정보몽땅 조회를 병렬 처리 (각 구가 독립 네트워크 호출)
    zones = []
    if districts:
        with cf.ThreadPoolExecutor(max_workers=min(8, len(districts))) as ex:
            futures = [ex.submit(fetch_zones, DISTRICT_CODES[d], 1, 200) for d in districts]
            for fut in cf.as_completed(futures):
                try:
                    fetched, _ = fut.result()
                    zones.extend(fetched)
                except Exception:
                    continue
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
            color=color, radius=9,
        ))
    return rows


def _poi_rows(show_subway: bool, show_school: bool, show_hynix: bool, show_samsung: bool) -> List[dict]:
    rows = []
    if show_subway:
        for s in SUBWAY_STATIONS:
            rows.append(_make_row(s["lat"], s["lng"], "🚇 지하철역", s["name"],
                                  info1=s["line"], color=_C["subway"], radius=5))
    if show_school:
        for s in ELEMENTARY_SCHOOLS:
            rows.append(_make_row(s["lat"], s["lng"], "🏫 초등학교", s["name"],
                                  color=_C["school"], radius=5))
    if show_hynix:
        for s in [x for x in SHUTTLE_STOPS if x["company"] == "SK하이닉스"]:
            rows.append(_make_row(s["lat"], s["lng"], "🚌 SK하이닉스 셔틀", s["name"],
                                  color=_C["hynix"], radius=6))
    if show_samsung:
        for s in [x for x in SHUTTLE_STOPS if x["company"] == "삼성전자"]:
            rows.append(_make_row(s["lat"], s["lng"], "🚌 삼성전자 셔틀", s["name"],
                                  color=_C["samsung"], radius=6))
    return rows


# ── folium 지도 ───────────────────────────────────────────────────────────────
def _popup_html(r: dict) -> str:
    return (
        "<div style='font-size:13px;min-width:150px;max-width:230px'>"
        f"<span style='color:#888;font-size:11px'>{r['label']}</span><br>"
        f"<b style='font-size:14px'>{r['name']}</b><br>"
        f"{r['info1']}<br><b>{r['info2']}</b><br>"
        f"<span style='color:#555'>{r['info3']}</span></div>"
    )


def _build_map(center: Tuple[float, float], zoom: int, rows: List[dict]) -> folium.Map:
    # prefer_canvas=True → 마커를 캔버스에 일괄 렌더링해 수백~수천 개도 빠르게 그립니다.
    m = folium.Map(location=list(center), zoom_start=zoom,
                   tiles="CartoDB positron", control_scale=True, prefer_canvas=True)
    for r in rows:
        # 상세 정보는 popup 대신 tooltip 하나로 — 마커당 생성되는 DOM 요소를 줄여
        # 렌더링/직렬화 비용을 낮춥니다.
        folium.CircleMarker(
            location=[r["lat"], r["lng"]],
            radius=r["radius"],
            color="#ffffff", weight=1,
            fill=True, fill_color=r["color"], fill_opacity=0.85,
            tooltip=folium.Tooltip(_popup_html(r)),
        ).add_to(m)
    return m


# ── UI ───────────────────────────────────────────────────────────────────────
st.title("🏠 부동산 전략 어시스턴트")
st.caption("지도를 움직여 동네를 정하고, '이 위치 조회'로 매물·실거래·재개발을 한눈에 비교합니다.")

with st.sidebar:
    st.markdown("### 📊 데이터 출처")
    st.markdown(
        "- 🔴 부동산뱅크: 현재 매물 호가\n"
        "- 🔵 국토교통부: 신고 실거래가\n"
        "- ⭐ 서울시 정보몽땅: 정비사업"
    )
    st.divider()
    st.markdown("### 🔍 조회 옵션")
    listing_limit = st.number_input("매물 수", 1, 100, 100,
                                    help="부동산뱅크 1페이지에서 파싱되는 만큼 표시됩니다.")
    deal_ymd = st.text_input("계약년월", value="202501")
    property_type = st.selectbox(
        "실거래 유형", list(PROPERTY_TYPES),
        format_func=lambda x: "연립다세대" if x == "villa" else "아파트",
    )
    transaction_limit = st.number_input("실거래 수", 1, 1000, 1000,
                                        help="국토부 API 최대 1000건까지 조회합니다.")
    redev_limit = st.number_input("재개발 구역 수", 1, 500, 200)
    st.divider()
    st.markdown("### 📍 지도 레이어")
    show_subway  = st.checkbox("🚇 역세권 (지하철역)", value=True)
    show_school  = st.checkbox("🏫 초품아 (초등학교)", value=True)
    show_hynix   = st.checkbox("🚌 SK하이닉스 셔틀",  value=True)
    show_samsung = st.checkbox("🚌 삼성전자 셔틀",    value=True)

mode = st.radio("모드", MODE_OPTIONS, horizontal=True, index=0)

# 지도 view 상태 (사용자가 마지막으로 본 위치 유지)
view = st.session_state.setdefault(
    "view", {"center": list(DISTRICT_CENTERS["광진구"]), "zoom": 14}
)
cur_district = _nearest_district(view["center"][0], view["center"][1])

# 재개발은 여러 구 비교가 자연스러우므로 모드일 때만 멀티셀렉트 노출
if mode == "재개발":
    districts = st.multiselect(
        "재개발 자치구 (여러 구 비교 가능)", list(DISTRICT_CODES.keys()),
        default=[cur_district],
    )
    rc = st.columns([3, 1])
    with rc[0]:
        stages = st.multiselect("진행단계", STAGES, default=INVESTMENT_STAGES)
    with rc[1]:
        only_redev = st.checkbox("재개발만", value=False)
else:
    districts = [cur_district]
    stages = INVESTMENT_STAGES
    only_redev = False

api_key = _get_secret("MOLIT_API_KEY")
if mode in ("통합", "실거래") and not api_key:
    api_key = st.text_input("MOLIT API KEY", type="password", help="실거래가 조회에 필요합니다.")

loc = st.columns([3, 1])
with loc[0]:
    st.info(f"📍 현재 지도 중심: **{cur_district}** — 이 위치 기준으로 조회합니다.")
with loc[1]:
    go = st.button("🔍 이 위치 조회", type="primary", use_container_width=True)

if go:
    map_rows: List[dict] = []
    table_rows: List[Dict] = []
    errors: List[str] = []

    # 모드별로 필요한 조회 작업을 모은 뒤 병렬 실행 (서로 독립적인 네트워크 호출)
    tasks: Dict[str, Callable[[], List[dict]]] = {}
    if mode in ("통합", "매물"):
        tasks["매물"] = lambda: _listing_rows(cur_district, listing_limit)
    if mode in ("통합", "실거래"):
        if not api_key:
            errors.append("실거래가 조회에는 MOLIT API KEY가 필요합니다.")
        else:
            tasks["실거래"] = lambda: _transaction_rows(
                cur_district, api_key, deal_ymd, property_type, transaction_limit)
    if mode in ("통합", "재개발"):
        if not districts:
            errors.append("재개발 자치구를 1개 이상 선택하세요.")
        else:
            tasks["재개발"] = lambda: _redevelopment_rows(
                tuple(districts), tuple(stages), only_redev, redev_limit)

    results_by_kind: Dict[str, List[dict]] = {}
    if tasks:
        with st.spinner(f"조회 중... ({', '.join(tasks)})"):
            with cf.ThreadPoolExecutor(max_workers=len(tasks)) as ex:
                future_kind = {ex.submit(fn): kind for kind, fn in tasks.items()}
                for fut in cf.as_completed(future_kind):
                    kind = future_kind[fut]
                    try:
                        results_by_kind[kind] = fut.result()
                    except Exception as e:
                        errors.append(f"{kind} 조회 실패: {e}")

    # 테이블/지도는 항상 같은 순서로 모읍니다 (매물 → 실거래 → 재개발)
    for kind in ("매물", "실거래", "재개발"):
        rows = results_by_kind.get(kind)
        if not rows:
            if kind in tasks and kind not in results_by_kind:
                continue  # 위에서 에러 기록됨
            if kind in tasks:
                errors.append(f"{kind}: 결과가 없습니다 ({cur_district}).")
            continue
        map_rows.extend(rows)
        for r in rows:
            table_rows.append({"구분": kind, "건물명": r["name"],
                               "면적/층": r["info1"], "가격": r["info2"], "비고": r["info3"]})

    st.session_state["results"] = {"map_rows": map_rows, "table_rows": table_rows,
                                   "errors": errors, "mode": mode, "district": cur_district}
    st.rerun()

res = st.session_state.get("results", {"map_rows": [], "table_rows": [], "errors": [], "mode": mode})
for err in res["errors"]:
    st.warning(err)

# ── 지도 ─────────────────────────────────────────────────────────────────────
poi_rows = _poi_rows(show_subway, show_school, show_hynix, show_samsung)
all_rows = res["map_rows"] + poi_rows

# 지도는 데이터(마커)가 바뀔 때만 새로 만듭니다. 단순 패닝/줌으로 인한 rerun에서는
# 캐시된 지도 객체를 재사용해 수백~수천 마커를 매번 다시 만드는 비용을 없앱니다.
map_sig = hash(tuple((round(r["lat"], 5), round(r["lng"], 5), r["color"]) for r in all_rows))
cache = st.session_state.get("_map_cache")
if not cache or cache["sig"] != map_sig:
    fmap = _build_map(view["center"], view["zoom"], all_rows)
    st.session_state["_map_cache"] = {"sig": map_sig, "map": fmap}
else:
    fmap = cache["map"]

state = st_folium(fmap, key="map", height=560, use_container_width=True,
                  returned_objects=["center", "zoom"])

# 사용자가 지도를 움직이면 중심/줌을 저장 → 다음 조회 위치가 됨.
# st_folium 위젯 값이 바뀌면 Streamlit이 자동으로 rerun 하므로 명시적 rerun 불필요.
if state and state.get("center"):
    view["center"] = [state["center"]["lat"], state["center"]["lng"]]
    view["zoom"] = state.get("zoom") or view["zoom"]

# ── 요약 + 테이블 ─────────────────────────────────────────────────────────────
table_rows = res["table_rows"]
if table_rows:
    counts: Dict[str, int] = {}
    for r in table_rows:
        counts[r["구분"]] = counts.get(r["구분"], 0) + 1
    cols = st.columns(len(counts))
    for col, (k, v) in zip(cols, counts.items()):
        col.metric(k, f"{v}건")
    st.divider()
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True, height=360)
elif not res["errors"]:
    st.info("지도를 움직여 위치를 정하고 '🔍 이 위치 조회'를 눌러주세요.")
