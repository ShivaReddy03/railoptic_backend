from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse
from typing import Optional

from app.configuration.database import get_cursor
from app.routers.ws_router import ws_manager

router = APIRouter()


def _normalize_alert_row(alert):
    if isinstance(alert, list):
        return alert[0] if alert else {}
    return alert or {}


def row_to_alert_out(alert, line_name=None, zone_name=None):
    alert = _normalize_alert_row(alert)
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
        "escalatedTo": alert.get("escalated_to"),
        "escalatedAt": alert["escalated_at"].isoformat() if alert.get("escalated_at") else None,
        "escalatedBy": alert.get("escalated_by"),
    }


async def _alerts_support_escalation_target(cur) -> bool:
    await cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'alerts' AND column_name = 'escalated_to'
        ) AS exists;
        """
    )
    row = _normalize_alert_row(await cur.fetchone())
    if "exists" in row:
        return bool(row.get("exists"))
    return True


@router.get("/alerts/summary")
async def alerts_summary():
    async with get_cursor() as cur:
        await cur.execute("SELECT COUNT(*) FROM alerts;")
        total = _normalize_alert_row(await cur.fetchone()).get("count", 0)

        await cur.execute("SELECT COUNT(*) FROM alerts WHERE status = 'active';")
        active = _normalize_alert_row(await cur.fetchone()).get("count", 0)
        await cur.execute("SELECT COUNT(*) FROM alerts WHERE status = 'active' AND severity = 'critical';")
        critical = _normalize_alert_row(await cur.fetchone()).get("count", 0)
        await cur.execute("SELECT COUNT(*) FROM alerts WHERE status = 'active' AND severity = 'warning';")
        warning = _normalize_alert_row(await cur.fetchone()).get("count", 0)
        await cur.execute("SELECT COUNT(*) FROM alerts WHERE status = 'active' AND severity = 'info';")
        info = _normalize_alert_row(await cur.fetchone()).get("count", 0)

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
    escalated_to: str = Query("all", pattern="^(all|rpf|maintenance|none)$"),
):
    async with get_cursor() as cur:
        supports_escalation_target = await _alerts_support_escalation_target(cur)

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

        if supports_escalation_target and escalated_to != "all":
            if escalated_to == "none":
                query_filters.append("alerts.escalated_to IS NULL")
            else:
                query_filters.append("alerts.escalated_to = %s")
                params.append(escalated_to)

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

        await cur.execute(count_sql, tuple(params))
        total = _normalize_alert_row(await cur.fetchone()).get("count", 0)
        params.extend([limit, offset])
        await cur.execute(sql, tuple(params))
        rows = await cur.fetchall()

    data = [row_to_alert_out(row, line_name=_normalize_alert_row(row).get("line_name"), zone_name=_normalize_alert_row(row).get("zone_name")) for row in rows]
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
        row = _normalize_alert_row(await cur.fetchone())

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    return row_to_alert_out(row, line_name=row.get("line_name"), zone_name=row.get("zone_name"))


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    async with get_cursor() as cur:
        await cur.execute("SELECT id FROM alerts WHERE id = %s", (alert_id,))
        if not _normalize_alert_row(await cur.fetchone()):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
        await cur.execute(
            "UPDATE alerts SET status = 'acknowledged', acknowledged_at = NOW() WHERE id = %s RETURNING id;",
            (alert_id,),
        )
        await cur.execute("DELETE FROM alert_affected_trains WHERE alert_id = %s;", (alert_id,))
        # Recompute node status based on remaining active alerts for the node
        await cur.execute("SELECT node_id FROM alerts WHERE id = %s", (alert_id,))
        node_row = _normalize_alert_row(await cur.fetchone())
        if node_row:
            node_id = node_row["node_id"]
            await cur.execute(
                "SELECT severity FROM alerts WHERE node_id = %s AND status = 'active' "
                "ORDER BY CASE WHEN severity='critical' THEN 3 WHEN severity='warning' THEN 2 ELSE 1 END DESC LIMIT 1;",
                (node_id,),
            )
            sev_row = _normalize_alert_row(await cur.fetchone())
            if sev_row and sev_row.get("severity"):
                node_status = "critical" if sev_row["severity"] == "critical" else "warning"
            else:
                node_status = "normal"

            await cur.execute("UPDATE nodes SET status = %s WHERE id = %s;", (node_status, node_id))

            # Fetch updated alert row for broadcasting
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
            alert_row = _normalize_alert_row(await cur.fetchone())
            if alert_row:
                try:
                    await ws_manager.broadcast({"event": "alert_updated", "payload": row_to_alert_out(alert_row, line_name=alert_row.get("line_name"), zone_name=alert_row.get("zone_name"))} )
                except Exception:
                    pass
            try:
                await ws_manager.broadcast({"event": "node_update", "payload": {"node": node_id, "status": node_status}})
            except Exception:
                pass
    return {"message": "Alert acknowledged"}


@router.post("/alerts/{alert_id}/escalate")
async def escalate_alert(alert_id: str, payload: dict):
    note = payload.get("note", "")
    escalated_to = payload.get("escalated_to")
    escalated_by = payload.get("escalated_by")
    async with get_cursor() as cur:
        await cur.execute("SELECT id, notes, severity FROM alerts WHERE id = %s", (alert_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
        if isinstance(row, list):
            row = row[0]

        existing_notes = row["notes"] or ""
        combined_notes = (existing_notes + "\n" + note).strip() if note else existing_notes
        
        has_escalation = await _alerts_support_escalation_target(cur)
        if has_escalation and (escalated_to or escalated_by):
            await cur.execute(
                "UPDATE alerts SET severity = 'critical', notes = %s, escalated_to = %s, escalated_at = NOW(), escalated_by = %s WHERE id = %s RETURNING id;",
                (combined_notes, escalated_to, escalated_by, alert_id),
            )
        else:
            await cur.execute(
                "UPDATE alerts SET severity = 'critical', notes = %s WHERE id = %s RETURNING id;",
                (combined_notes, alert_id),
            )

        # Update node status to critical (recompute for consistency)
        await cur.execute("SELECT node_id FROM alerts WHERE id = %s", (alert_id,))
        node_row = await cur.fetchone()
        if node_row:
            node_id = node_row["node_id"]
            node_status = "critical"
            await cur.execute("UPDATE nodes SET status = %s WHERE id = %s;", (node_status, node_id))

            # Fetch updated alert row for broadcasting
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
            alert_row = _normalize_alert_row(await cur.fetchone())
            if alert_row:
                try:
                    await ws_manager.broadcast({"event": "alert_updated", "payload": row_to_alert_out(alert_row, line_name=alert_row.get("line_name"), zone_name=alert_row.get("zone_name"))} )
                except Exception:
                    pass
            try:
                await ws_manager.broadcast({"event": "node_update", "payload": {"node": node_id, "status": node_status}})
            except Exception:
                pass

    return {"message": "Alert escalated", "note": note}


@router.get("/alerts/{alert_id}/export")
async def export_alert(alert_id: str, format: str = Query("pdf", pattern="^(pdf|csv)$")):
    async with get_cursor() as cur:
        await cur.execute("SELECT id FROM alerts WHERE id = %s", (alert_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return JSONResponse({"message": f"Export placeholder for {alert_id} as {format}"}, status_code=200)
