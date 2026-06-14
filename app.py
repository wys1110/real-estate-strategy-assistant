"""Streamlit 부동산 전략 어시스턴트 웹앱.

자양동 빌라/연립/다세대 매물 호가(부동산뱅크) + 실거래가(국토부 API)를
웹에서 조회·비교합니다.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request

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

st.set_page_config(page_title="부동산 전략 어시스턴트", page_icon="🏠", layout="wide")
st.title("부동산 전략 어시스턴트")
st.caption("자양동 빌라/연립/다세대 — 매물 호가 + 실거래가 비교")


def _get_secret(key: str, default: str = "") -> str:
    """st.secrets → os.environ 순서로 시크릿을 읽습니다."""
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return os.environ.get(key, default)

JAYANG_CENTER = (37.5350, 127.0700)


def _nominatim_search(address):
    """Nominatim 지오코딩. 실패 시 None."""
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


def _approx_coords(seed):
    """이름 해시 기반 근사 좌표."""
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    return (
        JAYANG_CENTER[0] + ((h % 1000) - 500) * 0.000006,
        JAYANG_CENTER[1] + (((h >> 10) % 1000) - 500) * 0.000006,
    )


def _geocode(address):
    """주소 → ((lat, lon), is_exact). session_state 캐시 사용."""
    cache = st.session_state.setdefault("_geo_cache", {})
    if address in cache:
        return cache[address]
    coords = _nominatim_search(address)
    if coords:
        cache[address] = (coords, True)
        time.sleep(1.1)
    else:
        cache[address] = (_approx_coords(address), False)
    return cache[address]


REGION_OPTIONS = {
    "서울 광진구 자양동": "1121510500",
}
LAWD_OPTIONS = {
    "서울 광진구 (11215)": "11215",
}

tab_listing, tab_tx, tab_compare, tab_map = st.tabs(["📋 매물 호가", "💰 실거래가", "🔍 비교", "🗺️ 지도"])

# ── 매물 호가 (부동산뱅크) ──
with tab_listing:
    st.subheader("현재 매물 호가 (부동산뱅크)")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        region_name = st.selectbox("지역", list(REGION_OPTIONS.keys()), key="listing_region")
    with col2:
        limit = st.number_input("조회 건수", min_value=1, max_value=100, value=20, key="listing_limit")
    with col3:
        include_all = st.checkbox("전체 유형 포함", key="listing_all_types")

    if st.button("매물 조회", key="btn_listing", type="primary"):
        region_code = REGION_OPTIONS[region_name]
        with st.spinner("부동산뱅크에서 매물 정보를 가져오는 중..."):
            try:
                source_url = build_list_url(region_code)
                html = fetch_html(source_url)
                listings = parse_listings(html, source_url=source_url)
                if not include_all:
                    listings = filter_villas(listings)
                listings = listings[:limit]

                if not listings:
                    st.warning("조회된 매물이 없습니다.")
                else:
                    rows = []
                    for li in listings:
                        rows.append({
                            "건물명": li.name,
                            "유형": li.listing_type,
                            "면적(㎡)": li.area_sqm,
                            "층": li.floor,
                            "호가(만원)": li.price_manwon,
                            "비고": li.note[:60],
                            "상세": li.detail_url,
                        })
                    df = pd.DataFrame(rows)
                    st.dataframe(
                        df,
                        use_container_width=True,
                        column_config={"상세": st.column_config.LinkColumn("상세")},
                    )
                    st.info(f"총 {len(listings)}건 조회 (data_type: current_listing)")
            except Exception as e:
                st.error(f"조회 실패: {e}")

# ── 실거래가 (국토부 API) ──
with tab_tx:
    st.subheader("실거래가 (국토교통부 공공데이터)")

    api_key = st.text_input(
        "MOLIT API KEY",
        value=_get_secret("MOLIT_API_KEY"),
        type="password",
        help="공공데이터포털 일반 인증키. Streamlit Cloud에서는 Settings > Secrets에 설정.",
        key="molit_key",
    )

    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1:
        lawd_name = st.selectbox("지역", list(LAWD_OPTIONS.keys()), key="tx_region")
    with col2:
        deal_ymd = st.text_input("계약년월 (YYYYMM)", value="202605", key="tx_ymd")
    with col3:
        prop_type = st.selectbox("유형", list(PROPERTY_TYPES), format_func=lambda x: "연립다세대" if x == "villa" else "아파트", key="tx_type")
    with col4:
        tx_limit = st.number_input("조회 건수", min_value=1, max_value=500, value=50, key="tx_limit")

    if st.button("실거래가 조회", key="btn_tx", type="primary"):
        effective_key = api_key or _get_secret("MOLIT_API_KEY")
        if not effective_key:
            st.error("API 키를 입력하거나 환경변수 MOLIT_API_KEY를 설정하세요.")
        else:
            lawd_cd = LAWD_OPTIONS[lawd_name]
            with st.spinner("국토부 API에서 실거래가를 조회하는 중..."):
                try:
                    txs = fetch_transactions(
                        lawd_cd=lawd_cd,
                        deal_ymd=deal_ymd,
                        property_type=prop_type,
                        api_key=effective_key,
                    )
                    txs = txs[:tx_limit]

                    if not txs:
                        st.warning("조회된 거래 내역이 없습니다.")
                    else:
                        rows = []
                        for t in txs:
                            rows.append({
                                "거래일": f"{t.deal_year}-{t.deal_month:02d}-{t.deal_day:02d}",
                                "건물명": t.name,
                                "법정동": t.dong,
                                "면적(㎡)": t.area_sqm,
                                "층": t.floor if t.floor is not None else "-",
                                "거래가(만원)": f"{t.price_manwon:,}",
                                "건축년도": t.build_year if t.build_year else "-",
                            })
                        df = pd.DataFrame(rows)
                        st.dataframe(df, use_container_width=True)
                        st.info(f"총 {len(txs)}건 조회 (data_type: actual_transaction)")
                except Exception as e:
                    st.error(f"조회 실패: {e}")

# ── 비교 탭 ──
with tab_compare:
    st.subheader("매물 호가 vs 실거래가 비교")
    st.markdown("""
    **사용법**: 위 두 탭에서 각각 매물 호가와 실거래가를 조회한 뒤,
    아래 버튼으로 최신 스냅샷 데이터와 비교할 수 있습니다.
    """)

    if st.button("최신 스냅샷 불러오기", key="btn_snapshot"):
        snapshot_path = os.path.join(os.path.dirname(__file__), "snapshots", "latest-jayang-villas.json")
        try:
            with open(snapshot_path, encoding="utf-8") as f:
                snap = json.load(f)

            st.caption(f"스냅샷 생성 시각: {snap.get('generated_at_kst', 'N/A')}")

            listings_data = snap.get("listings", [])
            if not listings_data:
                st.warning("스냅샷에 매물 데이터가 없습니다.")
            else:
                rows = []
                for li in listings_data:
                    rows.append({
                        "건물명": li.get("name", ""),
                        "유형": li.get("listing_type", ""),
                        "면적(㎡)": li.get("area_sqm", ""),
                        "층": li.get("floor", ""),
                        "호가(만원)": li.get("price_manwon", ""),
                        "비고": (li.get("note", ""))[:60],
                    })
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True)
                st.info(f"스냅샷 매물 {len(listings_data)}건 (data_type: current_listing)")

                if listings_data:
                    prices = [li.get("price_krw", 0) for li in listings_data if li.get("price_krw")]
                    if prices:
                        min_p = min(prices)
                        max_p = max(prices)
                        avg_p = sum(prices) / len(prices)
                        col1, col2, col3 = st.columns(3)
                        col1.metric("최저 호가", f"{min_p // 10000:,}만원")
                        col2.metric("최고 호가", f"{max_p // 10000:,}만원")
                        col3.metric("평균 호가", f"{avg_p // 10000:,.0f}만원")
        except FileNotFoundError:
            st.error("스냅샷 파일이 없습니다. CLI로 먼저 매물을 조회하세요.")
        except Exception as e:
            st.error(f"스냅샷 로드 실패: {e}")

# ── 지도 탭 ──
with tab_map:
    st.subheader("매물/실거래가 지도")

    col1, col2 = st.columns(2)
    with col1:
        show_listings = st.checkbox("매물 호가 (빨간 핀)", value=True, key="map_show_listings")
    with col2:
        show_tx = st.checkbox("실거래가 (파란 핀)", value=False, key="map_show_tx")

    if show_tx:
        mc1, mc2 = st.columns(2)
        with mc1:
            map_deal_ymd = st.text_input("계약년월", value="202605", key="map_ymd")
        with mc2:
            map_prop_type = st.selectbox(
                "유형", list(PROPERTY_TYPES),
                format_func=lambda x: "연립다세대" if x == "villa" else "아파트",
                key="map_type",
            )

    if st.button("지도에 표시", key="btn_map", type="primary"):
        pins = []

        if show_listings:
            with st.spinner("매물 조회 중..."):
                try:
                    url = build_list_url()
                    html = fetch_html(url)
                    listings = filter_villas(parse_listings(html, source_url=url))
                    for li in listings:
                        pins.append({
                            "address": "서울특별시 광진구 자양동 " + li.name,
                            "label": li.name,
                            "price": li.price_manwon + "만원",
                            "detail": f"면적: {li.area_sqm}㎡ | 층: {li.floor}",
                            "type": "listing",
                        })
                except Exception as e:
                    st.error(f"매물 조회 실패: {e}")

        if show_tx:
            api_key_val = _get_secret("MOLIT_API_KEY")
            if not api_key_val:
                st.error("실거래가 조회에는 MOLIT API KEY가 필요합니다. (실거래가 탭 또는 Secrets에 설정)")
            else:
                with st.spinner("실거래가 조회 중..."):
                    try:
                        txs = fetch_transactions(
                            lawd_cd="11215", deal_ymd=map_deal_ymd,
                            property_type=map_prop_type, api_key=api_key_val,
                        )
                        for t in txs:
                            pins.append({
                                "address": f"서울특별시 광진구 {t.dong} {t.lot_number}",
                                "label": t.name,
                                "price": f"{t.price_manwon:,}만원",
                                "detail": f"거래일: {t.deal_year}-{t.deal_month:02d}-{t.deal_day:02d} | {t.area_sqm}㎡ | {t.floor}층",
                                "type": "tx",
                            })
                    except Exception as e:
                        st.error(f"실거래가 조회 실패: {e}")

        if pins:
            unique_addrs = list(set(p["address"] for p in pins))
            progress = st.progress(0, text="주소를 좌표로 변환 중...")
            coords_map = {}
            for i, addr in enumerate(unique_addrs):
                progress.progress((i + 1) / len(unique_addrs), text=f"지오코딩 {i+1}/{len(unique_addrs)}")
                coords_map[addr] = _geocode(addr)
            progress.empty()

            m = folium.Map(location=list(JAYANG_CENTER), zoom_start=15)
            exact_count = 0
            for pin in pins:
                (lat, lon), is_exact = coords_map[pin["address"]]
                exact_count += int(is_exact)
                color = "red" if pin["type"] == "listing" else "blue"
                icon_name = "home" if pin["type"] == "listing" else "won-sign"
                popup_html = f"<b>{pin['label']}</b><br>{pin['price']}<br>{pin['detail']}"
                if not is_exact:
                    popup_html += "<br><i>(근사 위치)</i>"
                folium.Marker(
                    [lat, lon],
                    popup=folium.Popup(popup_html, max_width=250),
                    icon=folium.Icon(color=color, icon=icon_name, prefix="fa"),
                    tooltip=pin["label"],
                ).add_to(m)

            st_folium(m, height=500, use_container_width=True)

            listing_count = sum(1 for p in pins if p["type"] == "listing")
            tx_count = sum(1 for p in pins if p["type"] == "tx")
            st.caption(
                f"매물 {listing_count}건 (빨강) | 실거래 {tx_count}건 (파랑) | "
                f"정확 좌표 {exact_count}건, 근사 좌표 {len(pins) - exact_count}건"
            )
        elif not pins:
            st.info("표시할 데이터가 없습니다. 위 체크박스를 선택하고 버튼을 누르세요.")

# ── 사이드바 ──
with st.sidebar:
    st.markdown("### 데이터 출처")
    st.markdown("""
    - **매물 호가**: [부동산뱅크](https://www.neonet.co.kr) (현재 매물)
    - **실거래가**: [국토교통부 공공데이터](https://www.data.go.kr) (신고 실거래)
    """)
    st.divider()
    st.markdown("### 참고")
    st.markdown("""
    - 호가는 `current_listing` 타입, 실거래가는 `actual_transaction` 타입입니다.
    - 부동산뱅크 데이터는 HTML 파싱 기반이므로 불안정할 수 있습니다.
    - 실거래가 조회에는 공공데이터포털 API 키가 필요합니다.
    """)
