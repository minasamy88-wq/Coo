"""SQLite database: schema creation, connection management, and CRUD operations."""

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from typing import Optional

from .config import DB_PATH
from .models import (
    AnomalyModel,
    AnomalyWithContext,
    BillModel,
    BillWithContext,
    MeterModel,
    PropertyModel,
    ProviderTemplateModel,
    UnitModel,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT,
    city TEXT,
    province TEXT DEFAULT 'ON',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    unit_number TEXT NOT NULL,
    is_common_area BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(property_id, unit_number)
);

CREATE TABLE IF NOT EXISTS meters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    unit_id INTEGER REFERENCES units(id),
    account_number TEXT,
    meter_number TEXT,
    utility_type TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    is_bulk BOOLEAN DEFAULT FALSE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meter_id INTEGER NOT NULL REFERENCES meters(id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    usage_amount REAL,
    usage_unit TEXT,
    cost REAL,
    taxes REAL,
    total_amount REAL NOT NULL,
    source_file TEXT,
    confirmed BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(meter_id, period_start, period_end)
);

CREATE TABLE IF NOT EXISTS provider_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_name TEXT NOT NULL,
    utility_type TEXT NOT NULL,
    file_type TEXT DEFAULT 'pdf',
    field_patterns TEXT,
    column_mapping TEXT,
    sample_text TEXT,
    confirmed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider_name, utility_type, file_type)
);

CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id INTEGER NOT NULL REFERENCES bills(id),
    anomaly_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    value REAL,
    threshold REAL,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db():
    """Create all tables if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)


@contextmanager
def get_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --- Properties ---


def create_property(prop: PropertyModel) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO properties (name, address, city, province, notes) VALUES (?, ?, ?, ?, ?)",
            (prop.name, prop.address, prop.city, prop.province, prop.notes),
        )
        return cursor.lastrowid


def get_property(property_id: int) -> Optional[PropertyModel]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM properties WHERE id = ?", (property_id,)).fetchone()
        if row:
            return PropertyModel(**dict(row))
        return None


def get_property_by_name(name: str) -> Optional[PropertyModel]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM properties WHERE name = ?", (name,)).fetchone()
        if row:
            return PropertyModel(**dict(row))
        return None


def get_all_properties() -> list[PropertyModel]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM properties ORDER BY city, name").fetchall()
        return [PropertyModel(**dict(row)) for row in rows]


def update_property(prop: PropertyModel) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE properties SET name=?, address=?, city=?, province=?, notes=? WHERE id=?",
            (prop.name, prop.address, prop.city, prop.province, prop.notes, prop.id),
        )


# --- Units ---


def create_unit(unit: UnitModel) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO units (property_id, unit_number, is_common_area, notes) VALUES (?, ?, ?, ?)",
            (unit.property_id, unit.unit_number, unit.is_common_area, unit.notes),
        )
        if cursor.lastrowid:
            return cursor.lastrowid
        # If INSERT OR IGNORE didn't insert (duplicate), fetch existing
        row = conn.execute(
            "SELECT id FROM units WHERE property_id = ? AND unit_number = ?",
            (unit.property_id, unit.unit_number),
        ).fetchone()
        return row["id"]


def get_units_for_property(property_id: int) -> list[UnitModel]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM units WHERE property_id = ? ORDER BY unit_number", (property_id,)
        ).fetchall()
        return [UnitModel(**dict(row)) for row in rows]


# --- Meters ---


def create_meter(meter: MeterModel) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO meters
            (property_id, unit_id, account_number, meter_number, utility_type, provider_name, is_bulk, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                meter.property_id,
                meter.unit_id,
                meter.account_number,
                meter.meter_number,
                meter.utility_type,
                meter.provider_name,
                meter.is_bulk,
                meter.active,
            ),
        )
        return cursor.lastrowid


def get_meters_for_property(property_id: int) -> list[MeterModel]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM meters WHERE property_id = ? AND active = 1 ORDER BY utility_type, unit_id",
            (property_id,),
        ).fetchall()
        return [MeterModel(**dict(row)) for row in rows]


def get_meter_by_account(account_number: str) -> Optional[MeterModel]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM meters WHERE account_number = ? AND active = 1", (account_number,)
        ).fetchone()
        if row:
            return MeterModel(**dict(row))
        return None


def get_all_meters() -> list[MeterModel]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM meters WHERE active = 1 ORDER BY property_id, utility_type").fetchall()
        return [MeterModel(**dict(row)) for row in rows]


def update_meter(meter: MeterModel) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE meters SET unit_id=?, account_number=?, meter_number=?,
            utility_type=?, provider_name=?, is_bulk=?, active=? WHERE id=?""",
            (
                meter.unit_id,
                meter.account_number,
                meter.meter_number,
                meter.utility_type,
                meter.provider_name,
                meter.is_bulk,
                meter.active,
                meter.id,
            ),
        )


# --- Bills ---


def create_bill(bill: BillModel) -> Optional[int]:
    """Insert a bill. Returns None if duplicate (same meter + period)."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """INSERT INTO bills
                (meter_id, period_start, period_end, usage_amount, usage_unit, cost, taxes, total_amount, source_file, confirmed, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    bill.meter_id,
                    bill.period_start.isoformat(),
                    bill.period_end.isoformat(),
                    bill.usage_amount,
                    bill.usage_unit,
                    bill.cost,
                    bill.taxes,
                    bill.total_amount,
                    bill.source_file,
                    bill.confirmed,
                    bill.notes,
                ),
            )
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None  # Duplicate bill


def get_bills_for_meter(meter_id: int, limit: int = 24) -> list[BillModel]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM bills WHERE meter_id = ? ORDER BY period_start DESC LIMIT ?",
            (meter_id, limit),
        ).fetchall()
        return [BillModel(**dict(row)) for row in rows]


def get_bills_for_property(property_id: int, months: int = 12) -> list[BillWithContext]:
    """Get all bills for a property with meter/unit context."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT b.*, p.name as property_name, p.city as property_city,
                      u.unit_number, m.utility_type, m.provider_name,
                      m.account_number, m.meter_number
               FROM bills b
               JOIN meters m ON b.meter_id = m.id
               JOIN properties p ON m.property_id = p.id
               LEFT JOIN units u ON m.unit_id = u.id
               WHERE m.property_id = ?
               AND b.period_start >= date('now', ?)
               ORDER BY b.period_start DESC""",
            (property_id, f"-{months} months"),
        ).fetchall()
        return [BillWithContext(**dict(row)) for row in rows]


def get_all_bills(months: int = 12) -> list[BillWithContext]:
    """Get all bills across all properties with context."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT b.*, p.name as property_name, p.city as property_city,
                      u.unit_number, m.utility_type, m.provider_name,
                      m.account_number, m.meter_number
               FROM bills b
               JOIN meters m ON b.meter_id = m.id
               JOIN properties p ON m.property_id = p.id
               LEFT JOIN units u ON m.unit_id = u.id
               WHERE b.period_start >= date('now', ?)
               ORDER BY b.period_start DESC""",
            (f"-{months} months",),
        ).fetchall()
        return [BillWithContext(**dict(row)) for row in rows]


def get_latest_bill_per_meter() -> list[BillWithContext]:
    """Get the most recent bill for each active meter."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT b.*, p.name as property_name, p.city as property_city,
                      u.unit_number, m.utility_type, m.provider_name,
                      m.account_number, m.meter_number
               FROM bills b
               JOIN meters m ON b.meter_id = m.id
               JOIN properties p ON m.property_id = p.id
               LEFT JOIN units u ON m.unit_id = u.id
               WHERE b.id = (
                   SELECT b2.id FROM bills b2
                   WHERE b2.meter_id = b.meter_id
                   ORDER BY b2.period_start DESC LIMIT 1
               )
               AND m.active = 1
               ORDER BY p.name, m.utility_type"""
        ).fetchall()
        return [BillWithContext(**dict(row)) for row in rows]


# --- Provider Templates ---


def save_provider_template(template: ProviderTemplateModel) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT OR REPLACE INTO provider_templates
            (provider_name, utility_type, file_type, field_patterns, column_mapping, sample_text, confirmed)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                template.provider_name,
                template.utility_type,
                template.file_type,
                template.field_patterns,
                template.column_mapping,
                template.sample_text,
                template.confirmed,
            ),
        )
        return cursor.lastrowid


def get_provider_template(provider_name: str, utility_type: str, file_type: str = "pdf") -> Optional[ProviderTemplateModel]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM provider_templates WHERE provider_name = ? AND utility_type = ? AND file_type = ?",
            (provider_name, utility_type, file_type),
        ).fetchone()
        if row:
            return ProviderTemplateModel(**dict(row))
        return None


def get_all_provider_templates() -> list[ProviderTemplateModel]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM provider_templates ORDER BY provider_name, utility_type").fetchall()
        return [ProviderTemplateModel(**dict(row)) for row in rows]


# --- Anomalies ---


def create_anomaly(anomaly: AnomalyModel) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO anomalies
            (bill_id, anomaly_type, severity, description, value, threshold)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                anomaly.bill_id,
                anomaly.anomaly_type,
                anomaly.severity,
                anomaly.description,
                anomaly.value,
                anomaly.threshold,
            ),
        )
        return cursor.lastrowid


def get_active_anomalies() -> list[AnomalyWithContext]:
    """Get all unacknowledged anomalies with full context."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT a.*, p.name as property_name, p.city as property_city,
                      u.unit_number, m.utility_type, m.provider_name,
                      b.total_amount, b.period_start, b.period_end
               FROM anomalies a
               JOIN bills b ON a.bill_id = b.id
               JOIN meters m ON b.meter_id = m.id
               JOIN properties p ON m.property_id = p.id
               LEFT JOIN units u ON m.unit_id = u.id
               WHERE a.acknowledged = 0
               ORDER BY
                   CASE a.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                   a.created_at DESC"""
        ).fetchall()
        return [AnomalyWithContext(**dict(row)) for row in rows]


def acknowledge_anomaly(anomaly_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE anomalies SET acknowledged = 1, acknowledged_at = CURRENT_TIMESTAMP WHERE id = ?",
            (anomaly_id,),
        )


def clear_anomalies_for_meter(meter_id: int) -> None:
    """Clear old anomalies when re-running detection for a meter."""
    with get_connection() as conn:
        conn.execute(
            """DELETE FROM anomalies WHERE bill_id IN (
                SELECT id FROM bills WHERE meter_id = ?
            ) AND acknowledged = 0""",
            (meter_id,),
        )


# --- Summary Queries ---


def get_monthly_totals(months: int = 12) -> list[dict]:
    """Get total spend per month per utility type across all properties."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT strftime('%Y-%m', b.period_start) as month,
                      m.utility_type,
                      SUM(b.total_amount) as total,
                      COUNT(b.id) as bill_count
               FROM bills b
               JOIN meters m ON b.meter_id = m.id
               WHERE b.period_start >= date('now', ?)
               GROUP BY month, m.utility_type
               ORDER BY month""",
            (f"-{months} months",),
        ).fetchall()
        return [dict(row) for row in rows]


def get_property_monthly_totals(property_id: int, months: int = 12) -> list[dict]:
    """Get monthly spend by utility type for a specific property."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT strftime('%Y-%m', b.period_start) as month,
                      m.utility_type,
                      SUM(b.total_amount) as total,
                      SUM(b.usage_amount) as total_usage,
                      COUNT(b.id) as bill_count
               FROM bills b
               JOIN meters m ON b.meter_id = m.id
               WHERE m.property_id = ?
               AND b.period_start >= date('now', ?)
               GROUP BY month, m.utility_type
               ORDER BY month""",
            (property_id, f"-{months} months"),
        ).fetchall()
        return [dict(row) for row in rows]
