# Claude Code Collaboration Guide

이 프로젝트는 부동산 전략 어시스턴트입니다. 현재 목적은 한국 주택 매물 호가와 실거래가를 조합해 투자/매수 후보를 비교하는 것입니다.

## Working Rules

- Keep the assistant narrow: listing collection, source comparison, strategy notes.
- Do not expand into a general CRM, broker system, or large web app unless explicitly requested.
- Prefer standard-library Python. Current code has no third-party runtime dependency.
- Treat scraped or HTML-parsed listing data as unstable. Always preserve source URL and fetch timestamp.
- Do not hide uncertainty. Mark data as `current_listing`, `actual_transaction`, `index/statistic`, or `manual_note`.
- Avoid aggressive crawling. Fetch only the requested page or small page ranges.

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

# Streamlit 웹앱 (Python 3.12 venv)
.venv/bin/streamlit run app.py
```

## Source Boundaries

- `budongsanbank.py`: current listing asking prices from HTML.
- `molit.py`: official actual transaction prices from MOLIT public data APIs.
- `docs/api-setup.md`: API endpoints, required parameters, and credential handling rules.
- Future REB module: market index/statistics, not individual listings.

## Verification Checklist

- Run the CLI after parser changes.
- Confirm at least one listing has `listing_id`, `listing_type`, `name`, `area_sqm`, `floor`, and `price_manwon`.
- Run `python3 -m compileall src`.
- Keep docs aligned when adding a new source.
- If source access fails, report status code/body symptom rather than silently falling back.
