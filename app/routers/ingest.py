import logging
from datetime import datetime
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from app.schemas.ingest import IngestResponse
from app.configuration.database import get_cursor
from app.services.r2 import upload_detection_image
from app.services.roboflow import RoboflowInferenceError, infer_image
from app.services.risk import compute_risk_score, severity_from_score
from app.routers.ws_router import ws_manager

router = APIRouter()
logger = logging.getLogger(__name__)


def _parse_iso_timestamp(timestamp: str) -> datetime:
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    return datetime.fromisoformat(timestamp)


def _sanitize_timestamp(timestamp: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in timestamp)


async def _generate_alert_id(cur, year: int) -> str:
    prefix = f"ALT-{year}-"
    await cur.execute("SELECT id FROM alerts WHERE id LIKE %s ORDER BY id DESC LIMIT 1;", (prefix + "%",))
    row = await cur.fetchone()
    if row and row["id"]:
        try:
            seq = int(row["id"].split("-")[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


@router.post(
    "/detection",
    response_model=IngestResponse,
    summary="Ingest detection",
    description="Upload an image from a node, run Roboflow inference, compute risk, and create an alert when required.",
)
async def ingest_detection(
    image: UploadFile = File(...),
    node_id: str = Form(...),
    lidar_dist_m: float = Form(...),
    timestamp: str = Form(...),
):
    try:
        detected_at = _parse_iso_timestamp(timestamp)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="timestamp must be valid ISO-8601")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="image file is empty")

    async with get_cursor() as cur:
        await cur.execute(
            "SELECT nodes.id, lines.name AS line_name, zones.name AS zone_name "
            "FROM nodes "
            "JOIN lines ON nodes.line_id = lines.id "
            "JOIN zones ON lines.zone_id = zones.id "
            "WHERE nodes.id = %s;",
            (node_id,),
        )
        node_row = await cur.fetchone()
        if not node_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

        line_name = node_row["line_name"]

        try:
            image_url = await upload_detection_image(image_bytes, node_id, _sanitize_timestamp(timestamp))
        except Exception as exc:
            logger.exception("R2 upload failed")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Image upload failed")

        try:
            roboflow_result = await infer_image(image_bytes)
        except RoboflowInferenceError as exc:
            logger.exception("Roboflow inference failed")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

        hazard_count = roboflow_result["hazard_count"]
        top_prediction = roboflow_result["top_prediction"]
        risk_level = roboflow_result["risk_level"]
        risk_score = compute_risk_score(risk_level, lidar_dist_m)

        alert_id = None
        object_category = None
        if top_prediction["class"]:
            object_category = f"{top_prediction['class'].title()} Detected"

        if hazard_count > 0 and risk_score >= 30:
            alert_id = await _generate_alert_id(cur, detected_at.year)
            severity = severity_from_score(risk_score)
            title = f"{object_category or 'Hazard Detected'} on {line_name}"
            confidence = round(top_prediction["confidence"] * 100)
            distance_km = round(lidar_dist_m / 1000.0, 2)

            await cur.execute(
                "INSERT INTO alerts (id, node_id, object_category, title, source, severity, status, confidence, risk_score, distance_km, eta_sec, image_url, detected_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);",
                (
                    alert_id,
                    node_id,
                    object_category or "Hazard Detected",
                    title,
                    "AI Camera",
                    severity,
                    "active",
                    confidence,
                    risk_score,
                    distance_km,
                    None,
                    image_url,
                    detected_at,
                ),
            )

            payload = {
                "event": "new_alert",
                "payload": {
                    "id": alert_id,
                    "date": detected_at.date().isoformat(),
                    "time": detected_at.time().isoformat(timespec="seconds"),
                    "zone": node_row["zone_name"],
                    "line": line_name,
                    "node": node_id,
                    "objectCategory": object_category,
                    "title": title,
                    "source": "AI Camera",
                    "location": f"{line_name} - Node {node_id}",
                    "severity": severity,
                    "status": "active",
                    "confidence": confidence,
                    "riskScore": risk_score,
                    "nearestTrain": None,
                    "distanceKm": distance_km,
                    "etaSec": None,
                    "imageUrl": image_url,
                },
            }
            await ws_manager.broadcast(payload)

    return {
        "alert_id": alert_id,
        "risk_score": risk_score,
        "hazard_count": hazard_count,
        "object_category": object_category,
        "image_url": image_url,
    }
