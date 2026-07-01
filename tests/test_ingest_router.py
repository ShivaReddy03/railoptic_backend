import unittest
from datetime import datetime, timezone

from app.routers import ingest


class IngestTimestampTest(unittest.TestCase):
    def test_parse_timestamp_returns_now_when_missing(self):
        detected_at = ingest._coerce_detected_at(None)
        self.assertIsNotNone(detected_at)
        self.assertIsInstance(detected_at, datetime)
        self.assertIsNotNone(detected_at.tzinfo)

    def test_parse_timestamp_parses_iso_string(self):
        detected_at = ingest._coerce_detected_at("2026-06-29T10:00:00Z")
        self.assertEqual(detected_at, datetime(2026, 6, 29, 10, 0, tzinfo=timezone.utc))

    def test_select_train_candidates_prefers_same_line_and_at_risk(self):
        rows = [
            {"id": 1, "line_id": 2, "status": "on_time", "updated_at": datetime(2026, 6, 29, 10, 0, tzinfo=timezone.utc)},
            {"id": 2, "line_id": 3, "status": "at_risk", "updated_at": datetime(2026, 6, 29, 10, 1, tzinfo=timezone.utc)},
            {"id": 3, "line_id": 2, "status": "delayed", "updated_at": datetime(2026, 6, 29, 10, 2, tzinfo=timezone.utc)},
        ]

        candidates = ingest._select_train_candidates(rows, 2)

        self.assertEqual([row["id"] for row in candidates[:2]], [3, 1])


if __name__ == "__main__":
    unittest.main()
