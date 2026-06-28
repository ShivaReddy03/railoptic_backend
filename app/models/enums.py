import enum


class NodeStatusEnum(str, enum.Enum):
    normal = "normal"
    warning = "warning"
    critical = "critical"
    offline = "offline"


class TrainStatusEnum(str, enum.Enum):
    safe = "safe"
    monitor = "monitor"
    at_risk = "at_risk"
    delayed = "delayed"
    on_time = "on_time"


class SeverityEnum(str, enum.Enum):
    critical = "critical"
    warning = "warning"
    info = "info"


class AlertStatusEnum(str, enum.Enum):
    active = "active"
    acknowledged = "acknowledged"
    resolved = "resolved"
