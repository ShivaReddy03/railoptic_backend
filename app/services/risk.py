import math

# Roboflow risk_level → normalized base (0.0–1.0)
_LEVEL_BASE: dict[str, float] = {
    "high":   1.00,
    "medium": 0.65,
    "low":    0.35,
    "none":   0.00,
}

# Tuned for TF-Luna range (0.2m – 8m)
# exp(-0.2 * 8) ≈ 0.20  →  still contributes at max range
_DECAY_K = 0.20


def _distance_weight(dist_m: float) -> float:
    """Smooth exponential decay. Closer = higher weight, never fully zero."""
    dist_m = max(0.0, dist_m)
    return max(0.05, math.exp(-_DECAY_K * dist_m))


def compute_risk_score(risk_level: str, lidar_dist_m: float) -> int:
    level = (risk_level or "none").strip().lower()
    base   = _LEVEL_BASE.get(level, 0.0)
    weight = _distance_weight(lidar_dist_m)
    # Geometric mean: both factors must be high for a high score.
    # Neither alone can dominate — no detection = 0 regardless of distance.
    combined = math.sqrt(base * weight)
    return min(100, round(combined * 100))


def severity_from_score(risk_score: int) -> str:
    if risk_score >= 75:
        return "critical"
    if risk_score >= 40:
        return "warning"
    return "info"