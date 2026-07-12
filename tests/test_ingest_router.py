import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi import UploadFile

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


class IngestAlertResolutionTest(unittest.IsolatedAsyncioTestCase):
    async def test_benign_ingest_resolves_existing_active_alert(self):
        fake_cursor = AsyncMock()
        fake_cursor.fetchone.return_value = {
            "id": "NODE-1",
            "line_id": 7,
            "line_name": "A1",
            "zone_name": "Central",
        }

        @asynccontextmanager
        async def fake_get_cursor():
            yield fake_cursor

        image = UploadFile(filename="safe.jpg", file=__import__("io").BytesIO(b"safe"))

        with patch.object(ingest, "get_cursor", fake_get_cursor), \
            patch.object(ingest, "upload_detection_image", new=AsyncMock(return_value="https://example.com/safe.jpg")), \
            patch.object(ingest, "infer_image", new=AsyncMock(return_value={
                "hazard_count": 0,
                "risk_level": "none",
                "top_prediction": {"class": None, "confidence": 0.0},
                "object_area_px": None,
                "max_area_px": None,
            })), \
            patch.object(ingest, "compute_risk_score", return_value=0), \
            patch.object(ingest, "severity_from_score", return_value="info"), \
            patch.object(ingest.ws_manager, "broadcast", new=AsyncMock()):
            response = await ingest.ingest_detection(
                image=image,
                node_id="NODE-1",
                lidar_dist_m=12.5,
                timestamp="2026-06-29T10:00:00Z",
            )

        self.assertEqual(response["hazard_count"], 0)
        self.assertEqual(response["risk_score"], 0)

        resolved_query = next(
            (query for query, params in fake_cursor.execute.await_args_list if "UPDATE alerts SET status = 'resolved'" in str(query)),
            None,
        )
        self.assertIsNotNone(resolved_query)


if __name__ == "__main__":
    unittest.main()
