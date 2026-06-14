import unittest

from real_estate_strategy.redevelopment import (
    RedevelopmentZone,
    normalize_stage,
    score_zone,
)


class RedevelopmentStageTest(unittest.TestCase):
    def test_normalizes_cleanup_stage_aliases(self):
        self.assertEqual(normalize_stage("추진위원회승인"), "추진위원회 승인")
        self.assertEqual(normalize_stage("정비구역지정"), "정비구역 지정")

    def test_zone_uses_normalized_stage_for_progress_and_score(self):
        zone = RedevelopmentZone(
            district="광진구",
            biz_type="재개발(주택정비형)",
            name="테스트 구역",
            address="화양동 32-12",
            stage="추진위원회승인",
        )

        self.assertEqual(zone.stage, "추진위원회 승인")
        self.assertEqual(zone.progress, 20)
        self.assertEqual(score_zone(zone), 65)


if __name__ == "__main__":
    unittest.main()
