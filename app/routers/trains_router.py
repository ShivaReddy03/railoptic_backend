from fastapi import APIRouter, Query
from typing import Optional

from app.configuration.database import get_cursor

router = APIRouter()


def _serialize_train(row):
    return {
        "id": f"T-{row['id']}",
        "number": row["number"],
        "name": f"Train {row['number']}",
        "zone": row["zone_name"] or "",
        "line": row["line_name"] or "",
        "from": "",
        "to": "",
        "currentLocation": "",
        "destination": "",
        "speedKmh": None,
        "etaMin": None,
        "delayMin": 0,
        "status": row["status"] or "on_time",
        "distanceFromIncidentKm": None,
    }


@router.get("/trains")
async def list_trains(
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1),
    search: Optional[str] = None,
):
    query_filters = []
    params = []

    if search:
        query_filters.append("(trains.number ILIKE %s OR lines.name ILIKE %s OR zones.name ILIKE %s)")
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])

    where_clause = "WHERE " + " AND ".join(query_filters) if query_filters else ""
    limit = pageSize
    offset = (page - 1) * pageSize

    sql = f"""
        SELECT trains.id, trains.number, trains.status, trains.updated_at,
               lines.name AS line_name, zones.name AS zone_name
        FROM trains
        LEFT JOIN lines ON trains.line_id = lines.id
        LEFT JOIN zones ON lines.zone_id = zones.id
        {where_clause}
        ORDER BY trains.updated_at DESC, trains.id DESC
        LIMIT %s OFFSET %s;
    """

    count_sql = f"""
        SELECT COUNT(*) AS count
        FROM trains
        LEFT JOIN lines ON trains.line_id = lines.id
        LEFT JOIN zones ON lines.zone_id = zones.id
        {where_clause};
    """

    async with get_cursor() as cur:
        await cur.execute(count_sql, tuple(params))
        total = (await cur.fetchone())["count"]
        params.extend([limit, offset])
        await cur.execute(sql, tuple(params))
        rows = await cur.fetchall()

    data = [_serialize_train(row) for row in rows]
    return {"data": data, "total": total, "page": page, "pageSize": pageSize}


@router.get("/trains/summary")
async def trains_summary():
    async with get_cursor() as cur:
        await cur.execute("SELECT COUNT(*) AS total FROM trains;")
        total = (await cur.fetchone())["total"]

        await cur.execute("SELECT COUNT(*) AS delayed FROM trains WHERE status = 'delayed';")
        delayed = (await cur.fetchone())["delayed"]

        await cur.execute("SELECT COUNT(*) AS at_risk FROM trains WHERE status = 'at_risk';")
        at_risk = (await cur.fetchone())["at_risk"]

    return {"active": total, "delayed": delayed, "atRisk": at_risk, "total": total}
