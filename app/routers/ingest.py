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
    logger.info(f"Received detection POST request for node_id={node_id}, timestamp={timestamp}")
    try:
        detected_at = _parse_iso_timestamp(timestamp)
    except ValueError:
        logger.error(f"Invalid timestamp format received: {timestamp}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="timestamp must be valid ISO-8601")

    image_bytes = await image.read()
    if not image_bytes:
        logger.error("Empty image file received")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="image file is empty")
    logger.info(f"Read {len(image_bytes)} bytes from uploaded image.")

    async with get_cursor() as cur:
        logger.info(f"Verifying node_id={node_id} in database...")
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
            logger.warning(f"Node ID {node_id} not found in database.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

        line_name = node_row["line_name"]
        logger.info(f"Node {node_id} verified. Belongs to line '{line_name}' in zone '{node_row['zone_name']}'.")

        try:
            logger.info("Uploading image to Cloudflare R2...")
            image_url = await upload_detection_image(image_bytes, node_id, _sanitize_timestamp(timestamp))
            logger.info(f"Image successfully uploaded to R2: {image_url}")
        except Exception as exc:
            logger.exception("R2 upload failed")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Image upload failed")

        try:
            logger.info("Sending image to Roboflow for inference...")
            roboflow_result = await infer_image(image_bytes)
            logger.info(f"Roboflow inference complete. Result: {roboflow_result}")
        except RoboflowInferenceError as exc:
            logger.exception("Roboflow inference failed")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

        hazard_count = roboflow_result["hazard_count"]
        top_prediction = roboflow_result["top_prediction"]
        risk_level = roboflow_result["risk_level"]
        
        logger.info(f"Computing risk score based on risk_level='{risk_level}' and lidar_dist_m={lidar_dist_m}...")
        risk_score = compute_risk_score(risk_level, lidar_dist_m)
        logger.info(f"Computed risk score: {risk_score}")

        alert_id = None
        object_category = None
        if top_prediction["class"]:
            object_category = f"{top_prediction['class'].title()} Detected"

        if hazard_count > 0 and risk_score >= 30:
            logger.info(f"Alert conditions met (hazard_count={hazard_count}, risk_score={risk_score}). Generating alert...")
            alert_id = await _generate_alert_id(cur, detected_at.year)
            severity = severity_from_score(risk_score)
            title = f"{object_category or 'Hazard Detected'} on {line_name}"
            confidence = round(top_prediction["confidence"] * 100)
            distance_km = round(lidar_dist_m / 1000.0, 2)

            logger.info(f"Inserting alert {alert_id} into database...")
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
            logger.info(f"Alert {alert_id} successfully saved to database.")

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
            logger.info(f"Broadcasting alert {alert_id} to connected WebSocket clients...")
            await ws_manager.broadcast(payload)
            logger.info(f"Alert {alert_id} broadcast successfully.")
        else:
            logger.info(f"Alert conditions not met (hazard_count={hazard_count}, risk_score={risk_score}). No alert generated.")

    logger.info("Detection request processed successfully. Returning response.")
    return {
        "alert_id": alert_id,
        "risk_score": risk_score,
        "hazard_count": hazard_count,
        "object_category": object_category,
        "image_url": image_url,
    }
