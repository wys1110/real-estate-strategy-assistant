# API Setup

기준: 공공데이터포털(data.go.kr) 국토교통부 실거래가 API

## 인증키

스크린샷에서 `일반 인증키`가 발급된 것을 확인했습니다.

보안 원칙:

- 인증키는 git에 커밋하지 않습니다.
- 문서에는 인증키 원문을 쓰지 않습니다.
- 로컬 실행 시 `.env` 또는 shell 환경변수로만 사용합니다.

로컬 설정:

```bash
cp .env.example .env
# .env 파일에 아래 형식으로 입력
MOLIT_API_KEY=발급받은_일반_인증키
```

현재 코드는 `.env`를 자동 로드하지 않습니다. 실행 검증 시에는 우선 shell 환경변수로 넘깁니다.

```bash
export MOLIT_API_KEY=발급받은_일반_인증키
```

## 연립다세대 매매 실거래가

스크린샷의 API입니다.

| 항목 | 값 |
|---|---|
| 서비스 | 국토교통부_연립다세대 매매 실거래가 자료 |
| 데이터 포맷 | XML |
| Base URL | `https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade` |
| Operation | `getRTMSDataSvcRHTrade` |
| Endpoint | `https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade` |
| 인증키 환경변수 | `MOLIT_API_KEY` |
| 활용기간 | `2026-06-14 ~ 2028-06-14` |

필수 파라미터:

| 파라미터 | 설명 | 예시 |
|---|---|---|
| `serviceKey` | 공공데이터포털 일반 인증키 | `MOLIT_API_KEY` |
| `LAWD_CD` | 법정동코드 앞 5자리 | `11215` = 서울 광진구 |
| `DEAL_YMD` | 계약년월 6자리 | `202605` |

선택 파라미터:

| 파라미터 | 설명 | 기본 |
|---|---|---|
| `numOfRows` | 한 페이지 결과 수 | `100` |
| `pageNo` | 페이지 번호 | `1` |

CLI 실행:

```bash
MOLIT_API_KEY=... PYTHONPATH=src python3 -m real_estate_strategy.cli transactions --deal-ymd 202605 --type villa
```

검증 결과:

- `2026-06-14`에 스크린샷의 일반 인증키로 호출 성공
- 테스트 파라미터: `LAWD_CD=11215`, `DEAL_YMD=202501`
- 응답: `HTTP 200`, `resultMsg=OK`, 거래 3건 이상 파싱 확인

## 아파트 매매 실거래가

현재 코드에 같이 구현되어 있습니다.

| 항목 | 값 |
|---|---|
| 서비스 | 국토교통부_아파트 매매 실거래가 자료 |
| 데이터 포맷 | XML |
| Base URL | `https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade` |
| Operation | `getRTMSDataSvcAptTrade` |
| Endpoint | `https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade` |

CLI 실행:

```bash
MOLIT_API_KEY=... PYTHONPATH=src python3 -m real_estate_strategy.cli transactions --deal-ymd 202605 --type apt
```

검증 결과:

- `2026-06-14`에 같은 키로 호출 성공
- 테스트 파라미터: `LAWD_CD=11215`, `DEAL_YMD=202501`
- 응답: `HTTP 200`, `resultMsg=OK`, 거래 파싱 확인
- 단, 같은 키/파라미터에서도 간헐적으로 `HTTP 403 Forbidden`이 발생해 retry가 필요합니다.

## 호출 안정성

공공데이터포털 API는 같은 인증키와 같은 파라미터에서도 간헐적으로 `HTTP 403 Forbidden`을 반환할 수 있습니다. 실제 검증 중 아파트 매매 API에서 2회 실패 후 3회차에 정상 응답이 확인되었습니다.

현재 구현은 다음 HTTP 상태에 대해 재시도합니다.

- `403`
- `429`
- `500`
- `502`
- `503`
- `504`

재시도 정책:

- 최대 5회
- 0.5초부터 exponential backoff
- 최종 실패 로그에는 endpoint, `LAWD_CD`, `DEAL_YMD`만 포함
- 인증키 원문은 예외 메시지나 문서에 남기지 않음

## 코드 매핑

현재 구현 파일:

- `src/real_estate_strategy/molit.py`
- `src/real_estate_strategy/cli.py`

지원 타입:

| CLI type | API |
|---|---|
| `villa` | 연립다세대 매매 실거래가 |
| `apt` | 아파트 매매 실거래가 |

현재 미구현:

- 단독/다가구 매매 실거래가
- 오피스텔 매매 실거래가
- 전월세 실거래가
- `.env` 자동 로드

## Claude 구현 요청 후보

Claude Code에 맡길 다음 작업:

1. `.env` 자동 로더 추가
2. `single_house` 타입 추가: 단독/다가구 매매 실거래가
3. `officetel` 타입 추가
4. `rent` 계열 전월세 API 추가
5. API 응답 원문 저장 옵션 추가
