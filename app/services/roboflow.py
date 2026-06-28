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


def _summarize_inference_response(data: dict) -> dict:
    if not isinstance(data, dict):
        return {
            "hazard_count": 0,
            "risk_level": "none",
            "top_prediction": {"class": None, "confidence": 0.0},
            "max_area_px": None,
        }

    if isinstance(data.get("outputs"), list) and data["outputs"]:
        candidate = data["outputs"][0]
        if not isinstance(candidate, dict):
            candidate = {}
    else:
        candidate = data

    hazard_count = int(candidate.get("hazard_count") or data.get("hazard_count") or 0)
    if hazard_count == 0 and isinstance(candidate.get("results"), list) and candidate["results"]:
        hazard_count = int(candidate["results"][0].get("hazard_count") or 0)

    hazard_levels = []
    if hazard := candidate.get("hazard_predictions_in_roi"):
        hazard_levels.extend(
            p.get("risk_level")
            for p in hazard.get("predictions", [])
            if p.get("risk_level")
        )
    if not hazard_levels and isinstance(candidate.get("results"), list):
        for item in candidate["results"]:
            if hazard := item.get("hazard_predictions_in_roi"):
                hazard_levels.extend(
                    p.get("risk_level")
                    for p in hazard.get("predictions", [])
                    if p.get("risk_level")
                )
    if not hazard_levels and isinstance(data.get("outputs"), list):
        for item in data["outputs"]:
            if not isinstance(item, dict):
                continue
            if hazard := item.get("hazard_predictions_in_roi"):
                hazard_levels.extend(
                    p.get("risk_level")
                    for p in hazard.get("predictions", [])
                    if p.get("risk_level")
                )
            if not hazard_levels and item.get("risk_level"):
                hazard_levels.append(item.get("risk_level"))

    for item in candidate.get("object_boundaries_and_sizes", []) or []:
        if item.get("danger_level"):
            hazard_levels.append(item.get("danger_level"))

    risk_level = _normalize_risk_levels(hazard_levels)
    top_prediction = _extract_top_prediction(candidate)
    max_area_px = candidate.get("max_area_px") or data.get("max_area_px")

    return {
        "hazard_count": hazard_count,
        "risk_level": risk_level,
        "top_prediction": top_prediction,
        "max_area_px": max_area_px,
    }


async def infer_image(image_url: str) -> dict:
    url = os.getenv("ROBOFLOW_WORKFLOW_URL")
    api_key = os.getenv("ROBOFLOW_API_KEY")
    workspace_name = os.getenv("ROBOFLOW_WORKFLOW_WORKSPACE")
    workflow_id = os.getenv("ROBOFLOW_WORKFLOW_ID")

    if not url or not api_key or not workspace_name or not workflow_id:
        raise RoboflowInferenceError("Missing Roboflow workflow configuration")


    try:
        api_url = f"{url.rstrip('/')}/infer/workflows/{workspace_name}/{workflow_id}"
        
        payload = {
            "api_key": api_key,
            "inputs": {
                "image": {
                    "type": "url",
                    "value": image_url
                }
            }
        }
        
        # Increased timeout to 120 seconds for cold starts
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(api_url, json=payload)
            
            # Read response
            try:
                data = response.json()
                print(data)
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

    return _summarize_inference_response(data)
