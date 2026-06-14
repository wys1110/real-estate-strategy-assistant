"""서울시 정비사업(재개발/재건축) 구역 정보 수집 및 추천.

데이터 소스: 서울시 정비사업 정보몽땅 (cleanup.seoul.go.kr)
"""
from __future__ import annotations

import html as html_mod
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

DISTRICT_CODES: Dict[str, str] = {
    "종로구": "11110", "중구": "11140", "용산구": "11170",
    "성동구": "11200", "광진구": "11215", "동대문구": "11230",
    "중랑구": "11260", "성북구": "11290", "강북구": "11305",
    "도봉구": "11320", "노원구": "11350", "은평구": "11380",
    "서대문구": "11410", "마포구": "11440", "양천구": "11470",
    "강서구": "11500", "구로구": "11530", "금천구": "11545",
    "영등포구": "11560", "동작구": "11590", "관악구": "11620",
    "서초구": "11650", "강남구": "11680", "송파구": "11710",
    "강동구": "11740",
}

STAGES: List[str] = [
    "안전진단",
    "정비계획 수립",
    "정비구역 지정",
    "추진위원회 승인",
    "조합설립인가",
    "사업시행인가",
    "관리처분인가",
    "분양",
    "착공",
    "준공인가",
    "이전고시",
    "조합해산",
    "조합청산",
    "조합원 모집신고",
]

STAGE_PROGRESS: Dict[str, int] = {
    "안전진단": 5,
    "정비계획 수립": 10,
    "정비구역 지정": 15,
    "추진위원회 승인": 20,
    "조합설립인가": 35,
    "사업시행인가": 50,
    "관리처분인가": 65,
    "분양": 75,
    "착공": 80,
    "준공인가": 90,
    "이전고시": 95,
    "조합해산": 98,
    "조합청산": 100,
    "조합원 모집신고": 15,
}

INVESTMENT_STAGES = [
    "안전진단",
    "정비계획 수립",
    "정비구역 지정",
    "추진위원회 승인",
    "조합설립인가",
    "사업시행인가",
    "관리처분인가",
    "착공",
]

BIZ_TYPES = [
    "재건축",
    "재개발(주택정비형)",
    "재개발(도시정비형)",
    "가로주택정비",
    "소규모재건축",
    "소규모재개발",
]

CLEANUP_BASE = "https://cleanup.seoul.go.kr/cleanup/bsnssttus/lscrMainIndx.do"
_USER_AGENT = "RealEstateStrategyApp/1.0"

_STAGE_ALIASES = {
    "추진위원회승인": "추진위원회 승인",
    "정비구역지정": "정비구역 지정",
}


def normalize_stage(stage: str) -> str:
    """정보몽땅의 표기 차이를 앱의 표준 진행단계명으로 맞춥니다."""
    cleaned = re.sub(r"\s+", " ", stage).strip()
    return _STAGE_ALIASES.get(cleaned, cleaned)


@dataclass
class RedevelopmentZone:
    district: str
    biz_type: str
    name: str
    address: str
    stage: str
    progress: int = 0
    score: float = 0.0
    lat: Optional[float] = None
    lon: Optional[float] = None

    def __post_init__(self):
        self.stage = normalize_stage(self.stage)
        if not self.progress:
            self.progress = STAGE_PROGRESS.get(self.stage, 0)


def _parse_cleanup_html(html: str) -> List[RedevelopmentZone]:
    """cleanup.seoul.go.kr 검색결과 HTML에서 사업장 목록 파싱."""
    zones = []
    tbody = re.search(r'<tbody>(.*?)</tbody>', html, re.DOTALL)
    if not tbody:
        return zones
    row_pattern = re.compile(
        r'<tr>\s*'
        r'<td>\d+</td>\s*'                          # 번호
        r'<td>([^<]+)</td>\s*'                       # 자치구
        r'<td>([^<]+)</td>\s*'                       # 사업구분
        r'<td[^>]*>([^<]+)</td>\s*'                  # 사업장명
        r'<td>([^<]*)</td>\s*'                       # 대표지번
        r'<td>([^<]+)</td>',                         # 진행단계
        re.DOTALL,
    )
    for m in row_pattern.finditer(tbody.group(1)):
        district = html_mod.unescape(m.group(1).strip())
        biz_type = html_mod.unescape(m.group(2).strip())
        name = html_mod.unescape(m.group(3).strip())
        address = html_mod.unescape(m.group(4).strip())
        stage = html_mod.unescape(m.group(5).strip())
        if district and name:
            zones.append(RedevelopmentZone(
                district=district,
                biz_type=biz_type,
                name=name,
                address=address,
                stage=stage,
            ))
    return zones


def _total_pages(html: str) -> int:
    """페이지네이션에서 마지막 페이지 번호 추출."""
    m = re.search(r'cpage=(\d+)[^"]*"[^>]*>\s*(?:마지막|끝)', html)
    if m:
        return int(m.group(1))
    pages = re.findall(r'cpage=(\d+)', html)
    return max((int(p) for p in pages), default=1)


def fetch_zones(
    district_code: str,
    page: int = 1,
    page_size: int = 100,
) -> Tuple[List[RedevelopmentZone], int]:
    """cleanup.seoul.go.kr에서 특정 구의 정비사업 목록 조회.

    Returns (zones, total_pages).
    """
    params = urllib.parse.urlencode({
        "scupBsnsSttus.signguCode": district_code,
        "cpage": page,
        "pageSize": page_size,
    })
    url = f"{CLEANUP_BASE}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    zones = _parse_cleanup_html(html)
    total = _total_pages(html)
    return zones, total


def fetch_all_zones(district_codes: List[str]) -> List[RedevelopmentZone]:
    """여러 구의 정비사업 목록을 한번에 조회."""
    all_zones = []
    for code in district_codes:
        try:
            zones, _ = fetch_zones(code, page_size=200)
            all_zones.extend(zones)
        except Exception:
            continue
    return all_zones


def score_zone(zone: RedevelopmentZone) -> float:
    """투자 관점 추천 점수 (0~100).

    초기~중기 단계(조합설립~관리처분)에 높은 점수,
    완료 단계(준공 이후)에 낮은 점수.
    """
    stage_scores = {
        "안전진단": 25,
        "정비계획 수립": 40,
        "정비구역 지정": 45,
        "추진위원회 승인": 55,
        "조합설립인가": 75,
        "사업시행인가": 85,
        "관리처분인가": 80,
        "분양": 70,
        "착공": 65,
        "준공인가": 30,
        "이전고시": 15,
        "조합해산": 5,
        "조합청산": 5,
        "조합원 모집신고": 35,
    }
    base = stage_scores.get(zone.stage, 30)

    type_bonus = 0
    if "재개발" in zone.biz_type:
        type_bonus = 10
    elif "재건축" in zone.biz_type:
        type_bonus = 5

    return min(100.0, base + type_bonus)


def enrich_scores(zones: List[RedevelopmentZone]) -> List[RedevelopmentZone]:
    """각 구역에 추천 점수 부여."""
    for z in zones:
        z.score = score_zone(z)
    return zones


def zones_to_dicts(zones: List[RedevelopmentZone]) -> List[dict]:
    return [asdict(z) for z in zones]
