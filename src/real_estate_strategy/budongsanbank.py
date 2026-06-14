from __future__ import annotations

import datetime as dt
import html
import re
from dataclasses import asdict, dataclass
from typing import Iterable, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://www.neonet.co.kr/novo-rebank/view/offerings/inc_OfferingsList.neo"
DETAIL_URL = "https://www.neonet.co.kr/novo-rebank/view/offerings/OfferingsDetail.neo"
DEFAULT_REGION_CODE = "1121510500"  # Seoul, Gwangjin-gu, Jayang-dong


@dataclass
class Listing:
    listing_id: str
    trade_type: str
    listing_type: str
    name: str
    area_sqm: str
    floor: str
    price_manwon: str
    price_krw: Optional[int]
    agency: str
    note: str
    source: str
    detail_url: str
    fetched_at: str

    def to_dict(self) -> dict:
        return asdict(self)


def build_list_url(region_code: str = DEFAULT_REGION_CODE) -> str:
    params = {
        "offerings_gbn": "SH",
        "sub_offerings_gbn": "",
        "complex_cd": "",
        "offer_gbn": "P",
        "region_cd": region_code,
        "list_gbn": "",
        "agency_cd": "",
        "area": "",
        "price": "",
        "area_min": "",
        "area_max": "",
        "price_min": "",
        "price_max": "",
        "price_month": "",
        "price_month_min": "",
        "price_month_max": "",
        "building_no": "",
        "pyung_cd": "",
        "sort_list": "",
        "prc_sort": "",
    }
    return BASE_URL + "?" + urlencode(params)


def fetch_html(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=20) as response:
        raw = response.read()
    return raw.decode("euc-kr", errors="replace")


def parse_listings(source_html: str, source_url: str, fetched_at: Optional[str] = None) -> List[Listing]:
    fetched_at = fetched_at or dt.datetime.now(dt.timezone.utc).isoformat()
    row_pairs = re.findall(
        r"(<tr class=\"bg_(?:white|gray)\">.*?onClickDetail\('([^']+)', '([^']+)'\).*?</tr>)"
        r"\s*(<tr class=\"bg_(?:white|gray)\">.*?</tr>)",
        source_html,
        re.S,
    )

    listings: List[Listing] = []
    for main_row, source_prefix, source_id, note_row in row_pairs:
        cells = [_clean(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", main_row, re.S)]
        if len(cells) < 7:
            continue

        name_match = re.search(r"class=\"link_blue\"[^>]*>(.*?)</a>", main_row, re.S)
        name = _clean(name_match.group(1)) if name_match else ""
        listing_id = f"{source_prefix}_{source_id}"
        listing_type = cells[1]
        price_manwon = cells[6]

        listings.append(
            Listing(
                listing_id=listing_id,
                trade_type=cells[0],
                listing_type=listing_type,
                name=name,
                area_sqm=cells[4],
                floor=cells[5],
                price_manwon=price_manwon,
                price_krw=_price_manwon_to_krw(price_manwon),
                agency=cells[7] if len(cells) > 7 else "",
                note=_clean(note_row),
                source=source_url,
                detail_url=build_detail_url(source_prefix, source_id),
                fetched_at=fetched_at,
            )
        )
    return listings


def filter_villas(listings: Iterable[Listing]) -> List[Listing]:
    keywords = ("빌라", "연립", "다세대")
    return [listing for listing in listings if any(keyword in listing.listing_type for keyword in keywords)]


def build_detail_url(source_prefix: str, source_id: str, region_code: str = DEFAULT_REGION_CODE) -> str:
    params = {
        "offerings_cd": f"{source_prefix}_{source_id}",
        "offerings_gbn": "VG" if source_prefix == "VG" else "SH",
        "offer_gbn": "P",
        "region_cd": region_code,
    }
    return DETAIL_URL + "?" + urlencode(params)


def _clean(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _price_manwon_to_krw(value: str) -> Optional[int]:
    digits = re.sub(r"[^0-9]", "", value)
    if not digits:
        return None
    return int(digits) * 10000
