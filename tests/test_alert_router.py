import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from app.routers import alert_router


class FakeCursor:
    def __init__(self):
        self.executed_sql = []
        self._result = None

    async def execute(self, sql, params=None):
        self.executed_sql.append((sql, params))
        if "COUNT(*)" in sql:
            self._result = {"count": 2}
        else:
            self._result = [{
                "id": "ALT-2026-0001",
                "node_id": "NODE-1",
                "object_category": "Hazard",
                "title": "Hazard Detected",
                "source": "AI Camera",
                "severity": "critical",
                "status": "active",
                "confidence": 90,
                "risk_score": 80,
                "train_number": None,
                "distance_km": 1.2,
                "eta_sec": None,
                "image_url": "https://example.com/image.jpg",
                "detected_at": datetime(2026, 6, 29, 10, 0, 0),
                "line_name": "Line A",
                "zone_name": "Zone 1",
            }]

    async def fetchone(self):
        return self._result

    async def fetchall(self):
        return self._result if isinstance(self._result, list) else []


class FakeCursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    async def __aenter__(self):
        return self.cursor

    async def __aexit__(self, exc_type, exc, tb):
        return False


class AlertRouterOrderingTest(unittest.IsolatedAsyncioTestCase):
    async def test_list_alerts_orders_newest_first(self):
        cursor = FakeCursor()

        def fake_get_cursor():
            return FakeCursorContext(cursor)

        with patch.object(alert_router, "get_cursor", side_effect=fake_get_cursor):
            await alert_router.list_alerts(page=1, pageSize=10)

        self.assertTrue(any("ORDER BY alerts.detected_at DESC" in sql for sql, _ in cursor.executed_sql))
        self.assertTrue(any("alerts.id DESC" in sql for sql, _ in cursor.executed_sql))

    async def test_list_alerts_supports_escalated_to_filter(self):
        cursor = FakeCursor()

        def fake_get_cursor():
            return FakeCursorContext(cursor)

        with patch.object(alert_router, "get_cursor", side_effect=fake_get_cursor):
            await alert_router.list_alerts(page=1, pageSize=10, escalated_to="rpf")

        self.assertTrue(any("alerts.escalated_to = %s" in sql for sql, _ in cursor.executed_sql))

    async def test_escalate_alert_accepts_team_target_without_breaking_old_payloads(self):
        cursor = FakeCursor()
        cursor._result = {"id": "ALT-2026-0001", "node_id": "NODE-1"}

        def fake_get_cursor():
            return FakeCursorContext(cursor)

        with patch.object(alert_router, "get_cursor", side_effect=fake_get_cursor), \
            patch.object(alert_router.ws_manager, "broadcast", new=AsyncMock()):
            response = await alert_router.escalate_alert(
                "ALT-2026-0001",
                {"note": "Forward to maintenance", "team": "maintenance"},
            )

        self.assertEqual(response["escalated_to"], "maintenance")
        self.assertTrue(any("escalated_to" in sql for sql, _ in cursor.executed_sql))


if __name__ == "__main__":
    unittest.main()
