import logging
from datetime import datetime, timezone
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from app.schemas.ingest import IngestResponse
from app.configuration.database import get_cursor
from app.models.enums import NodeStatusEnum
from app.services.r2 import upload_detection_image
from app.services.roboflow import RoboflowInferenceError, infer_image
from app.services.risk import compute_risk_score, severity_from_score
from app.routers.ws_router import ws_manager

router = APIRouter()
logger = logging.getLogger(__name__)


def _select_train_candidates(train_rows, line_id: int | None):
    if not train_rows:
        return []

    same_line = [row for row in train_rows if row.get("line_id") == line_id]
    fallback = [row for row in train_rows if row.get("line_id") != line_id and row.get("line_id") is not None]
    candidates = same_line or (fallback or train_rows)

    status_order = {"delayed": 0, "at_risk": 1, "monitor": 2, "safe": 3, "on_time": 4}

    def sort_key(row):
        status = str(row.get("status") or "on_time").strip().lower()
        updated_at = row.get("updated_at")
        if updated_at is None:
            updated_at = datetime.min.replace(tzinfo=timezone.utc)
        return (status_order.get(status, 99), updated_at, row.get("id", 0))

    return sorted(candidates, key=sort_key)


async def _assign_trains_to_alert(cur, alert_id: str, line_id: int | None):
    await cur.execute(
        "SELECT id, number, line_id, status, updated_at FROM trains WHERE line_id IS NOT NULL OR line_id IS NULL;"
    )
    train_rows = await cur.fetchall()
    candidates = _select_train_candidates(train_rows, line_id)
    if not candidates:
        return None

    nearest_train = candidates[0]
    affected_candidates = candidates[:4]

    await cur.execute(
        "UPDATE alerts SET nearest_train_id = %s WHERE id = %s;",
        (nearest_train["id"], alert_id),
    )

    for idx, train_row in enumerate(affected_candidates):
        distance_from_incident = round(0.5 + (idx * 0.8), 2)
        eta_min = max(2, int(distance_from_incident * 10))
        await cur.execute(
            "INSERT INTO alert_affected_trains (alert_id, train_id, distance_from_incident, eta_min, status) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (alert_id, train_id) DO NOTHING;",
            (
                alert_id,
                train_row["id"],
                distance_from_incident,
                eta_min,
                train_row["status"],
            ),
        )

    return nearest_train


def _parse_iso_timestamp(timestamp: str) -> datetime:
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    return datetime.fromisoformat(timestamp)


def _coerce_detected_at(timestamp: str | None) -> datetime:
    if timestamp:
        return _parse_iso_timestamp(timestamp)
    return datetime.now().astimezone()


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


async def _resolve_active_alerts_for_node(cur, node_id: str, resolved_at: datetime) -> list[str]:
    await cur.execute(
        "SELECT id FROM alerts WHERE node_id = %s AND status = 'active' ORDER BY detected_at DESC;",
        (node_id,),
    )
    rows = await cur.fetchall()
    if not rows:
        return []

    await cur.execute(
        "UPDATE alerts SET status = 'resolved', resolved_at = %s WHERE node_id = %s AND status = 'active';",
        (resolved_at, node_id),
    )
    return [row["id"] for row in rows]


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
    timestamp: str | None = Form(None),
):
    logger.info(f"Received detection POST request for node_id={node_id}, timestamp={timestamp}")
    try:
        detected_at = _coerce_detected_at(timestamp)
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
            "SELECT nodes.id, lines.id AS line_id, lines.name AS line_name, zones.name AS zone_name "
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
        line_id = node_row.get("line_id")
        logger.info(f"Node {node_id} verified. Belongs to line '{line_name}' in zone '{node_row['zone_name']}'.")

        try:
            logger.info("Uploading image to Cloudflare R2...")
            image_url = await upload_detection_image(image_bytes, node_id, _sanitize_timestamp(timestamp or detected_at.isoformat()))
            logger.info(f"Image successfully uploaded to R2: {image_url}")
        except Exception as exc:
            logger.exception("R2 upload failed")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Image upload failed")

        try:
            logger.info("Sending R2 image URL to Roboflow for inference...")
            roboflow_result = await infer_image(image_url)
            logger.info(f"Roboflow inference complete. Result: {roboflow_result}")
        except RoboflowInferenceError as exc:
            logger.exception("Roboflow inference failed")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

        hazard_count = roboflow_result["hazard_count"]
        top_prediction = roboflow_result["top_prediction"]
        risk_level = roboflow_result["risk_level"]
        object_area_px = roboflow_result.get("object_area_px")
        max_area_px = roboflow_result.get("max_area_px")

        logger.info(
            f"Computing risk score based on risk_level='{risk_level}', confidence={top_prediction['confidence']}, "
            f"hazard_count={hazard_count}, class={top_prediction['class']}, lidar_dist_m={lidar_dist_m}..."
        )
        risk_score = compute_risk_score(
            risk_level,
            lidar_dist_m,
            confidence=top_prediction.get("confidence"),
            hazard_count=hazard_count,
            class_name=top_prediction.get("class"),
            object_area_px=object_area_px,
            max_area_px=max_area_px,
        )
        logger.info(f"Computed risk score: {risk_score}")

        alert_id = None
        object_category = None
        if top_prediction["class"]:
            object_category = f"{top_prediction['class'].title()} Detected"
        object_category_text = object_category or "Hazard Detected"
        severity = severity_from_score(risk_score, top_prediction.get("class"))

        if hazard_count > 0 and risk_score >= 30:
            logger.info(f"Alert conditions met (hazard_count={hazard_count}, risk_score={risk_score}). Generating alert...")

            # Keep alerts from spamming for the same node and same object type.
            await cur.execute(
                "SELECT id, status, severity, object_category FROM alerts "
                "WHERE node_id = %s AND status = 'active' "
                "ORDER BY detected_at DESC LIMIT 1;",
                (node_id,),
            )
            existing_alert = await cur.fetchone()
            if existing_alert and existing_alert["object_category"] == object_category_text and existing_alert["severity"] == severity:
                alert_id = existing_alert["id"]
                logger.info(f"Existing active alert {alert_id} on node {node_id} matched current detection; skipping duplicate alert creation.")
            else:
                # Resolve any existing active alerts for this node before creating a new one.
                await cur.execute(
                    "UPDATE alerts SET status = 'resolved', resolved_at = NOW() WHERE node_id = %s AND status = 'active';",
                    (node_id,),
                )
                alert_id = await _generate_alert_id(cur, detected_at.year)
                title = f"{object_category_text} on {line_name}"
                confidence = round(top_prediction["confidence"] * 100)
                distance_km = round(lidar_dist_m / 1000.0, 2)

                logger.info(f"Inserting alert {alert_id} into database...")
                await cur.execute(
                    "INSERT INTO alerts (id, node_id, object_category, title, source, severity, status, confidence, risk_score, distance_km, eta_sec, image_url, detected_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);",
                    (
                        alert_id,
                        node_id,
                        object_category_text,
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
                nearest_train = await _assign_trains_to_alert(cur, alert_id, line_id)
                if nearest_train:
                    logger.info(f"Assigned nearest train {nearest_train['id']} to alert {alert_id}.")
                else:
                    logger.info(f"No trains available to assign to alert {alert_id}.")

                payload = {
                    "event": "new_alert",
                    "payload": {
                        "id": alert_id,
                        "date": detected_at.date().isoformat(),
                        "time": detected_at.time().isoformat(timespec="seconds"),
                        "zone": node_row["zone_name"],
                        "line": line_name,
                        "node": node_id,
                        "objectCategory": object_category_text,
                        "title": title,
                        "source": "AI Camera",
                        "location": f"{line_name} - Node {node_id}",
                        "severity": severity,
                        "status": "active",
                        "confidence": confidence,
                        "riskScore": risk_score,
                        "nearestTrain": nearest_train["number"] if nearest_train else None,
                        "distanceKm": distance_km,
                        "etaSec": None,
                        "imageUrl": image_url,
                    },
                }
                logger.info(f"Broadcasting alert {alert_id} to connected WebSocket clients...")
                await ws_manager.broadcast(payload)
                logger.info(f"Alert {alert_id} broadcast successfully.")
        else:
            resolved_alert_ids = await _resolve_active_alerts_for_node(cur, node_id, detected_at)
            if resolved_alert_ids:
                logger.info(
                    f"Alert conditions not met (hazard_count={hazard_count}, risk_score={risk_score}). "
                    f"Resolving {len(resolved_alert_ids)} active alert(s) on node {node_id}."
                )
            else:
                logger.info(f"Alert conditions not met (hazard_count={hazard_count}, risk_score={risk_score}). No alert generated.")

        if hazard_count == 0:
            node_status = NodeStatusEnum.normal.value
        elif severity == "critical":
            node_status = NodeStatusEnum.critical.value
        else:
            node_status = NodeStatusEnum.warning.value

        await cur.execute(
            "UPDATE nodes SET status = %s, last_seen = %s WHERE id = %s;",
            (node_status, detected_at, node_id),
        )
        logger.info(f"Node {node_id} status updated to {node_status}.")

    logger.info("Detection request processed successfully. Returning response.")
    return {
        "alert_id": alert_id,
        "risk_score": risk_score,
        "hazard_count": hazard_count,
        "object_category": object_category,
        "image_url": image_url,
    }
