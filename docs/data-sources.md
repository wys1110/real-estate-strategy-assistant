# 데이터 소스

## 1. 현재 매물 호가

### 부동산뱅크

- 용도: 현재 올라온 매물 호가 샘플 조회
- 방식: 서버 렌더링 HTML iframe 파싱
- 상태: 2026-06-14 자양동 매매 페이지 접근 및 파싱 확인
- 장점: 로그인 없이 HTML 접근 가능
- 리스크: HTML 구조 변경, 서비스 약관, 중복 매물, 허위/낚시 매물 가능성

테스트 URL:

```text
https://www.neonet.co.kr/novo-rebank/view/offerings/OfferingsList.neo?offer_gbn=P&offerings_gbn=SH&region_cd=1121510500&sub_offerings_gbn=
```

실제 파싱 URL:

```text
https://www.neonet.co.kr/novo-rebank/view/offerings/inc_OfferingsList.neo?offerings_gbn=SH&sub_offerings_gbn=&complex_cd=&offer_gbn=P&region_cd=1121510500&list_gbn=&agency_cd=&area=&price=&area_min=&area_max=&price_min=&price_max=&price_month=&price_month_min=&price_month_max=&building_no=&pyung_cd=&sort_list=&prc_sort=
```

### 네이버부동산

- 용도: 현재 매물 호가
- 상태: 공식 공개 API 아님
- 2026-06-14 테스트 결과:
  - `new.land.naver.com/api/articles...` 호출은 `429 TOO_MANY_REQUESTS`
  - `m.land.naver.com/cluster/ajax/articleList...` 호출은 `HTTP 200`, 본문 `null`
- 결론: 운영 소스로 바로 쓰기 어렵고, 제휴/상용 API 또는 브라우저 기반 수동 확인이 더 안전합니다.

## 2. 실거래가

### 국토교통부 공공데이터포털

- 용도: 신고된 실거래가
- 데이터: 아파트/연립/다세대/단독/다가구/오피스텔 등 매매 및 전월세
- 장점: 공식, 무료, 법적 리스크 낮음
- 한계: 현재 호가가 아니라 신고된 거래 데이터
- 현재 구현: 연립다세대 매매, 아파트 매매

주요 후보:

- 국토교통부 연립다세대 매매 실거래가 자료: `apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade`
- 국토교통부 아파트 매매 실거래가 자료: `apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade`
- 국토교통부 실거래가 공개시스템: `https://rt.molit.go.kr/`

실행:

```bash
export MOLIT_API_KEY=공공데이터포털_일반_인증키
PYTHONPATH=src python3 -m real_estate_strategy.cli transactions --deal-ymd 202605 --type villa
PYTHONPATH=src python3 -m real_estate_strategy.cli transactions --deal-ymd 202605 --type apt
```

## 3. 시세/통계

### 한국부동산원

- 용도: 지역별 시장 흐름, 가격지수, 거래현황
- 장점: 공식 통계
- 한계: 개별 현재 매물이 아님

### KB/상용 데이터

- 용도: 시세, 추정가, 부동산 정보 통합
- 접근: 제휴 또는 상용 API 필요 가능성 높음
- 예: 하이픈 부동산정보 조회 API는 스크래핑 방식 상품으로 KB시세/네이버부동산정보 등을 제공한다고 안내합니다.
