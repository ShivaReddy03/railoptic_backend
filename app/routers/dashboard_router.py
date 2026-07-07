from fastapi import APIRouter, Query
from app.configuration.database import get_cursor
from app.schemas.dashboard import DashboardOverviewResponse

router = APIRouter()


def _classify_node_health(status, health):
    status_value = str(status or "").strip().lower()
    try:
        health_value = int(health or 0)
    except (TypeError, ValueError):
        health_value = 0

    if status_value == "offline":
        return "offline"
    if status_value == "critical" or health_value <= 30:
        return "critical"
    if status_value == "warning" or health_value <= 70:
        return "warning"
    return "normal"


def _classify_device_status(status):
    return "offline" if str(status or "").strip().lower() == "offline" else "online"


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
            WHERE alerts.status = 'active' AND alerts.severity IN ('critical', 'warning')
            ORDER BY alerts.detected_at DESC
            LIMIT 5;
            """
        )
        latest_critical_alerts = await cur.fetchall()

        affected_trains = []
        for critical_alert in latest_critical_alerts:
            await cur.execute(
                """
                SELECT trains.id, trains.number, alert_affected_trains.distance_from_incident, alert_affected_trains.eta_min, alert_affected_trains.status
                FROM alert_affected_trains
                JOIN trains ON alert_affected_trains.train_id = trains.id
                WHERE alert_affected_trains.alert_id = %s
                ORDER BY alert_affected_trains.distance_from_incident ASC
                LIMIT 5;
                """,
                (critical_alert["id"],),
            )
            affected_rows = await cur.fetchall()
            affected_trains.extend(
                [
                    {
                        "id": str(row["id"]),
                        "number": row["number"],
                        "alertId": critical_alert["id"],
                        "nodeId": critical_alert["node_id"],
                        "distanceFromIncidentKm": float(row["distance_from_incident"]),
                        "etaMin": row["eta_min"],
                        "status": row["status"],
                    }
                    for row in affected_rows
                ]
            )

    return {
        "activeAlerts": active_alerts,
        "criticalCount": critical_count,
        "warningCount": warning_count,
        "totalNodes": total_nodes,
        "onlineNodes": online_nodes,
        "activeTrains": active_trains,
        "systemHealth": system_health,
        "critical": [serialize_alert(alert) for alert in latest_critical_alerts],
        "affectedTrains": affected_trains,
    }


@router.get("/analytics/summary")
async def analytics_summary():
    async with get_cursor() as cur:
        await cur.execute("SELECT COUNT(*) AS total FROM alerts;")
        total_detections = (await cur.fetchone()).get("total")

        await cur.execute("SELECT COUNT(*) AS critical FROM alerts WHERE status = 'active' AND severity = 'critical';")
        critical_incidents = (await cur.fetchone()).get("critical")

        await cur.execute("SELECT COUNT(*) AS total FROM nodes;")
        total_nodes = (await cur.fetchone()).get("total")

        await cur.execute("SELECT COUNT(*) AS online FROM nodes WHERE status != 'offline';")
        online_nodes = (await cur.fetchone()).get("online")

        total_nodes = total_nodes or 0
        online_nodes = online_nodes or 0
        uptime = 100.0 if total_nodes == 0 else round((online_nodes / total_nodes) * 100, 1)

        detections_by_type = [
            {"name": "Human", "value": 450, "color": "#10b981"},
            {"name": "Animal", "value": 320, "color": "#3b82f6"},
            {"name": "Vehicle", "value": 150, "color": "#f59e0b"},
        ]

        detections_over_time = [
            {"date": "2023-10-01", "value": 120},
            {"date": "2023-10-02", "value": 135},
            {"date": "2023-10-03", "value": 148},
        ]

        critical_incidents = critical_incidents or 0
        incidents_by_severity = [
            {"name": "Critical", "value": max(1, critical_incidents)},
            {"name": "Warning", "value": 45},
            {"name": "Info", "value": 89},
        ]

        uptime_trend = [
            {"date": "2023-10-01", "value": 99.9},
            {"date": "2023-10-02", "value": 100.0},
            {"date": "2023-10-03", "value": 99.8},
        ]

        by_zone = [
            {"zone": "South Central", "incidents": 15},
            {"zone": "North Western", "incidents": 8},
        ]

    return {
        "totalDetections": total_detections,
        "criticalIncidents": critical_incidents,
        "detectionAccuracy": 98.5,
        "uptime": uptime,
        "detectionsByType": detections_by_type,
        "detectionsOverTime": detections_over_time,
        "incidentsBySeverity": incidents_by_severity,
        "uptimeTrend": uptime_trend,
        "byZone": by_zone,
    }


@router.get("/nodes/summary")
async def nodes_summary():
    async with get_cursor() as cur:
        await cur.execute("SELECT status, health FROM nodes;")
        rows = await cur.fetchall()

    total = len(rows)
    online = 0
    healthy = 0
    warning = 0
    critical = 0
    offline = 0

    for row in rows:
        bucket = _classify_node_health(row.get("status"), row.get("health"))
        if bucket == "offline":
            offline += 1
        else:
            online += 1

        if bucket == "normal":
            healthy += 1
        elif bucket == "warning":
            warning += 1
        elif bucket == "critical":
            critical += 1

    return {
        "total": total,
        "online": online,
        "healthy": healthy,
        "warning": warning,
        "critical": critical,
        "offline": offline,
    }


@router.get("/devices")
async def list_devices(page: int = Query(1, ge=1), pageSize: int = Query(10, ge=1), search: str | None = None):
    async with get_cursor() as cur:
        params = []
        where_clause = ""
        if search:
            where_clause = "WHERE nodes.id ILIKE %s OR lines.name ILIKE %s OR zones.name ILIKE %s"
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term])

        count_sql = f"SELECT COUNT(*) AS count FROM nodes {where_clause};"
        await cur.execute(count_sql, tuple(params))
        total = (await cur.fetchone()).get("count")

        limit = pageSize
        offset = (page - 1) * pageSize
        sql = f"""
            SELECT nodes.id, nodes.id AS node_id, lines.name AS line_name,
                   zones.name AS zone_name, nodes.status, nodes.health, nodes.last_seen AS updated_at
            FROM nodes
            JOIN lines ON nodes.line_id = lines.id
            JOIN zones ON lines.zone_id = zones.id
            {where_clause}
            ORDER BY nodes.last_seen DESC NULLS LAST, nodes.id DESC
            LIMIT %s OFFSET %s;
        """
        await cur.execute(sql, tuple(params + [limit, offset]))
        rows = await cur.fetchall()

    data = []
    for row in rows:
        health_value = _classify_node_health(row.get("status"), row.get("health"))
        status_value = _classify_device_status(row.get("status"))
        data.append(
            {
                "id": row["id"],
                "name": f"Camera Node {row['id']}",
                "nodeId": row.get("node_id") or row["id"],
                "location": f"{row.get('line_name', '')} / {row.get('zone_name', '')}".strip(" /"),
                "type": "Vision Sensor",
                "health": health_value,
                "status": status_value,
                "lastSeen": row["updated_at"].isoformat() if row.get("updated_at") else None,
                "sensors": {
                    "ok": 4,
                    "warn": 0,
                    "critical": 0,
                    "offline": 0,
                },
                "components": [
                    {"name": "Primary Lens", "status": "normal", "lastMaintenance": "2023-09-15"},
                    {"name": "Network Module", "status": "normal", "lastMaintenance": "2023-09-15"},
                ],
            }
        )

    return {"data": data, "total": total, "page": page, "pageSize": pageSize}


@router.get("/nodes")
async def list_nodes():
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT nodes.id,
                   lines.name AS line_name,
                   nodes.lat,
                   nodes.lng,
                   CASE
                       WHEN EXISTS (
                           SELECT 1
                           FROM alerts
                           WHERE node_id = nodes.id AND status = 'active' AND severity = 'critical'
                       ) THEN 'critical'
                       WHEN EXISTS (
                           SELECT 1
                           FROM alerts
                           WHERE node_id = nodes.id AND status = 'active' AND severity IN ('warning', 'info')
                       ) THEN 'warning'
                       ELSE nodes.status
                   END AS current_status,
                   nodes.health,
                   (
                       SELECT id
                       FROM alerts
                       WHERE node_id = nodes.id AND status = 'active'
                       ORDER BY detected_at DESC
                       LIMIT 1
                   ) AS current_alert_id
            FROM nodes
            JOIN lines ON nodes.line_id = lines.id
            ORDER BY nodes.id ASC;
            """
        )
        rows = await cur.fetchall()

    out = []
    for row in rows:
        current_alert = None
        status = str(row.get("current_status") or "").strip().lower()
        # Only expose currentAlertId to frontend when the node is in warning/critical state
        if status in ("warning", "critical"):
            current_alert = row.get("current_alert_id")

        out.append(
            {
                "id": row["id"],
                "line": row["line_name"],
                "gps": {"lat": float(row["lat"]), "lng": float(row["lng"])},
                "status": row["current_status"],
                "health": row["health"],
                "currentAlertId": current_alert,
            }
        )

    return out
