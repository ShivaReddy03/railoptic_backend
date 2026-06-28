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


if __name__ == "__main__":
    unittest.main()
