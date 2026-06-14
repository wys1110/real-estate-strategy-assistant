from __future__ import annotations

import argparse
import csv
import json
import sys

from .budongsanbank import build_list_url, fetch_html, filter_villas, parse_listings
from .molit import fetch_transactions


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Real estate strategy assistant CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch current listings from BudongsanBank")
    fetch_parser.add_argument("--region-code", default="1121510500", help="Legal dong code")
    fetch_parser.add_argument("--limit", type=int, default=20)
    fetch_parser.add_argument("--include-all-types", action="store_true")
    fetch_parser.add_argument("--format", choices=("table", "json", "csv"), default="table")

    tx_parser = subparsers.add_parser("transactions", help="Fetch actual transaction prices from MOLIT (국토부)")
    tx_parser.add_argument("--lawd-cd", default="11215", help="법정동코드 앞 5자리 (기본: 11215 광진구)")
    tx_parser.add_argument("--deal-ymd", required=True, help="계약년월 6자리 (예: 202605)")
    tx_parser.add_argument("--type", dest="property_type", choices=("villa", "apt"), default="villa",
                           help="villa=연립다세대(기본), apt=아파트")
    tx_parser.add_argument("--limit", type=int, default=50)
    tx_parser.add_argument("--format", choices=("table", "json", "csv"), default="table")

    args = parser.parse_args(argv)
    if args.command == "fetch":
        return _fetch(args)
    if args.command == "transactions":
        return _transactions(args)
    parser.error("unknown command")
    return 2


def _fetch(args) -> int:
    source_url = build_list_url(args.region_code)
    html = fetch_html(source_url)
    listings = parse_listings(html, source_url=source_url)
    if not args.include_all_types:
        listings = filter_villas(listings)
    if args.limit >= 0:
        listings = listings[: args.limit]

    if args.format == "json":
        json.dump([listing.to_dict() for listing in listings], sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    if args.format == "csv":
        writer = csv.DictWriter(
            sys.stdout,
            fieldnames=[
                "listing_id",
                "trade_type",
                "listing_type",
                "name",
                "area_sqm",
                "floor",
                "price_manwon",
                "price_krw",
                "agency",
                "note",
                "detail_url",
                "fetched_at",
            ],
        )
        writer.writeheader()
        for listing in listings:
            row = listing.to_dict()
            row.pop("source", None)
            writer.writerow(row)
        return 0

    _print_table(listings)
    return 0


def _transactions(args) -> int:
    try:
        txs = fetch_transactions(lawd_cd=args.lawd_cd, deal_ymd=args.deal_ymd, property_type=args.property_type)
    except ValueError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"조회 실패: {e}", file=sys.stderr)
        return 1

    if args.limit >= 0:
        txs = txs[: args.limit]

    if args.format == "json":
        import dataclasses
        json.dump([dataclasses.asdict(t) for t in txs], sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.format == "csv":
        import dataclasses
        if not txs:
            return 0
        writer = csv.DictWriter(sys.stdout, fieldnames=[f.name for f in dataclasses.fields(txs[0])])
        writer.writeheader()
        for t in txs:
            writer.writerow(dataclasses.asdict(t))
        return 0

    _print_tx_table(txs)
    return 0


def _print_tx_table(txs) -> None:
    rows = [
        [
            f"{t.deal_year}-{t.deal_month:02d}-{t.deal_day:02d}",
            t.name,
            t.dong,
            f"{t.area_sqm}㎡",
            t.floor if t.floor is not None else "-",
            f"{t.price_manwon:,}만원",
            t.build_year if t.build_year else "-",
        ]
        for t in txs
    ]
    headers = ["거래일", "건물명", "법정동", "면적", "층", "거래가", "건축년도"]
    widths = _column_widths([headers] + rows)
    print(_format_row(headers, widths))
    print(_format_row(["-" * w for w in widths], widths))
    for row in rows:
        print(_format_row(row, widths))
    print(f"\ncount={len(rows)}")


def _print_table(listings) -> None:
    rows = [
        [
            listing.listing_id,
            listing.listing_type,
            listing.name,
            listing.area_sqm,
            listing.floor,
            listing.price_manwon,
            listing.note[:36],
        ]
        for listing in listings
    ]
    headers = ["id", "type", "name", "area", "floor", "price_manwon", "note"]
    widths = _column_widths([headers] + rows)
    print(_format_row(headers, widths))
    print(_format_row(["-" * width for width in widths], widths))
    for row in rows:
        print(_format_row(row, widths))
    print(f"\ncount={len(rows)}")


def _column_widths(rows):
    return [max(len(str(row[index])) for row in rows) for index in range(len(rows[0]))]


def _format_row(row, widths):
    return " | ".join(str(value).ljust(widths[index]) for index, value in enumerate(row))


if __name__ == "__main__":
    raise SystemExit(main())
