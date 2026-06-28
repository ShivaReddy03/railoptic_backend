from fastapi import APIRouter
from app.configuration.database import get_cursor
from app.schemas.dashboard import DashboardOverviewResponse

router = APIRouter()


def serialize_alert(alert, critical=False):
    if not alert:
        return None

    return {
        "id": alert["id"],
        "objectCategory": alert["object_category"],
        "line": alert["line_name"],
        "node": alert["node_id"],
        "date": alert["detected_at"].date().isoformat(),
        "time": alert["detected_at"].time().isoformat(timespec="seconds"),
        "severity": alert["severity"],
        "status": alert["status"],
        "confidence": alert["confidence"],
        "riskScore": alert["risk_score"],
        "nearestTrain": alert["train_number"],
        "distanceKm": float(alert["distance_km"]) if alert["distance_km"] is not None else None,
        "etaSec": alert["eta_sec"],
        "imageUrl": alert["image_url"],
    }


@router.get("/dashboard/overview", response_model=DashboardOverviewResponse)
async def dashboard_overview():
    async with get_cursor() as cur:
        await cur.execute("SELECT COUNT(*) AS total FROM nodes;")
        total_nodes = (await cur.fetchone())["total"]

        await cur.execute("SELECT COUNT(*) AS online FROM nodes WHERE status != 'offline';")
        online_nodes = (await cur.fetchone())["online"]

        await cur.execute("SELECT COUNT(*) AS total FROM trains;")
        active_trains = (await cur.fetchone())["total"]

        await cur.execute("SELECT COUNT(*) AS active FROM alerts WHERE status = 'active';")
        active_alerts = (await cur.fetchone())["active"]

        await cur.execute("SELECT COUNT(*) AS critical FROM alerts WHERE status = 'active' AND severity = 'critical';")
        critical_count = (await cur.fetchone())["critical"]

        await cur.execute("SELECT COUNT(*) AS warning FROM alerts WHERE status = 'active' AND severity = 'warning';")
        warning_count = (await cur.fetchone())["warning"]

        system_health = 0
        if total_nodes:
            system_health = round((online_nodes / total_nodes) * 100)

        await cur.execute(
            """
            SELECT alerts.*, lines.name AS line_name, zones.name AS zone_name, trains.number AS train_number
            FROM alerts
            JOIN nodes ON alerts.node_id = nodes.id
            JOIN lines ON nodes.line_id = lines.id
            JOIN zones ON lines.zone_id = zones.id
            LEFT JOIN trains ON alerts.nearest_train_id = trains.id
            WHERE alerts.status = 'active' AND alerts.severity = 'critical'
            ORDER BY alerts.detected_at DESC
            LIMIT 1;
            """
        )
        latest_critical = await cur.fetchone()

        affected_trains = []
        if latest_critical:
            await cur.execute(
                """
                SELECT trains.id, trains.number, alert_affected_trains.distance_from_incident, alert_affected_trains.eta_min, alert_affected_trains.status
                FROM alert_affected_trains
                JOIN trains ON alert_affected_trains.train_id = trains.id
                WHERE alert_affected_trains.alert_id = %s
                ORDER BY alert_affected_trains.distance_from_incident ASC
                LIMIT 5;
                """,
                (latest_critical["id"],),
            )
            affected_rows = await cur.fetchall()
            affected_trains = [
                {
                    "id": str(row["id"]),
                    "number": row["number"],
                    "distanceFromIncidentKm": float(row["distance_from_incident"]),
                    "etaMin": row["eta_min"],
                    "status": row["status"],
                }
                for row in affected_rows
            ]

    return {
        "activeAlerts": active_alerts,
        "criticalCount": critical_count,
        "warningCount": warning_count,
        "totalNodes": total_nodes,
        "onlineNodes": online_nodes,
        "activeTrains": active_trains,
        "systemHealth": system_health,
        "critical": serialize_alert(latest_critical),
        "affectedTrains": affected_trains,
    }


@router.get("/nodes")
async def list_nodes():
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT nodes.id, lines.name AS line_name, nodes.lat, nodes.lng, nodes.status, nodes.health
            FROM nodes
            JOIN lines ON nodes.line_id = lines.id
            ORDER BY nodes.id ASC;
            """
        )
        rows = await cur.fetchall()

    return [
        {
            "id": row["id"],
            "line": row["line_name"],
            "gps": {"lat": float(row["lat"]), "lng": float(row["lng"])},
            "status": row["status"],
            "health": row["health"],
        }
        for row in rows
    ]
