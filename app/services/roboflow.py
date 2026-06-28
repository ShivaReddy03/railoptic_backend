import asyncio
import os
import tempfile
import logging
import base64
import httpx

logger = logging.getLogger(__name__)


class RoboflowInferenceError(Exception):
    pass


def _normalize_risk_levels(values):
    if not values:
        return "none"
    levels = [str(v).strip().lower() for v in values if v]
    if "high" in levels:
        return "high"
    if "medium" in levels:
        return "medium"
    if "low" in levels:
        return "low"
    return "none"


def _extract_top_prediction(data: dict) -> dict:
    predictions = []
    if hazard := data.get("hazard_predictions_in_roi"):
        predictions = hazard.get("predictions", []) or []
    top_prediction = {"class": None, "confidence": 0.0}
    if predictions:
        best = max(predictions, key=lambda item: float(item.get("confidence", 0.0) or 0.0))
        top_prediction["class"] = best.get("class") or best.get("label")
        top_prediction["confidence"] = float(best.get("confidence", 0.0) or 0.0)
    elif boundaries := data.get("object_boundaries_and_sizes"):
        if isinstance(boundaries, list) and boundaries:
            best = max(boundaries, key=lambda item: float(item.get("confidence", 0.0) or 0.0))
            top_prediction["class"] = best.get("class") or best.get("label")
            top_prediction["confidence"] = float(best.get("confidence", 0.0) or 0.0)
    return top_prediction


async def infer_image(image_bytes: bytes) -> dict:
    url = os.getenv("ROBOFLOW_WORKFLOW_URL")
    api_key = os.getenv("ROBOFLOW_API_KEY")
    workspace_name = os.getenv("ROBOFLOW_WORKFLOW_WORKSPACE")
    workflow_id = os.getenv("ROBOFLOW_WORKFLOW_ID")

    if not url or not api_key or not workspace_name or not workflow_id:
        raise RoboflowInferenceError("Missing Roboflow workflow configuration")


    try:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        api_url = f"{url.rstrip('/')}/infer/workflows/{workspace_name}/{workflow_id}"
        
        payload = {
            "api_key": api_key,
            "inputs": {
                "image": {
                    "type": "base64",
                    "value": base64_image
                }
            }
        }
        
        # Increased timeout to 120 seconds for cold starts
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(api_url, json=payload)
            
            # Read response
            try:
                data = response.json()
                print("API Response:", data)
            except Exception:
                response.raise_for_status()
                raise

            # If there's an error in the response json, log and raise
            if response.status_code >= 400:
                error_msg = data.get("error", {}).get("message") if isinstance(data, dict) else str(data)
                raise Exception(f"API Error ({response.status_code}): {error_msg}")

    except Exception as exc:
        logger.exception("Roboflow inference failed")
        raise RoboflowInferenceError(
            f"Roboflow inference failed: {exc}"
        ) from exc

    hazard_count = int(data.get("hazard_count") or 0)
    if hazard_count == 0 and isinstance(data.get("results"), list) and data["results"]:
        hazard_count = int(data["results"][0].get("hazard_count") or 0)

    hazard_levels = []
    if hazard := data.get("hazard_predictions_in_roi"):
        hazard_levels.extend(
            p.get("risk_level")
            for p in hazard.get("predictions", [])
            if p.get("risk_level")
        )
    if not hazard_levels and isinstance(data.get("results"), list):
        for item in data["results"]:
            if hazard := item.get("hazard_predictions_in_roi"):
                hazard_levels.extend(
                    p.get("risk_level")
                    for p in hazard.get("predictions", [])
                    if p.get("risk_level")
                )
    for item in data.get("object_boundaries_and_sizes", []) or []:
        if item.get("danger_level"):
            hazard_levels.append(item.get("danger_level"))

    risk_level = _normalize_risk_levels(hazard_levels)
    top_prediction = _extract_top_prediction(data)
    max_area_px = data.get("max_area_px")

    return {
        "hazard_count": hazard_count,
        "risk_level": risk_level,
        "top_prediction": top_prediction,
        "max_area_px": max_area_px,
    }
