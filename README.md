# 부동산 전략 어시스턴트

한국 주택 매물 가격과 실거래가를 함께 보는 개인 전략 어시스턴트입니다.

현재 범위는 작게 유지합니다.

- 자양동 빌라/연립/다세대 현재 매물 호가 수집
- 국토교통부 실거래가 API 조회
- Claude Code와 Codex가 같은 기준으로 협업할 수 있는 문서화

## 현재 결론

2026-06-14 15:06 KST 테스트 기준:

- 국토교통부 공공데이터포털 API는 실거래가 조회에 적합합니다.
- 네이버부동산 내부 JSON 호출은 현재 실행환경에서 `429 TOO_MANY_REQUESTS`가 발생했습니다.
- 부동산뱅크 자양동 매물 HTML은 접근 가능했고, 첫 페이지 30건 중 빌라/연립/다세대 계열 16건을 파싱했습니다.
- 최신 매물 스냅샷은 `snapshots/latest-jayang-villas.json`에 저장했습니다.
- GitHub의 Claude 작업 브랜치에 있던 국토부 실거래가 모듈을 main에 통합했습니다.

## 빠른 실행

```bash
cd /Users/yongseokwon/dev/real-estate-strategy-assistant
PYTHONPATH=src python3 -m real_estate_strategy.cli fetch --limit 12
```

JSON으로 받기:

```bash
PYTHONPATH=src python3 -m real_estate_strategy.cli fetch --format json --limit 5
```

국토교통부 실거래가 조회:

```bash
export MOLIT_API_KEY=공공데이터포털_일반_인증키
PYTHONPATH=src python3 -m real_estate_strategy.cli transactions --deal-ymd 202605 --type villa
PYTHONPATH=src python3 -m real_estate_strategy.cli transactions --deal-ymd 202605 --type apt
```

CSV로 받기:

```bash
PYTHONPATH=src python3 -m real_estate_strategy.cli fetch --format csv > listings.csv
```

## 기본 조회 대상

- 지역: 서울특별시 광진구 자양동
- 법정동 코드: `1121510500`
- 거래: 매매
- 필터: 빌라/연립/다세대
- 소스: 부동산뱅크 매물 HTML

## 구조

```text
src/real_estate_strategy/
  budongsanbank.py  # 부동산뱅크 HTML fetch/parse
  molit.py          # 국토교통부 실거래가 API fetch/parse
  cli.py            # CLI 진입점
docs/
  data-sources.md   # 데이터 소스별 가능/불가능 범위
  current-snapshot.md
snapshots/
  latest-jayang-villas.json
CLAUDE.md           # Claude Code 협업 지침
AGENTS.md           # Codex 협업 지침
```

## 주의

현재 매물 호가는 공식 공공 API가 아닙니다. HTML 구조 변경, 접근 제한, 약관 이슈가 생길 수 있으므로 수집 결과는 의사결정 보조로만 사용하고, 실제 매수 판단 전 원문 링크와 중개사 확인이 필요합니다.
