from fastapi import APIRouter, Query
from typing import Optional

from app.configuration.database import get_cursor

router = APIRouter()


@router.get("/reports")
async def list_reports(
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1),
    search: Optional[str] = None,
):
    query_filters = []
    params = []

    if search:
        query_filters.append("(id ILIKE %s OR name ILIKE %s OR type ILIKE %s)")
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])

    where_clause = "WHERE " + " AND ".join(query_filters) if query_filters else ""
    limit = pageSize
    offset = (page - 1) * pageSize

    sql = f"""
        SELECT 'REP-2026-001' AS id, 'Weekly Incident Report' AS name, 'Incidents' AS type,
               '2026-06-21 to 2026-06-28' AS date_range,
               '2026-06-29T08:00:00Z' AS generated_on,
               'System' AS generated_by, 'PDF' AS format, 2.4 AS size_mb
        {where_clause}
        ORDER BY generated_on DESC
        LIMIT %s OFFSET %s;
    """

    count_sql = f"""
        SELECT COUNT(*) AS count
        FROM (SELECT 'REP-2026-001' AS id, 'Weekly Incident Report' AS name, 'Incidents' AS type) AS reports
        {where_clause};
    """

    async with get_cursor() as cur:
        await cur.execute(count_sql, tuple(params))
        total = (await cur.fetchone())["count"]
        params.extend([limit, offset])
        await cur.execute(sql, tuple(params))
        rows = await cur.fetchall()

    data = [
        {
            "id": row["id"],
            "name": row["name"],
            "type": row["type"],
            "dateRange": row["date_range"],
            "generatedOn": row["generated_on"],
            "generatedBy": row["generated_by"],
            "format": row["format"],
            "sizeMb": float(row["size_mb"]),
        }
        for row in rows
    ]
    return {"data": data, "total": total, "page": page, "pageSize": pageSize}


@router.get("/reports/summary")
async def reports_summary():
    return {"total": 128, "scheduled": 28, "manual": 100, "exportedGb": 12.4}
