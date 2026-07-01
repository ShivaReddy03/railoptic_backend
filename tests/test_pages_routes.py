import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.routers import dashboard_router, trains_router, reports_router


class FakeCursor:
    def __init__(self):
        self.executed_sql = []
        self._result = None

    async def execute(self, sql, params=None):
        self.executed_sql.append((sql, params))
        if "COUNT(*)" in sql and "trains" in sql:
            self._result = [{"count": 3}]
        elif "FROM trains" in sql:
            self._result = [{
                "id": 1,
                "number": "12010",
                "line_id": 10,
                "status": "on_time",
                "updated_at": datetime(2026, 6, 29, 8, 0, tzinfo=timezone.utc),
                "line_name": "North Line",
                "zone_name": "Northern Railway",
            }]
        elif "FROM alerts" in sql and "COUNT(*)" in sql:
            self._result = [{"count": 2}]
        else:
            self._result = [{
                "id": "ALT-2026-0001",
                "object_category": "Rock Detected",
                "detected_at": datetime(2026, 6, 29, 8, 0, tzinfo=timezone.utc),
            }]

    async def fetchone(self):
        return self._result[0] if isinstance(self._result, list) and self._result else None

    async def fetchall(self):
        return self._result if isinstance(self._result, list) else []


class FakeCursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    async def __aenter__(self):
        return self.cursor

    async def __aexit__(self, exc_type, exc, tb):
        return False


class PagesRouterTest(unittest.IsolatedAsyncioTestCase):
    async def test_trains_list_returns_expected_shape(self):
        cursor = FakeCursor()

        def fake_get_cursor():
            return FakeCursorContext(cursor)

        with patch.object(trains_router, "get_cursor", side_effect=fake_get_cursor):
            response = await trains_router.list_trains(page=1, pageSize=10)

        self.assertIn("data", response)
        self.assertEqual(response["page"], 1)
        self.assertEqual(response["pageSize"], 10)
        self.assertTrue(response["data"])
        self.assertEqual(response["data"][0]["number"], "12010")

    async def test_reports_summary_returns_expected_fields(self):
        cursor = FakeCursor()

        def fake_get_cursor():
            return FakeCursorContext(cursor)

        with patch.object(reports_router, "get_cursor", side_effect=fake_get_cursor):
            response = await reports_router.reports_summary()

        self.assertIn("total", response)
        self.assertIn("scheduled", response)
        self.assertIn("manual", response)
        self.assertIn("exportedGb", response)

    async def test_analytics_summary_returns_expected_fields(self):
        cursor = FakeCursor()

        def fake_get_cursor():
            return FakeCursorContext(cursor)

        with patch.object(dashboard_router, "get_cursor", side_effect=fake_get_cursor):
            response = await dashboard_router.analytics_summary()

        self.assertIn("totalDetections", response)
        self.assertIn("criticalIncidents", response)
        self.assertIn("detectionsByType", response)
        self.assertIn("incidentsBySeverity", response)
        self.assertIn("byZone", response)

    async def test_nodes_summary_returns_expected_fields(self):
        cursor = FakeCursor()

        def fake_get_cursor():
            return FakeCursorContext(cursor)

        with patch.object(dashboard_router, "get_cursor", side_effect=fake_get_cursor):
            response = await dashboard_router.nodes_summary()

        self.assertIn("total", response)
        self.assertIn("online", response)
        self.assertIn("healthy", response)
        self.assertIn("warning", response)
        self.assertIn("critical", response)
        self.assertIn("offline", response)

    async def test_devices_list_returns_paginated_shape(self):
        cursor = FakeCursor()

        def fake_get_cursor():
            return FakeCursorContext(cursor)

        with patch.object(dashboard_router, "get_cursor", side_effect=fake_get_cursor):
            response = await dashboard_router.list_devices(page=1, pageSize=2)

        self.assertIn("data", response)
        self.assertIn("total", response)
        self.assertIn("page", response)
        self.assertIn("pageSize", response)
        self.assertTrue(isinstance(response["data"], list))

    def test_classify_node_health_uses_numeric_health(self):
        self.assertEqual(dashboard_router._classify_node_health("normal", 85), "normal")
        self.assertEqual(dashboard_router._classify_node_health("normal", 25), "critical")
        self.assertEqual(dashboard_router._classify_node_health("normal", 60), "warning")
        self.assertEqual(dashboard_router._classify_node_health("offline", 0), "offline")


if __name__ == "__main__":
    unittest.main()
