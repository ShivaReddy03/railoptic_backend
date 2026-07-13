# Escalation API & Schema Updates

This document outlines the recent changes made to the backend to support Alert Escalation routing (e.g., to RPF or Maintenance teams). These changes are fully backward-compatible.

## 1. Database Schema Additions

The `alerts` table has been extended with the following columns to track escalation state:

- `escalated_to` (VARCHAR): The target team or group the alert was escalated to (e.g., `"rpf"`, `"maintenance"`).
- `escalated_at` (TIMESTAMPTZ): The exact timestamp when the escalation occurred.
- `escalated_by` (INTEGER): The ID of the user who triggered the escalation.

## 2. API Response: The Alert Object

Any endpoint returning an Alert or list of Alerts (such as `GET /alerts` or `GET /alerts/{id}`) now includes the new escalation fields.

### Updated JSON Structure
```json
{
  "id": "ALT-2026-0001",
  "date": "2026-06-28",
  "time": "14:32:11",
  "zone": "South Central",
  "line": "North Line",
  "node": "N047",
  "objectCategory": "Rock Detected",
  "title": "Rock Detected on North Line",
  "source": "AI Camera",
  "location": "North Line - Node 47",
  "severity": "critical",
  "status": "active",
  "confidence": 98,
  "riskScore": 92,
  "nearestTrain": "12045",
  "distanceKm": 4.2,
  "etaSec": 360,
  "imageUrl": "https://cdn.example.com/detections/alt-2026-0001.jpg",
  
  // -- NEW FIELDS --
  "escalatedTo": "rpf",
  "escalatedAt": "2026-06-28T14:35:00Z",
  "escalatedBy": 12
}
```
*(Note: These fields will be `null` if the alert has not been escalated).*

## 3. Updated Endpoints

### 3.1 Escalate an Alert
`POST /alerts/{alert_id}/escalate`

Triggers an escalation for a specific alert. This will automatically upgrade the alert's severity to `critical`, append any notes, and record the escalation metadata.

**Request Body (JSON)**
```json
{ 
  "note": "Contacting section controller immediately.",
  "escalated_to": "rpf",
  "escalated_by": 12
}
```

*All fields in the body are optional, but `escalated_to` is required to actually route it to a specific team dashboard.*

**Response (200 OK)**
Returns the updated Alert object (which is also broadcasted over WebSocket to connected clients).

### 3.2 List & Filter Alerts
`GET /alerts`

The existing list endpoint now actively supports the `escalated_to` query parameter for filtering.

**Query Parameters**
- `escalated_to` (string, optional): Pass `"rpf"`, `"maintenance"`, `"none"`, or `"all"`.
  - `"all"` (default): Returns all alerts.
  - `"none"`: Returns alerts that have *not* been escalated.
  - `"rpf"` / `"maintenance"`: Returns alerts routed to that specific team.

**Example Usage:**
- Long polling for the RPF dashboard: `GET /alerts?status=active&escalated_to=rpf`
- Long polling for the Maintenance dashboard: `GET /alerts?status=active&escalated_to=maintenance`

## 4. WebSockets

When an alert is escalated via the `POST /alerts/{alert_id}/escalate` endpoint, an `alert_updated` event is broadcasted over the WebSocket (`/ws/alerts`). The payload will contain the full Alert object including the new `escalatedTo`, `escalatedAt`, and `escalatedBy` fields so the frontend can react in real-time.
