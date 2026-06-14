import csv
import io
import unittest
from unittest.mock import patch

from real_estate_strategy.budongsanbank import Listing
from real_estate_strategy.cli import main


class CliFetchCsvTest(unittest.TestCase):
    def test_fetch_csv_preserves_listing_source(self):
        listing = Listing(
            listing_id="SH_123",
            trade_type="매매",
            listing_type="빌라",
            name="테스트빌라",
            area_sqm="39/30㎡",
            floor="중/5",
            price_manwon="100,000",
            price_krw=1000000000,
            agency="테스트공인",
            note="테스트 메모",
            source="https://example.com/source",
            detail_url="https://example.com/detail",
            fetched_at="2026-06-14T00:00:00+00:00",
        )

        with patch("real_estate_strategy.cli.fetch_html", return_value=""), patch(
            "real_estate_strategy.cli.parse_listings",
            return_value=[listing],
        ):
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                exit_code = main(["fetch", "--format", "csv", "--limit", "1"])

        self.assertEqual(exit_code, 0)
        rows = list(csv.DictReader(io.StringIO(stdout.getvalue())))
        self.assertEqual(rows[0]["source"], "https://example.com/source")
        self.assertEqual(rows[0]["fetched_at"], "2026-06-14T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
