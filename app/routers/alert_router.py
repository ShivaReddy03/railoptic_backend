from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse
from typing import Optional

from app.configuration.database import get_cursor

router = APIRouter()


def row_to_alert_out(alert, line_name=None, zone_name=None):
    date = alert["detected_at"].date().isoformat()
    time = alert["detected_at"].time().isoformat(timespec="seconds")
    return {
        "id": alert["id"],
        "date": date,
        "time": time,
        "zone": zone_name or "",
        "line": line_name or "",
        "node": alert["node_id"],
        "objectCategory": alert["object_category"],
        "title": alert["title"],
        "source": alert["source"],
        "location": f"{line_name or ''} - {alert['node_id']}",
        "severity": alert["severity"],
        "status": alert["status"],
        "confidence": alert["confidence"],
        "riskScore": alert["risk_score"],
        "nearestTrain": alert["train_number"],
        "distanceKm": float(alert["distance_km"]) if alert["distance_km"] is not None else None,
        "etaSec": alert["eta_sec"],
        "imageUrl": alert["image_url"],
    }


@router.get("/alerts/summary")
async def alerts_summary():
    async with get_cursor() as cur:
        await cur.execute("SELECT COUNT(*) FROM alerts;")
        total = (await cur.fetchone())["count"]

        await cur.execute("SELECT COUNT(*) FROM alerts WHERE status = 'active';")
        active = (await cur.fetchone())["count"]
        await cur.execute("SELECT COUNT(*) FROM alerts WHERE status = 'active' AND severity = 'critical';")
        critical = (await cur.fetchone())["count"]
        await cur.execute("SELECT COUNT(*) FROM alerts WHERE status = 'active' AND severity = 'warning';")
        warning = (await cur.fetchone())["count"]
        await cur.execute("SELECT COUNT(*) FROM alerts WHERE status = 'active' AND severity = 'info';")
        info = (await cur.fetchone())["count"]

    return {"active": active, "critical": critical, "warning": warning, "info": info, "total": total}


@router.get("/alerts")
async def list_alerts(
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1),
    search: Optional[str] = None,
    severity: str = Query("all", pattern="^(all|critical|warning|info)$"),
    status: str = Query("all", pattern="^(all|active|acknowledged|resolved)$"),
    zone: Optional[str] = None,
    line: Optional[str] = None,
):
    query_filters = []
    params = []

    if search:
        query_filters.append("(alerts.id ILIKE %s OR alerts.object_category ILIKE %s OR alerts.node_id ILIKE %s)")
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])

    if severity != "all":
        query_filters.append("alerts.severity = %s")
        params.append(severity)

    if status != "all":
        query_filters.append("alerts.status = %s")
        params.append(status)

    if zone:
        query_filters.append("zones.name = %s")
        params.append(zone)

    if line:
        query_filters.append("lines.name = %s")
        params.append(line)

    where_clause = "WHERE " + " AND ".join(query_filters) if query_filters else ""
    limit = pageSize
    offset = (page - 1) * pageSize

    sql = f"""
        SELECT alerts.*, nodes.line_id, lines.name AS line_name, zones.name AS zone_name,
               trains.number AS train_number
        FROM alerts
        JOIN nodes ON alerts.node_id = nodes.id
        JOIN lines ON nodes.line_id = lines.id
        JOIN zones ON lines.zone_id = zones.id
        LEFT JOIN trains ON alerts.nearest_train_id = trains.id
        {where_clause}
        ORDER BY alerts.detected_at DESC, alerts.id DESC
        LIMIT %s OFFSET %s;
    """

    count_sql = f"""
        SELECT COUNT(*) AS count
        FROM alerts
        JOIN nodes ON alerts.node_id = nodes.id
        JOIN lines ON nodes.line_id = lines.id
        JOIN zones ON lines.zone_id = zones.id
        {where_clause};
    """

    async with get_cursor() as cur:
        await cur.execute(count_sql, tuple(params))
        total = (await cur.fetchone())["count"]
        params.extend([limit, offset])
        await cur.execute(sql, tuple(params))
        rows = await cur.fetchall()

    data = [row_to_alert_out(row, line_name=row["line_name"], zone_name=row["zone_name"]) for row in rows]
    return {"data": data, "total": total, "page": page, "pageSize": pageSize}


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: str):
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT alerts.*, nodes.line_id, lines.name AS line_name, zones.name AS zone_name,
                   trains.number AS train_number
            FROM alerts
            JOIN nodes ON alerts.node_id = nodes.id
            JOIN lines ON nodes.line_id = lines.id
            JOIN zones ON lines.zone_id = zones.id
            LEFT JOIN trains ON alerts.nearest_train_id = trains.id
            WHERE alerts.id = %s
            """,
            (alert_id,),
        )
        row = await cur.fetchone()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    return row_to_alert_out(row, line_name=row["line_name"], zone_name=row["zone_name"])


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    async with get_cursor() as cur:
        await cur.execute("SELECT id FROM alerts WHERE id = %s", (alert_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
        await cur.execute(
            "UPDATE alerts SET status = 'acknowledged', acknowledged_at = NOW() WHERE id = %s RETURNING id;",
            (alert_id,),
        )
    return {"message": "Alert acknowledged"}


@router.post("/alerts/{alert_id}/escalate")
async def escalate_alert(alert_id: str, payload: dict):
    note = payload.get("note", "")
    async with get_cursor() as cur:
        await cur.execute("SELECT id, notes, severity FROM alerts WHERE id = %s", (alert_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

        existing_notes = row["notes"] or ""
        combined_notes = (existing_notes + "\n" + note).strip() if note else existing_notes
        await cur.execute(
            "UPDATE alerts SET severity = 'critical', notes = %s WHERE id = %s RETURNING id;",
            (combined_notes, alert_id),
        )

    return {"message": "Alert escalated", "note": note}


@router.get("/alerts/{alert_id}/export")
async def export_alert(alert_id: str, format: str = Query("pdf", pattern="^(pdf|csv)$")):
    async with get_cursor() as cur:
        await cur.execute("SELECT id FROM alerts WHERE id = %s", (alert_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return JSONResponse({"message": f"Export placeholder for {alert_id} as {format}"}, status_code=200)
