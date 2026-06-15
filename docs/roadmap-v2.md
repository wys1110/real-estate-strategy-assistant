# 부동산 전략 어시스턴트 — Roadmap v2

## 목표

Streamlit Cloud에서 실데이터 기반 투자 전략 분석 제공:
- 매일 자동 수집 → DB → 앱 즉시 응답
- 실 좌표 지도, 호가↔실거래 갭, 월별 추세, 재개발 점수 상세화

---

## Phase 1 — 데이터 인프라

### 1-1. GitHub Actions 자동 수집

파일: `.github/workflows/collect.yml`

- **트리거**: 매일 02:00 KST (17:00 UTC) + 수동 `workflow_dispatch`
- **동작**:
  1. `python3 -m real_estate_strategy.cli collect --all --deal-ymd <YYYYMM>` (당월 + 전월)
  2. `snapshots/realestate.db`를 `git add --force` → `git commit` → `git push`
- **시크릿**: `MOLIT_API_KEY` → GitHub repo secret
- **효과**: Streamlit Cloud가 repo clone 시 최신 DB 포함 → 네트워크 0으로 즉시 응답

```yaml
# .github/workflows/collect.yml 스켈레톤
on:
  schedule:
    - cron: '0 17 * * *'
  workflow_dispatch:

jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt
      - run: |
          MOLIT_API_KEY=${{ secrets.MOLIT_API_KEY }} \
          PYTHONPATH=src python3 -m real_estate_strategy.cli collect --all --deal-ymd $(date -d '1 month ago' +%Y%m)
          MOLIT_API_KEY=${{ secrets.MOLIT_API_KEY }} \
          PYTHONPATH=src python3 -m real_estate_strategy.cli collect --all --deal-ymd $(date +%Y%m)
      - run: |
          git config user.email "actions@github.com"
          git config user.name "GitHub Actions"
          git add --force snapshots/realestate.db
          git diff --cached --quiet || git commit -m "chore: daily DB snapshot $(date +%Y-%m-%d)"
          git push
```

### 1-2. 실제 지오코딩 (Nominatim/OSM)

파일: `src/real_estate_strategy/geocode.py` (신규)

- **API**: `https://nominatim.openstreetmap.org/search` — 무료, API 키 불필요
- **Rate limit**: 1 req/s (sleep 준수)
- **캐시**: `store.py`의 `geocode_cache` 테이블 (주소 → lat/lon)
- **호출 시점**: `collect` 배치에서만. 앱은 DB `lat`/`lon` 컬럼만 읽음
- **스키마 변경**:
  - `listings`: `lat REAL`, `lon REAL` 컬럼 추가
  - `transactions`: `lat REAL`, `lon REAL` 컬럼 추가
  - `zones`: `lat REAL`, `lon REAL` (이미 구현 여부 확인 필요)
  - `geocode_cache(address TEXT PRIMARY KEY, lat REAL, lon REAL, fetched_at TEXT)`

```python
# geocode.py 핵심 로직
import urllib.request, urllib.parse, json, time

_CACHE: dict[str, tuple[float, float]] = {}

def geocode(address: str) -> tuple[float, float] | None:
    if address in _CACHE:
        return _CACHE[address]
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": address, "format": "json", "limit": 1,
        "accept-language": "ko",
    })
    req = urllib.request.Request(url, headers={"User-Agent": "real-estate-strategy/1.0"})
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.loads(r.read())
    time.sleep(1.0)
    if data:
        result = float(data[0]["lat"]), float(data[0]["lon"])
        _CACHE[address] = result
        return result
    return None
```

### 1-3. 멀티월 누적 수집

- `collect.py`: Actions에서 당월·전월 호출 → 6개월 누적 시 추세 차트 가능
- `store.save_transactions`: `(district, deal_ymd, property_type)` 기준 INSERT OR REPLACE → 월별 누적 자동 보장
- CLI: `--deal-ymd-list 202501,202502,...` 옵션 추가 (선택)

---

## Phase 2 — 분석 UI

### 2-1. 호가 vs 실거래 갭 분석

파일: `src/real_estate_strategy/analysis.py` (신규)  
앱 위치: `app.py` — "갭 분석" 탭

**분석 방법**:
```
매물(listings) → 구별 ㎡당 평균 호가
실거래(transactions) → 구별 ㎡당 평균 실거래가 (최근 3개월)
갭 = (호가 - 실거래) / 실거래 × 100 (%)
```

**UI 컴포넌트**:
- `st.metric`: 평균 호가, 평균 실거래가, 갭(%)
- `st.dataframe`: 구별 랭킹 테이블 (갭 큰 순 정렬)
- `st.bar_chart`: 구별 갭 시각화

**매칭 기준**: `area_sqm` ±10% 범위 내 매물↔실거래 페어링 (면적 기반)

### 2-2. 월별 가격 추세 차트

파일: `app.py` — "추세" 탭

**데이터**: `transactions` 테이블 `deal_ymd` 컬럼으로 월별 그룹
```sql
SELECT deal_ymd, AVG(price_manwon / area_sqm) as price_per_sqm
FROM transactions
WHERE district = ?
GROUP BY deal_ymd
ORDER BY deal_ymd
```

**UI**:
- `st.line_chart(df.set_index("deal_ymd"))` — ㎡당 실거래가 추세
- 구·면적대(소/중/대) 필터

### 2-3. 재개발 투자 점수 상세화

현재: 단계·사업유형 2개 인자  
개선: 5개 인자 복합 점수 (0–100)

| 인자 | 가중치 | 설명 |
|---|---|---|
| 사업 단계 | 40 | 관리처분인가 이후 > 사업시행인가 > 조합설립 > 정비구역지정 |
| 사업 유형 | 20 | 재건축 > 재개발 > 주거환경개선 |
| 경과 기간 | 20 | 최근 단계 진입 후 경과 연수 (2년 이내 = 고점, 5년 초과 = 감점) |
| 지역 가격 | 10 | 구 평균 실거래가 대비 상대 위치 |
| 지하철 거리 | 10 | `poi.py` 역 데이터 기준 500m 이내 보너스 |

파일: `src/real_estate_strategy/scoring.py` (신규)

```python
def redev_score(zone: dict, district_avg_price: float, stations: list) -> dict:
    """Returns {total: int, breakdown: dict}"""
    ...
```

앱: 점수 breakdown 툴팁 또는 expander로 표시

---

## 파일 변경 요약

```
신규
├── .github/workflows/collect.yml
├── src/real_estate_strategy/geocode.py
├── src/real_estate_strategy/analysis.py
└── src/real_estate_strategy/scoring.py

수정
├── store.py          — lat/lon 컬럼, geocode_cache 테이블
├── collect.py        — geocode 호출 추가
├── app.py            — 갭분석·추세·재개발점수 탭 추가
└── cli.py            — (선택) --deal-ymd-list 옵션
```

---

## 검증 체크리스트

- [ ] `python3 -m compileall src` 통과
- [ ] `geocode.py` — Nominatim 1 req/s 준수, User-Agent 헤더 포함
- [ ] `store.py` — 기존 DB 마이그레이션 (ALTER TABLE ... ADD COLUMN IF NOT EXISTS)
- [ ] `collect.py` — geocode 실패 시 `record_failure` 호출 (조용한 폴백 금지)
- [ ] `analysis.py` — 매물 0건·실거래 0건일 때 graceful 처리
- [ ] Actions — `MOLIT_API_KEY` secret 없으면 실거래 수집 skip (에러 아님)
- [ ] 앱 — 새 탭 추가 후 기존 탭 동작 회귀 확인
