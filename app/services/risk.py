import math

# Roboflow risk_level → normalized base (0.0–1.0)
_LEVEL_BASE: dict[str, float] = {
    "high": 1.00,
    "medium": 0.70,
    "low": 0.40,
    "clear": 0.00,
    "none": 0.00,
}

# Tuned for TF-Luna range (0.2m – 8m)
# exp(-0.2 * 8) ≈ 0.20 → still contributes at max range
_DECAY_K = 0.20

# Importance multipliers for object classes.
_CLASS_WEIGHTS: dict[str, float] = {
    "human": 1.35,
    "person": 1.35,
    "person on railway": 1.40,
    "worker": 1.30,
    "animal": 1.05,
    "sheep": 1.05,
    "elephant": 1.10,
    "vehicle": 1.15,
    "car": 1.15,
    "truck": 1.20,
    "train": 1.30,
}


def _distance_weight(dist_m: float) -> float:
    """Smooth exponential decay. Closer = higher weight, never fully zero."""
    dist_m = max(0.0, dist_m)
    return max(0.05, math.exp(-_DECAY_K * dist_m))


def _confidence_weight(confidence: float | None) -> float:
    confidence = max(0.0, min(1.0, float(confidence or 0.0)))
    return 0.5 + (0.5 * confidence)


def _size_weight(object_area_px: float | None, max_area_px: float | None) -> float:
    if object_area_px is None or object_area_px <= 0:
        return 1.0
    if max_area_px is None or max_area_px <= 0:
        return 1.0
    ratio = max(0.0, min(1.0, object_area_px / max_area_px))
    return 0.85 + (0.15 * ratio)


def _count_weight(hazard_count: int | None) -> float:
    count = max(0, int(hazard_count or 0))
    if count <= 1:
        return 1.0
    if count == 2:
        return 1.10
    if count == 3:
        return 1.20
    return min(1.45, 1.20 + (0.05 * (count - 3)))


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

    distance_weight = _distance_weight(lidar_dist_m)
    confidence_weight = _confidence_weight(confidence)
    size_weight = _size_weight(object_area_px, max_area_px)
    count_weight = _count_weight(hazard_count)

    class_key = (class_name or "").strip().lower()
    class_weight = _CLASS_WEIGHTS.get(class_key, 1.0)

    # Blend several signals so that high-confidence, important classes,
    # large objects, and multiple detections all raise urgency.
    combined = base * distance_weight * confidence_weight * size_weight * count_weight * class_weight
    score = min(100, round(combined * 100))
    return max(0, score)


def severity_from_score(risk_score: int) -> str:
    if risk_score >= 75:
        return "critical"
    if risk_score >= 40:
        return "warning"
    return "info"