"""Streamlit 부동산 전략 어시스턴트 웹앱.

자양동 빌라/연립/다세대 매물 호가(부동산뱅크) + 실거래가(국토부 API)를
웹에서 조회·비교합니다.
"""
from __future__ import annotations

import dataclasses
import os
import sys

import pandas as pd
import streamlit as st

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

REGION_OPTIONS = {
    "서울 광진구 자양동": "1121510500",
}
LAWD_OPTIONS = {
    "서울 광진구 (11215)": "11215",
}

tab_listing, tab_tx, tab_compare = st.tabs(["📋 매물 호가", "💰 실거래가", "🔍 비교"])

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
        import json
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
