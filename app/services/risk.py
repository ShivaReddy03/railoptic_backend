def compute_risk_score(risk_level: str, lidar_dist_m: float) -> int:
    level = (risk_level or "none").strip().lower()
    if level == "high":
        base_score = 80
    elif level == "medium":
        base_score = 50
    elif level == "low":
        base_score = 20
    else:
        base_score = 0

    if lidar_dist_m < 10:
        multiplier = 1.0
    elif lidar_dist_m < 30:
        multiplier = 0.75
    elif lidar_dist_m < 100:
        multiplier = 0.5
    else:
        multiplier = 0.2

    return min(100, round(base_score * multiplier))


def severity_from_score(risk_score: int) -> str:
    if risk_score >= 75:
        return "critical"
    if risk_score >= 40:
        return "warning"
    return "info"
