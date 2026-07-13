# Backend Implementation Details: Escalation Feature

This document summarizes the changes made to the backend to support the new Alert Escalation feature. It is intended for the backend team to review the architectural and codebase updates.

## 1. Database Schema Changes
A database migration was run (`migrate.py`) to add the following columns to the `alerts` table in PostgreSQL:
- `escalated_to` (VARCHAR(20)): Stores the escalation target (`rpf`, `maintenance`).
- `escalated_at` (TIMESTAMPTZ): Records the exact time of escalation.
- `escalated_by` (INTEGER): Stores the ID of the user who escalated the alert.

## 2. SQLAlchemy Model (`app/models/alert.py`)
The `Alert` model was updated to include the new columns to ensure the ORM is synchronized with the database schema:
```python
    escalated_to = Column(String(20), nullable=True)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    escalated_by = Column(Integer, nullable=True)
```

## 3. Pydantic Schema (`app/schemas/alert.py`)
The response schema `AlertOut` was updated so the frontend receives the escalation metadata in the JSON response:
```python
    escalatedTo: Optional[str] = None
    escalatedAt: Optional[str] = None
    escalatedBy: Optional[int] = None
```

## 4. Router Updates (`app/routers/alert_router.py`)

### `GET /alerts` (List & Filter)
- The query parameter validation pattern for `escalated_to` was updated to explicitly allow the options.
- **Pattern:** `^(all|rpf|maintenance|none)$`
- The `row_to_alert_out` serialization function was updated to map the database columns to the new camelCase Pydantic fields (`escalatedTo`, `escalatedAt`, `escalatedBy`).

### `POST /alerts/{alert_id}/escalate` (Escalation Action)
- The payload now accepts `escalated_to` and `escalated_by`.
- The raw SQL query was updated to cleanly stamp the escalation metadata. 
- **Logic:**
  ```sql
  UPDATE alerts 
  SET severity = 'critical', notes = %s, escalated_to = %s, escalated_at = NOW(), escalated_by = %s 
  WHERE id = %s RETURNING id;
  ```
- The backend checks if the columns exist using `_alerts_support_escalation_target` before attempting to insert, preserving backward compatibility if the database hasn't been migrated yet.
- The updated alert is automatically broadcast over WebSockets to instantly notify the frontend.

## 5. Main API Documentation (`railoptic_api_and_schema.md`)
The core API documentation file was updated to reflect these changes so the frontend and backend contracts remain in sync.
