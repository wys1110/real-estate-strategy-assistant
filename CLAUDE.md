# Claude Code Collaboration Guide

이 프로젝트는 부동산 전략 어시스턴트입니다. 현재 목적은 한국 주택 매물 호가와 실거래가를 조합해 투자/매수 후보를 비교하는 것입니다.

## Working Rules

- Keep the assistant narrow: listing collection, source comparison, strategy notes.
- Do not expand into a general CRM, broker system, or large web app unless explicitly requested.
- Prefer standard-library Python. Current code has no third-party runtime dependency.
- Treat scraped or HTML-parsed listing data as unstable. Always preserve source URL and fetch timestamp.
- Do not hide uncertainty. Mark data as `current_listing`, `actual_transaction`, `index/statistic`, or `manual_note`.
- Avoid aggressive crawling. Fetch only the requested page or small page ranges.
- Keep user-facing outputs source-aware: listing CSV output and Streamlit detail rows should expose source/fetched timestamp where available.

## Current Data Findings

As of 2026-06-14:

- Naver Real Estate internal JSON request returned `429 TOO_MANY_REQUESTS` in this environment.
- Mobile Naver cluster endpoint returned `HTTP 200` but body `null` for the tested parameters.
- BudongsanBank listing iframe returned HTML that includes listing rows and prices.
- For Jayang-dong sale listings, the parser found 30 first-page rows and 16 villa/row-house/multi-family rows.
- The latest saved listing snapshot is `snapshots/latest-jayang-villas.json`.
- The local `main` branch has integrated the newer Claude branch MOLIT code, with Python 3.7-compatible type hints.

## Main Commands

```bash
cd /Users/yongseokwon/dev/real-estate-strategy-assistant

# CLI
PYTHONPATH=src python3 -m real_estate_strategy.cli fetch --limit 12
PYTHONPATH=src python3 -m real_estate_strategy.cli fetch --format json --limit 5
MOLIT_API_KEY=... PYTHONPATH=src python3 -m real_estate_strategy.cli transactions --deal-ymd 202605 --type villa

# 배치 수집 → SQLite 스냅샷 (조회 앱은 이 DB만 읽음, 네트워크 없음)
PYTHONPATH=src python3 -m real_estate_strategy.cli collect --all --deal-ymd 202501
PYTHONPATH=src python3 -m real_estate_strategy.cli collect --district 광진구 --kinds 매물,재개발

# Streamlit 웹앱 (Python 3.12 venv)
.venv/bin/streamlit run app.py
```

## Architecture

수집(배치) ↔ 저장(SQLite) ↔ 조회(앱) 3계층 분리. 조회 시점에 네트워크를
사용하지 않아 즉시 응답합니다. 지도는 입력이 아니라 결과 표시 전용입니다.

- 수집: `cli collect` → `collect.py` 가 각 구의 매물/실거래/정비사업을 가져옴.
- 저장: `store.py` (stdlib `sqlite3`) → `snapshots/realestate.db`. 레코드마다
  `source`/`fetched_at`/`collected_at` 보존, 실패는 `collections.status`에 증상 기록.
- 조회: `app.py` 는 `store.load_*` 로 DB만 읽음. `snapshots/*.db` 는 git 무시 대상.

## Source Boundaries

- `budongsanbank.py`: current listing asking prices from HTML.
- `molit.py`: official actual transaction prices from MOLIT public data APIs.
- `redevelopment.py`: Seoul 정비사업 zones from cleanup.seoul.go.kr.
- `store.py`: SQLite snapshot persistence (stdlib only).
- `collect.py`: batch collection orchestration; records failure symptoms, no silent fallback.
- `docs/api-setup.md`: API endpoints, required parameters, and credential handling rules.
- Future REB module: market index/statistics, not individual listings.

## Verification Checklist

- Run the CLI after parser changes (`fetch`, `transactions`, `collect`).
- Confirm at least one listing has `listing_id`, `listing_type`, `name`, `area_sqm`, `floor`, and `price_manwon`.
- Confirm CSV listing output keeps `source` and `fetched_at`.
- After store/collect changes, verify SQLite roundtrip (`save_*` → `load_*`) and that
  `collect` records failure symptoms instead of crashing.
- Run `python3 -m compileall src`.
- Keep docs aligned when adding a new source.
- If source access fails, report status code/body symptom rather than silently falling back.
