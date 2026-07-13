import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USERNAME = os.getenv("DB_USERNAME")
DB_PASSWORD = os.getenv("DB_PASSWORD")

DATABASE_URL = f"postgresql+psycopg://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

def migrate():
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS escalated_to VARCHAR(20);"))
        conn.execute(text("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS escalated_at TIMESTAMPTZ;"))
        conn.execute(text("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS escalated_by INTEGER;"))
    print("Migration complete. Added escalated_to, escalated_at, and escalated_by to alerts table.")

if __name__ == "__main__":
    migrate()
