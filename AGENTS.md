# AGENTS.md

## 행동 지침

- 요청된 범위만 구현합니다.
- 매물 호가와 실거래가는 명확히 구분합니다.
- 현재 매물 HTML 파싱 결과는 불안정한 데이터로 취급하고, 소스 URL과 조회 시각을 유지합니다.
- 크롤링 강도를 높이지 않습니다. 테스트는 소량 요청으로 제한합니다.
- Claude Code와 협업할 수 있도록 `CLAUDE.md`와 README를 함께 갱신합니다.
- 이 머신의 기본 Python은 3.7 계열입니다. Python 3.9+ 전용 타입 문법을 쓰지 않습니다.

## 실행

```bash
PYTHONPATH=src python3 -m real_estate_strategy.cli fetch --limit 12
PYTHONPATH=src python3 -m real_estate_strategy.cli fetch --format json --limit 5
MOLIT_API_KEY=... PYTHONPATH=src python3 -m real_estate_strategy.cli transactions --deal-ymd 202605 --type villa
```

## 현재 소스

- 부동산뱅크 자양동 매물 HTML: 현재 호가
- 국토교통부 공공데이터포털: 실거래가
- 한국부동산원: 통계/지수 연동 예정
