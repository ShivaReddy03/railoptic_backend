# RailOptic — API Documentation & Database Schema

---

## 1. Database Schema (PostgreSQL)

### 1.1 `zones`
Railway zones / administrative regions.

```sql
CREATE TABLE zones (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,   -- e.g. "South Central"
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

### 1.2 `lines`
Track lines within a zone.

```sql
CREATE TABLE lines (
    id         SERIAL PRIMARY KEY,
    zone_id    INTEGER NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    name       VARCHAR(100) NOT NULL,            -- e.g. "North Line"
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (zone_id, name)
);
```

---

### 1.3 `nodes`
Detection nodes (ESP32-CAM + TF-Luna units) deployed along a line.

```sql
CREATE TYPE node_status_enum AS ENUM ('normal', 'warning', 'critical', 'offline');

CREATE TABLE nodes (
    id          VARCHAR(10) PRIMARY KEY,         -- e.g. "N047"
    line_id     INTEGER NOT NULL REFERENCES lines(id) ON DELETE CASCADE,
    lat         DOUBLE PRECISION NOT NULL,
    lng         DOUBLE PRECISION NOT NULL,
    status      node_status_enum NOT NULL DEFAULT 'normal',
    health      SMALLINT NOT NULL DEFAULT 100     -- 0–100
                    CHECK (health BETWEEN 0 AND 100),
    last_seen   TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_nodes_line_id ON nodes(line_id);
CREATE INDEX idx_nodes_status  ON nodes(status);
```

---

### 1.4 `trains`
Active trains on the network (refreshed by telemetry ingestion).

```sql
CREATE TYPE train_status_enum AS ENUM ('safe', 'monitor', 'at_risk', 'delayed', 'on_time');

CREATE TABLE trains (
    id         SERIAL PRIMARY KEY,
    number     VARCHAR(20) NOT NULL UNIQUE,      -- e.g. "12045"
    line_id    INTEGER REFERENCES lines(id) ON DELETE SET NULL,
    status     train_status_enum NOT NULL DEFAULT 'on_time',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trains_number ON trains(number);
```

---

### 1.5 `alerts`
Core table — one row per detection event.

```sql
CREATE TYPE severity_enum     AS ENUM ('critical', 'warning', 'info');
CREATE TYPE alert_status_enum AS ENUM ('active', 'acknowledged', 'resolved');

CREATE TABLE alerts (
    id               VARCHAR(20) PRIMARY KEY,      -- e.g. "ALT-2026-0001"
    node_id          VARCHAR(10) NOT NULL REFERENCES nodes(id),
    object_category  VARCHAR(100) NOT NULL,         -- e.g. "Rock Detected"
    title            VARCHAR(200) NOT NULL,
    source           VARCHAR(50)  NOT NULL DEFAULT 'AI Camera',
    severity         severity_enum     NOT NULL,
    status           alert_status_enum NOT NULL DEFAULT 'active',
    confidence       SMALLINT NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    risk_score       SMALLINT NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    nearest_train_id INTEGER REFERENCES trains(id) ON DELETE SET NULL,
    distance_km      NUMERIC(6,2),
    eta_sec          INTEGER,
    image_url        TEXT,
    detected_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at  TIMESTAMPTZ,
    resolved_at      TIMESTAMPTZ,
    acknowledged_by  INTEGER,                       -- FK to users when auth is added
    notes            TEXT
);

CREATE INDEX idx_alerts_status     ON alerts(status);
CREATE INDEX idx_alerts_severity   ON alerts(severity);
CREATE INDEX idx_alerts_node_id    ON alerts(node_id);
CREATE INDEX idx_alerts_detected   ON alerts(detected_at DESC);
```

---

### 1.6 `alert_affected_trains`
Trains near a critical alert (up to 5 per alert).

```sql
CREATE TABLE alert_affected_trains (
    alert_id               VARCHAR(20) NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    train_id               INTEGER     NOT NULL REFERENCES trains(id) ON DELETE CASCADE,
    distance_from_incident NUMERIC(6,2) NOT NULL,
    eta_min                INTEGER      NOT NULL,
    status                 train_status_enum NOT NULL,
    PRIMARY KEY (alert_id, train_id)
);
```

---

### 1.7 Sequence for alert IDs
```sql
CREATE SEQUENCE alert_seq START 1;

-- Usage in application layer:
-- f"ALT-{year}-{nextval('alert_seq'):04d}"
```

---

## 2. API Documentation

### Conventions

| Item | Value |
|------|-------|
| Base URL | `VITE_API_BASE_URL` (e.g. `https://api.railoptic.example/v1`) |
| Auth | `Authorization: Bearer <token>` (skip for now) |
| Timestamps | ISO-8601 UTC — `2026-06-28T14:32:11Z` |
| Errors | HTTP status + `{ "detail": "message" }` |
| Pagination | `{ "data": [], "total": 0, "page": 1, "pageSize": 10 }` |

---

### 2.1 Dashboard

#### `GET /dashboard/overview`
Polled every 15 s by `useDashboard()`.

**Response**
```json
{
  "activeAlerts":  47,
  "criticalCount": 8,
  "warningCount":  23,
  "totalNodes":    500,
  "onlineNodes":   478,
  "activeTrains":  312,
  "systemHealth":  98,
  "critical": {
    "id":             "ALT-2026-0001",
    "objectCategory": "Rock Detected",
    "line":           "North Line",
    "node":           "N047",
    "date":           "2026-06-28",
    "time":           "14:32:11",
    "severity":       "critical",
    "status":         "active",
    "confidence":     98,
    "riskScore":      92,
    "nearestTrain":   "12045",
    "distanceKm":     4.2,
    "etaSec":         360,
    "imageUrl":       "https://cdn.example.com/detections/alt-2026-0001.jpg"
  },
  "affectedTrains": [
    {
      "id":                      "T-1",
      "number":                  "12045",
      "distanceFromIncidentKm":  4.2,
      "etaMin":                  12,
      "status":                  "at_risk"
    }
  ]
}
```

**Notes**
- `critical` is `null` when no active alert exists.
- `affectedTrains`: ≤ 5 trains, sorted ascending by `distanceFromIncidentKm`.
- `systemHealth` = `(onlineNodes / totalNodes) * 100`, rounded integer.

**Query (SQLAlchemy outline)**
```python
# systemHealth
health = round((online_count / total_count) * 100)

# critical alert
alert = (
    db.query(Alert)
    .filter(Alert.status == "active", Alert.severity == "critical")
    .order_by(Alert.detected_at.desc())
    .first()
)

# affected trains
trains = (
    db.query(AlertAffectedTrain)
    .filter(AlertAffectedTrain.alert_id == alert.id)
    .order_by(AlertAffectedTrain.distance_from_incident.asc())
    .limit(5)
    .all()
)
```

---

#### `GET /nodes`
Used by `useNodes()` for Track Monitoring Overview. Returns a plain array (no pagination).

**Response**
```json
[
  {
    "id":             "N001",
    "line":           "North Line",
    "gps":            { "lat": 17.385, "lng": 78.486 },
    "status":         "warning",
    "health":         85,
    "currentAlertId": "ALT-2026-0001"
  }
]
```

**Notes**
- `currentAlertId` is included only when the node `status` is `warning` or `critical` and contains the latest active alert ID for that node. For `normal` or `offline` nodes the value will be `null`.
- The frontend can use `currentAlertId` to call `GET /alerts/{id}` and load detailed alert information.
- Region-scoped: if caller role is `section_controller` or `maintenance`, filter by their assigned zone.
- No query params required from the frontend.

---

### 2.2 Alerts

#### `GET /alerts/summary`
Drives four stat cards in the Alerts screen. Called by `useAlertsSummary()`.

**Response**
```json
{ "active": 47, "critical": 8, "warning": 23, "info": 16, "total": 1000 }
```

- `active/critical/warning/info` count only alerts where `status = 'active'`.
- `total` is the all-time row count in the `alerts` table.

---

#### `GET /alerts`
Paginated table, called by `useAlerts(params)`.

**Query Parameters**

| Name     | Type   | Default | Notes |
|----------|--------|---------|-------|
| page     | int    | 1       | 1-indexed |
| pageSize | int    | 10      | |
| search   | string | —       | Matches `id`, `objectCategory`, or `node_id` |
| severity | string | `all`   | `all \| critical \| warning \| info` |
| status   | string | `all`   | `all \| active \| acknowledged \| resolved` |
| zone     | string | —       | Optional zone name filter |
| line     | string | —       | Optional line name filter |

**Response**
```json
{
  "data": [
    {
      "id":             "ALT-2026-0001",
      "date":           "2026-06-28",
      "time":           "14:32:11",
      "zone":           "South Central",
      "line":           "North Line",
      "node":           "N047",
      "objectCategory": "Rock Detected",
      "title":          "Rock Detected on North Line",
      "source":         "AI Camera",
      "location":       "North Line - Node 47",
      "severity":       "critical",
      "status":         "active",
      "confidence":     98,
      "riskScore":      92,
      "nearestTrain":   "12045",
      "distanceKm":     4.2,
      "etaSec":         360,
      "imageUrl":       "https://cdn.example.com/detections/alt-2026-0001.jpg"
    }
  ],
  "total": 1000,
  "page": 1,
  "pageSize": 10
}
```

**Filter logic (pseudo-SQL)**
```sql
WHERE
  (search IS NULL OR id ILIKE '%search%' OR object_category ILIKE '%search%' OR node_id ILIKE '%search%')
  AND (severity_param = 'all' OR severity = severity_param)
  AND (status_param  = 'all' OR status  = status_param)
  AND (zone   IS NULL OR zones.name = zone)
  AND (line   IS NULL OR lines.name = line)
ORDER BY detected_at DESC
LIMIT pageSize OFFSET (page - 1) * pageSize
```

---

#### `GET /alerts/{id}`
Single alert detail, called by `useAlert(id)`. Returns one Alert object (same shape as a row in the list above).

**Errors**
- `404` if alert not found.

---

#### `POST /alerts/{id}/acknowledge`
No request body needed. Sets `status = 'acknowledged'` and stamps `acknowledged_at`.

**Response** — updated Alert object.

---

#### `POST /alerts/{id}/escalate`
**Request body**
```json
{ "note": "Contacting section controller immediately." }
```

Sets `severity` to `critical` (if not already), appends `note` to `notes`, optionally triggers WebSocket broadcast.

**Response** — updated Alert object.

---

#### `GET /alerts/{id}/export`
**Query param**: `format=pdf` or `format=csv`

**Response**: file stream with `Content-Disposition: attachment; filename="ALT-2026-0001.pdf"`.

---

### 2.3 WebSocket — Live Alert Feed

#### `WS /ws/alerts`
Pushes events to the dashboard in real time.

**Message shape (server → client)**
```json
{
  "event":   "new_alert" | "alert_updated" | "node_status_changed",
  "payload": { /* Alert or Node object */ }
}
```

Connect on dashboard mount; reconnect with exponential back-off on disconnect.

---

## 3. Enums Reference

| Field | Allowed values |
|-------|----------------|
| `severity` | `critical` \| `warning` \| `info` |
| `alert.status` | `active` \| `acknowledged` \| `resolved` |
| `train.status` | `safe` \| `monitor` \| `at_risk` \| `delayed` \| `on_time` |
| `node.status` | `normal` \| `warning` \| `critical` \| `offline` |
| `confidence`, `riskScore`, `health` | integer 0–100 |

---

## 4. FastAPI Router Structure

```
app/
├── main.py
├── database.py          # SQLAlchemy engine + session
├── models/
│   ├── alert.py
│   ├── node.py
│   └── train.py
├── schemas/             # Pydantic response models
│   ├── alert.py
│   ├── node.py
│   └── dashboard.py
└── routers/
    ├── dashboard.py     # GET /dashboard/overview, GET /nodes
    ├── alerts.py        # GET/POST /alerts/*
    └── ws.py            # WS /ws/alerts
```

### Example Pydantic schemas

```python
# schemas/alert.py
from pydantic import BaseModel
from typing import Optional
from datetime import date, time

class AlertOut(BaseModel):
    id: str
    date: date
    time: time
    zone: str
    line: str
    node: str
    objectCategory: str
    title: str
    source: str
    location: str
    severity: str
    status: str
    confidence: int
    riskScore: int
    nearestTrain: Optional[str]
    distanceKm: Optional[float]
    etaSec: Optional[int]
    imageUrl: Optional[str]

    class Config:
        from_attributes = True

class AlertListResponse(BaseModel):
    data: list[AlertOut]
    total: int
    page: int
    pageSize: int
```

---

## 5. CSV Simulation Mapping (MVP)

For the CSV-based MVP (no physical hardware), ingest scripts write to these tables directly:

| CSV field | Maps to |
|-----------|---------|
| `node_id` | `alerts.node_id` |
| `timestamp` | `alerts.detected_at` |
| `object_class` | `alerts.object_category` |
| `confidence` | `alerts.confidence` |
| `risk_score` | `alerts.risk_score` |
| `nearest_train` | resolved to `trains.number` → `alerts.nearest_train_id` |
| `distance_km` | `alerts.distance_km` |
| `eta_sec` | `alerts.eta_sec` |

Alert ID generated as: `ALT-{YYYY}-{nextval:04d}`
