# 부동산 전략 어시스턴트

한국 주택 매물 호가와 실거래가를 함께 조회·비교하는 도구입니다.

- **매물 호가**: 부동산뱅크 HTML 파싱 (현재 매물)
- **실거래가**: 국토교통부 공공데이터포털 API (신고 실거래)
- **웹 UI**: 한 페이지에서 모드를 바꾸며 지도와 상세 데이터를 함께 보는 Streamlit 앱

## 주요 기능

| 기능 | 설명 |
|---|---|
| 매물 호가 조회 | 부동산뱅크에서 빌라/연립/다세대 매물 호가 수집 |
| 실거래가 조회 | 국토부 API로 연립다세대·아파트 실거래가 조회 |
| 호가 vs 실거래가 비교 | 한 지도에서 서로 다른 색상 핀으로 비교 |
| 재개발 추천 | 서울시 정비사업 데이터를 점수화해 지도에 표시 |
| CLI | 터미널에서 직접 조회 (table/json/csv 출력) |

## 설치

```bash
git clone https://github.com/wys1110/real-estate-strategy-assistant.git
cd real-estate-strategy-assistant

python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 국토부 실거래가 API 키 발급

실거래가 조회를 사용하려면 [공공데이터포털](https://www.data.go.kr)에서 API 키를 발급받아야 합니다.

```bash
cp .env.example .env
# .env 파일에 MOLIT_API_KEY 값을 입력
```

## 실행

### 웹앱 (Streamlit)

```bash
.venv/bin/streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속. 앱은 단일 페이지이며 `통합`, `매물`, `실거래`, `재개발` 모드만 바꿔서 사용합니다. 지도는 기본적으로 주소의 동/구 중심을 기준으로 빠르게 표시하고, 필요하면 `주소 좌표 조회`를 켤 수 있습니다.

### CLI

```bash
# 매물 호가 조회
PYTHONPATH=src python3 -m real_estate_strategy.cli fetch --limit 12

# JSON 출력
PYTHONPATH=src python3 -m real_estate_strategy.cli fetch --format json --limit 5

# 실거래가 조회 (연립다세대)
MOLIT_API_KEY=발급받은_키 PYTHONPATH=src python3 -m real_estate_strategy.cli transactions --deal-ymd 202605 --type villa

# 실거래가 조회 (아파트)
MOLIT_API_KEY=발급받은_키 PYTHONPATH=src python3 -m real_estate_strategy.cli transactions --deal-ymd 202605 --type apt
```

## Streamlit Cloud 배포

1. [share.streamlit.io](https://share.streamlit.io)에서 GitHub 계정으로 로그인
2. New app → Repository: 이 레포, Branch: `main`, Main file: `app.py`
3. Advanced settings > Secrets에 아래 입력:
   ```toml
   MOLIT_API_KEY = "발급받은_키"
   ```
4. Deploy 클릭

## 프로젝트 구조

```
app.py                          # Streamlit 웹앱
requirements.txt                # Python 의존성
src/real_estate_strategy/
  budongsanbank.py              # 부동산뱅크 HTML 파싱
  molit.py                      # 국토부 실거래가 API
  cli.py                        # CLI 진입점
.streamlit/
  config.toml                   # Streamlit 설정
  secrets.toml.example          # 시크릿 템플릿
docs/
  api-setup.md                  # API 엔드포인트 정리
  data-sources.md               # 데이터 소스 범위
snapshots/
  latest-jayang-villas.json     # 매물 스냅샷 예시
```

## 기본 조회 대상

- 지역: 서울특별시 광진구 자양동 (`1121510500`)
- 거래 유형: 매매
- 매물 필터: 빌라/연립/다세대

## 주의

매물 호가는 공식 API가 아닌 HTML 파싱 기반입니다. 구조 변경이나 접근 제한이 발생할 수 있으며, 수집 결과는 참고용으로만 사용해야 합니다.

## 라이선스

MIT
