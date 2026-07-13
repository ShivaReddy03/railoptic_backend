import math
import re

_LEVEL_BASE: dict[str, float] = {
    "high":   1.00,
    "medium": 0.70,
    "low":    0.40,
    "clear":  0.00,
    "none":   0.00,
}

_CLASS_WEIGHTS: dict[str, float] = {
    "human":            1.35,
    "person":           1.35,
    "person on railway":1.40,
    "worker":           1.30,
    "animal":           1.05,
    "sheep":            1.05,
    "elephant":         1.10,
    "vehicle":          1.15,
    "car":              1.15,
    "truck":            1.20,
    "train":            0.00,
}


def _distance_weight(dist_m: float) -> float:
    return 1.0


def _confidence_weight(confidence: float | None) -> float:
    confidence = max(0.0, min(1.0, float(confidence or 0.0)))
    return 0.5 + (0.5 * confidence)


def _size_weight(object_area_px: float | None, max_area_px: float | None, dist_m: float) -> float:
    if object_area_px is None or object_area_px <= 0:
        return 1.0
    if max_area_px is None or max_area_px <= 0:
        return 1.0
    ratio = max(0.0, min(1.0, object_area_px / max_area_px))
    # Same pixel ratio at 8m = physically ~4x larger than at 2m
    # dist_amp: 1m→0.5, 2m→1.0, 4m→2.0, 8m→4.0 — capped at 4.0
    dist_amp = max(0.5, min(4.0, dist_m / 2.0))
    physical_ratio = min(1.0, ratio * dist_amp / 4.0)
    return 0.85 + (0.15 * physical_ratio)


def _count_weight(hazard_count: int | None) -> float:
    count = max(0, int(hazard_count or 0))
    if count <= 1:
        return 1.0
    if count == 2:
        return 1.10
    if count == 3:
        return 1.20
    return min(1.45, 1.20 + (0.05 * (count - 3)))


def _proximity_boost(dist_m: float) -> float:
    """Object >5 m away is still on track and approaching → small urgency bump."""
    return 1.10 if dist_m > 5.0 else 1.0


def compute_risk_score(
    risk_level: str,
    lidar_dist_m: float,
    *,
    confidence: float | None = None,
    hazard_count: int | None = None,
    class_name: str | None = None,
    object_area_px: float | None = None,
    max_area_px: float | None = None,
) -> int:
    level = (risk_level or "none").strip().lower()
    base = _LEVEL_BASE.get(level, 0.0)

    if base <= 0.0:
        return 0

    distance_weight  = _distance_weight(lidar_dist_m)
    confidence_weight = _confidence_weight(confidence)
    size_weight      = _size_weight(object_area_px, max_area_px, lidar_dist_m)
    count_weight     = _count_weight(hazard_count)
    proximity_boost  = _proximity_boost(lidar_dist_m)

    class_key    = (class_name or "").strip().lower()
    class_weight = _CLASS_WEIGHTS.get(class_key, 1.0)

    combined = (
        base
        * distance_weight
        * confidence_weight
        * size_weight
        * count_weight
        * class_weight
        * proximity_boost
    )

    return max(0, min(100, round(combined * 100)))


def severity_from_score(risk_score: int, class_name: str | None = None) -> str:
    if class_name and re.search(r'(rock|elephant|tree)', class_name, re.IGNORECASE):
        return "critical"
    
    return "warning"