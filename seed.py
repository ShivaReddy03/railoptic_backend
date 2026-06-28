import os
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USERNAME = os.getenv("DB_USERNAME")
DB_PASSWORD = os.getenv("DB_PASSWORD")

DATABASE_URL = (
    f"postgresql+psycopg://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(DATABASE_URL, future=True)


def create_tables():
    from app.models.base import Base
    from app.models.zone import Zone
    from app.models.line import Line
    from app.models.node import Node
    from app.models.train import Train
    from app.models.alert import Alert
    from app.models.alert_affected_train import AlertAffectedTrain

    Base.metadata.create_all(engine)


def seed_data():
    zone_names = ["North Zone", "South Zone", "East Zone", "West Zone"]
    line_defs = [
        {"name": "North Line", "zone": "North Zone"},
        {"name": "South Line", "zone": "South Zone"},
        {"name": "East Line", "zone": "East Zone"},
        {"name": "West Line", "zone": "West Zone"},
    ]

    node_categories = ["Rock Detected", "Track Obstruction", "Trespasser", "Signal Fault", "Debris"]
    alert_titles = {
        "Rock Detected": "Rock Detected on {line}",
        "Track Obstruction": "Track Obstruction on {line}",
        "Trespasser": "Unauthorized Person on {line}",
        "Signal Fault": "Signal Fault on {line}",
        "Debris": "Debris Detected on {line}",
    }
    train_statuses = ["safe", "monitor", "at_risk", "delayed", "on_time"]
    node_statuses = ["normal", "warning", "critical", "offline"]
    alert_statuses = ["active", "acknowledged", "resolved"]
    severities = ["critical", "warning", "info"]

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE alert_affected_trains, alerts, trains, nodes, lines, zones RESTART IDENTITY CASCADE;"))

        zone_map = {}
        for zone_name in zone_names:
            result = conn.execute(text("INSERT INTO zones (name) VALUES (:name) RETURNING id"), {"name": zone_name})
            zone_map[zone_name] = result.scalar_one()

        line_map = {}
        for line_def in line_defs:
            result = conn.execute(
                text("INSERT INTO lines (zone_id, name) VALUES (:zone_id, :name) RETURNING id"),
                {"zone_id": zone_map[line_def["zone"]], "name": line_def["name"]},
            )
            line_map[line_def["name"]] = result.scalar_one()

        nodes = []
        for line_name, line_id in line_map.items():
            base_lat = 17.0 + random.random() * 0.5
            base_lng = 78.0 + random.random() * 0.5
            for node_index in range(1, 11):
                node_id = f"N{len(nodes) + 1:03d}"
                status = random.choices(node_statuses, weights=[60, 20, 10, 10], k=1)[0]
                health = max(0, min(100, 100 - random.randint(0, 30) if status != "normal" else 100 - random.randint(0, 5)))
                lat = base_lat + (node_index * 0.0015)
                lng = base_lng + (node_index * 0.0012)
                last_seen = datetime.utcnow() - timedelta(minutes=random.randint(1, 90))
                conn.execute(
                    text(
                        "INSERT INTO nodes (id, line_id, lat, lng, status, health, last_seen) "
                        "VALUES (:id, :line_id, :lat, :lng, :status, :health, :last_seen)"
                    ),
                    {
                        "id": node_id,
                        "line_id": line_id,
                        "lat": lat,
                        "lng": lng,
                        "status": status,
                        "health": health,
                        "last_seen": last_seen,
                    },
                )
                nodes.append({"id": node_id, "line": line_name})

        train_ids = []
        for idx in range(1, 11):
            number = f"120{idx:02d}"
            status = random.choice(train_statuses)
            line_name = random.choice(list(line_map.keys()))
            line_id = line_map[line_name]
            result = conn.execute(
                text(
                    "INSERT INTO trains (number, line_id, status, updated_at) VALUES (:number, :line_id, :status, :updated_at) RETURNING id"
                ),
                {"number": number, "line_id": line_id, "status": status, "updated_at": datetime.utcnow() - timedelta(minutes=random.randint(0, 30))},
            )
            train_ids.append(result.scalar_one())

        alert_ids = []
        for alert_index in range(1, 21):
            node = random.choice(nodes)
            line_name = node["line"]
            category = random.choice(node_categories)
            title = alert_titles[category].format(line=line_name)
            severity = random.choices(severities, weights=[20, 40, 40], k=1)[0]
            status = random.choices(alert_statuses, weights=[60, 25, 15], k=1)[0]
            nearest_train_id = random.choice(train_ids) if random.random() > 0.2 else None
            distance_km = round(random.uniform(0.5, 8.0), 1) if nearest_train_id else None
            eta_sec = random.randint(60, 600) if nearest_train_id else None
            detected_at = datetime.utcnow() - timedelta(hours=random.randint(0, 48), minutes=random.randint(0, 59))
            acknowledged_at = None
            resolved_at = None
            if status == "acknowledged":
                acknowledged_at = detected_at + timedelta(minutes=15)
            elif status == "resolved":
                acknowledged_at = detected_at + timedelta(minutes=10)
                resolved_at = detected_at + timedelta(minutes=30)

            alert_id = f"ALT-2026-{alert_index:04d}"
            alert_ids.append(alert_id)
            conn.execute(
                text(
                    "INSERT INTO alerts (id, node_id, object_category, title, source, severity, status, confidence, risk_score, nearest_train_id, distance_km, eta_sec, image_url, detected_at, acknowledged_at, resolved_at, notes) "
                    "VALUES (:id, :node_id, :object_category, :title, :source, :severity, :status, :confidence, :risk_score, :nearest_train_id, :distance_km, :eta_sec, :image_url, :detected_at, :acknowledged_at, :resolved_at, :notes)"
                ),
                {
                    "id": alert_id,
                    "node_id": node["id"],
                    "object_category": category,
                    "title": title,
                    "source": "AI Camera",
                    "severity": severity,
                    "status": status,
                    "confidence": random.randint(65, 99),
                    "risk_score": random.randint(40, 98),
                    "nearest_train_id": nearest_train_id,
                    "distance_km": distance_km,
                    "eta_sec": eta_sec,
                    "image_url": f"https://cdn.example.com/detections/{alert_id}.jpg",
                    "detected_at": detected_at,
                    "acknowledged_at": acknowledged_at,
                    "resolved_at": resolved_at,
                    "notes": None,
                },
            )

        for alert_id in random.sample(alert_ids, 10):
            selected_trains = random.sample(train_ids, k=random.randint(1, 3))
            for idx, train_id in enumerate(selected_trains, start=1):
                conn.execute(
                    text(
                        "INSERT INTO alert_affected_trains (alert_id, train_id, distance_from_incident, eta_min, status) "
                        "VALUES (:alert_id, :train_id, :distance_from_incident, :eta_min, :status)"
                    ),
                    {
                        "alert_id": alert_id,
                        "train_id": train_id,
                        "distance_from_incident": round(0.5 + idx * random.uniform(0.8, 2.2), 2),
                        "eta_min": random.randint(5, 25),
                        "status": random.choice(["at_risk", "monitor", "delayed", "safe"]),
                    },
                )

    print("Seed data loaded successfully.")


if __name__ == "__main__":
    create_tables()
    seed_data()
