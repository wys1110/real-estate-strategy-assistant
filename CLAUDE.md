# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

한국 주택 매물 호가와 실거래가를 조합해 투자/매수 후보를 비교하는 부동산 전략 어시스턴트입니다.
범위: 매물 수집, 소스 비교, 정비사업 분석. CRM/중개 시스템으로 확장하지 않습니다.

## Commands

```bash
# 컴파일 체크 (변경 후 항상 실행)
python3 -m compileall src

# CLI — 매물/실거래 직접 조회 (네트워크 필요)
PYTHONPATH=src python3 -m real_estate_strategy.cli fetch --limit 12
PYTHONPATH=src python3 -m real_estate_strategy.cli fetch --format json --limit 5
MOLIT_API_KEY=... PYTHONPATH=src python3 -m real_estate_strategy.cli transactions --deal-ymd 202605 --type villa

# 배치 수집 → SQLite 스냅샷 (앱은 이 DB만 읽음)
PYTHONPATH=src python3 -m real_estate_strategy.cli collect --all --deal-ymd 202501
PYTHONPATH=src python3 -m real_estate_strategy.cli collect --district 광진구 --kinds 매물,재개발
MOLIT_API_KEY=... PYTHONPATH=src python3 -m real_estate_strategy.cli collect --district 광진구 --deal-ymd 202501

# 테스트
PYTHONPATH=src python3 -m unittest tests/test_cli.py
PYTHONPATH=src python3 -m unittest tests/test_redevelopment.py
PYTHONPATH=src python3 -m unittest discover tests

# Streamlit 웹앱
.venv/bin/streamlit run app.py
```

## Architecture

**3계층 분리**: 수집(배치) ↔ 저장(SQLite) ↔ 조회(앱). 조회 시점에 네트워크를 사용하지 않아 즉시 응답합니다.

```
cli collect (배치)
    ↓ collect.py
각 소스 (BudongsanBank / MOLIT / cleanup.seoul.go.kr)
    ↓ store.py
snapshots/realestate.db  (git 무시 대상)
    ↓ store.load_*
app.py  (읽기 전용, 네트워크 0)
```

`app.py`는 지도를 **결과 표시 전용**으로만 씁니다 (`returned_objects=[]`로 패닝/줌 rerun 없음). 검색은 자치구 selectbox로 합니다.

## Source Boundaries

| 파일 | 역할 | 비고 |
|---|---|---|
| `budongsanbank.py` | 부동산뱅크 HTML 파싱 → 매물 호가 | `price_manwon`은 `str` 타입 (포맷 지정자 `:,` 불가) |
| `molit.py` | 국토부 공공데이터포털 XML API → 실거래 | `MOLIT_API_KEY` 환경변수, serviceKey는 URL에 직접 삽입(이중인코딩 방지) |
| `redevelopment.py` | cleanup.seoul.go.kr HTML → 정비사업 구역 | `DISTRICT_CODES`: 구명 → 5자리 코드 |
| `store.py` | stdlib sqlite3 스냅샷 | `save_*` → `load_*` 쌍, `record_failure()` |
| `collect.py` | 배치 수집 오케스트레이션 | 실패 시 증상 기록, 조용한 폴백 금지 |
| `poi.py` | 지하철역·초등학교·셔틀버스 정류장 정적 데이터 | |
| `cli.py` | `fetch` / `transactions` / `collect` 서브커맨드 | |

## Key Constraints

- **stdlib Python만 사용** — 런타임 third-party 의존성 없음 (`store.py`, `collect.py` 포함).
- **스크래핑 데이터는 불안정** — `source` URL과 `fetched_at` 타임스탬프를 항상 보존.
- **API 키 보안** — `MOLIT_API_KEY`는 환경변수 또는 Streamlit secrets. 예외 메시지·문서·커밋에 원문 기록 금지.
- **소량 수집** — 페이지 단위로만 fetch, 전체 크롤링 금지.
- **MOLIT API 불안정** — 동일 파라미터에서 간헐적 403 발생. 현재 최대 5회 exponential backoff 재시도 구현됨.

## Data Types (출처 구분)

- `current_listing` — 부동산뱅크 매물 호가 (HTML 파싱)
- `actual_transaction` — 국토부 신고 실거래가 (공식 API)
- `index/statistic` — 향후 REB 통계 모듈 (미구현)
- `manual_note` — 사용자 입력

## BudongsanBank Region Codes

10자리 법정동코드 (시도 2 + 시군구 3 + 읍면동 3 + 리 2). `collect.py`의 `BBANK_CODES` dict에 25개 구 등록. **광진구 자양동 `1121510500`만 실제 동작 확인됨**, 나머지는 추정값 (`읍면동 101 + 리 00`).

## SQLite Schema (snapshots/realestate.db)

`listings` / `transactions` / `zones` / `collections` 4개 테이블. `collections` 테이블이 구·종류별 마지막 수집 현황(성공/실패 증상)을 기록합니다.

## Verification Checklist

변경 후 반드시 확인:
- `python3 -m compileall src` 통과
- CLI 수집 함수 변경 시 `collect` 또는 `fetch`/`transactions` 실행
- `store.py` 변경 시 `save_*` → `load_*` 라운드트립 확인 (스모크 테스트: synthetic data)
- `collect.py` 변경 시 실패 시 `record_failure` 호출 여부 확인 (조용한 폴백 금지)
- `budongsanbank.py` 변경 시: 결과에 `listing_id`, `listing_type`, `name`, `area_sqm`, `floor`, `price_manwon` 포함 확인
- 새 소스 추가 시 `docs/api-setup.md` 및 Source Boundaries 업데이트
