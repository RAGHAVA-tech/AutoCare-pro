import os
import json
from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Text, DateTime, Date, Boolean, text
)
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

# Database connection is configured ONLY via the DATABASE_URL environment
# variable (see .env.example). Never hard-code credentials in source code —
# a real Postgres password used to live here and has since been removed.
# Rotate that credential immediately if it was ever used against a live database.
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    # Allow .env file loading in development
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
        DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    # Fallback to sqlite for quick local testing
    DATABASE_URL = f"sqlite:///./autocare.db"

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class CustomerORM(Base):
    __tablename__ = "customers"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, index=True, nullable=False)
    email = Column(String, nullable=True)
    vehicle_make = Column(String, nullable=True)
    vehicle_model = Column(String, nullable=True)
    vehicle_year = Column(Integer, nullable=True)
    service_history = Column(Text, default="[]")  # JSON array string
    total_spent = Column(Float, default=0.0)
    preferred_advisor = Column(String, nullable=True)
    loyalty_points = Column(Integer, default=0)
    next_service_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReminderORM(Base):
    __tablename__ = "reminders"
    id = Column(String, primary_key=True, index=True)
    customer_id = Column(String, nullable=False, index=True)
    reminder_date = Column(Date, nullable=False)
    medium = Column(String, nullable=False, default="sms")
    message = Column(Text, nullable=True)
    sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class AppointmentORM(Base):
    __tablename__ = "appointments"
    id = Column(String, primary_key=True, index=True)
    customer_id = Column(String, nullable=False, index=True)
    service_type = Column(String, nullable=False)
    scheduled_date = Column(String, nullable=False)
    scheduled_time = Column(String, nullable=False)
    status = Column(String, nullable=False)
    advisor = Column(String, nullable=True)
    estimated_cost = Column(Float, default=0.0)
    estimated_duration = Column(Integer, default=0)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    # create any missing tables
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        # If running against Postgres and the DB user lacks CREATE privileges on schema 'public',
        # attempting to create tables will raise an error (psycopg2.errors.InsufficientPrivilege).
        # Make init_db best-effort in development: warn and return so the app can continue.
        print("Warning: failed to create tables during init_db():", e)
        print("If using Postgres, grant CREATE/USAGE on schema 'public' or run migrations as a superuser.")
        return

    # For existing SQLite databases, SQLAlchemy won't add columns to existing tables.
    # Apply a lightweight migration: add `next_service_date` column to `customers` if missing.
    try:
        with engine.connect() as conn:
            dialect = engine.dialect.name
            if dialect == "sqlite":
                # SQLite: read table info and add column if missing
                # NOTE: SQLAlchemy 2.0 requires raw strings to be wrapped in text()
                res = conn.execute(text("PRAGMA table_info('customers')"))
                cols = [r[1] for r in res.fetchall()]
                if 'next_service_date' not in cols:
                    try:
                        conn.execute(text("ALTER TABLE customers ADD COLUMN next_service_date DATE"))
                        conn.commit()
                    except Exception:
                        pass
            elif dialect in ("postgresql", "postgres"):
                # PostgreSQL: use IF NOT EXISTS to add column and ensure reminders table exists
                try:
                    conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS next_service_date DATE;"))
                except Exception:
                    pass
                try:
                    conn.execute(text(
                        """
                        CREATE TABLE IF NOT EXISTS reminders (
                            id VARCHAR PRIMARY KEY,
                            customer_id VARCHAR NOT NULL,
                            reminder_date DATE NOT NULL,
                            medium VARCHAR NOT NULL DEFAULT 'sms',
                            message TEXT,
                            sent BOOLEAN DEFAULT FALSE,
                            created_at TIMESTAMP DEFAULT now()
                        )
                        """
                    ))
                except Exception:
                    pass
    except Exception:
        # ignore migration errors — init_db is best-effort for local dev
        pass


# small helpers for external modules
def get_session():
    return SessionLocal()


def load_all_customers():
    """Return every persisted customer row as plain dicts (best-effort)."""
    try:
        s = get_session()
        try:
            rows = s.query(CustomerORM).all()
            return [
                {
                    "id": r.id, "name": r.name, "phone": r.phone, "email": r.email,
                    "vehicle_make": r.vehicle_make, "vehicle_model": r.vehicle_model,
                    "vehicle_year": r.vehicle_year,
                    "service_history": deserialize_history(r.service_history),
                    "total_spent": r.total_spent or 0.0,
                    "preferred_advisor": r.preferred_advisor,
                    "loyalty_points": r.loyalty_points or 0,
                } for r in rows
            ]
        finally:
            s.close()
    except Exception as e:
        print("Warning: could not load customers from DB:", e)
        return []


def load_all_appointments():
    """Return every persisted appointment row as plain dicts (best-effort)."""
    try:
        s = get_session()
        try:
            rows = s.query(AppointmentORM).all()
            return [
                {
                    "id": r.id, "customer_id": r.customer_id, "service_type": r.service_type,
                    "scheduled_date": r.scheduled_date, "scheduled_time": r.scheduled_time,
                    "status": r.status, "advisor": r.advisor,
                    "estimated_cost": r.estimated_cost or 0.0,
                    "estimated_duration": r.estimated_duration or 0,
                    "notes": r.notes or "",
                } for r in rows
            ]
        finally:
            s.close()
    except Exception as e:
        print("Warning: could not load appointments from DB:", e)
        return []


def update_appointment_status(appointment_id: str, status: str, scheduled_date: str = None,
                               scheduled_time: str = None) -> bool:
    """Best-effort update of an appointment's status/date/time (cancel or reschedule)."""
    try:
        s = get_session()
        try:
            row = s.query(AppointmentORM).filter_by(id=appointment_id).first()
            if not row:
                return False
            row.status = status
            if scheduled_date:
                row.scheduled_date = scheduled_date
            if scheduled_time:
                row.scheduled_time = scheduled_time
            s.commit()
            return True
        finally:
            s.close()
    except Exception as e:
        print("Warning: could not update appointment in DB:", e)
        return False

def serialize_history(history_list):
    try:
        return json.dumps(history_list)
    except Exception:
        return json.dumps([])

def deserialize_history(history_text):
    try:
        return json.loads(history_text or "[]")
    except Exception:
        return []
