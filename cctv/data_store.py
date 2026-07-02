"""
data_store.py — Local data persistence layer for the CCTV AI Core Engine.

Responsibilities:
  • Initialise and manage the local SQLite telemetry database.
  • Provide a thread-safe interface for inserting structured events.
  • Mirror every event to a newline-delimited JSON log for easy inspection.
  • Expose query helpers that the engine uses for reporting.
  • Define the blacklist schema and load blacklisted face embeddings.

This module is deliberately independent of the engine so it can be swapped
out for a Supabase / PostgreSQL backend by replacing only this file.
"""

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import config

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default blacklist (written to disk if the file does not exist)
# ---------------------------------------------------------------------------
_DEFAULT_BLACKLIST: List[Dict] = [
    {
        "blacklist_id": "BL001",
        "alias": "Suspect-Alpha",
        "risk_level": "HIGH",
        # 8-dimensional mock embedding — replace with real face vectors.
        "mock_embedding": [0.95, 0.05, 0.85, 0.15, 0.75, 0.25, 0.65, 0.35],
        "reason": "Prior shoplifting incident (2024-11-03)",
    },
    {
        "blacklist_id": "BL002",
        "alias": "Suspect-Beta",
        "risk_level": "MEDIUM",
        "mock_embedding": [0.1, 0.9, 0.2, 0.8, 0.3, 0.7, 0.4, 0.6],
        "reason": "Trespassing warning issued (2025-01-15)",
    },
]


# ---------------------------------------------------------------------------
# DataStore
# ---------------------------------------------------------------------------

class DataStore:
    """
    Thread-safe wrapper around SQLite + JSON log file.

    Usage
    -----
    ds = DataStore()
    ds.log_event("PHONE_ABUSE", {"employee_id": "EMP001", "phone_duration_seconds": 6.2})
    """

    def __init__(
        self,
        db_path: str = config.SQLITE_DB_PATH,
        json_path: str = config.JSON_LOG_PATH,
        blacklist_path: str = config.BLACKLIST_PATH,
    ) -> None:
        self._db_path   = db_path
        self._json_path = json_path
        self._lock      = threading.Lock()

        # Ensure parent directories exist.
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_db()
        self._blacklist: List[Dict] = self._load_blacklist(blacklist_path)

        log.info("DataStore initialised. DB=%s  JSON=%s", db_path, json_path)

    # ------------------------------------------------------------------
    # Database initialisation
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Create the telemetry table and indexes if they do not exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT    NOT NULL,
                    event_type  TEXT    NOT NULL,
                    details     TEXT    NOT NULL   -- JSON-encoded dict
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_event_type ON telemetry_events(event_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON telemetry_events(timestamp)"
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        """Return a new SQLite connection with WAL mode for concurrent writes."""
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ------------------------------------------------------------------
    # Public API — event logging
    # ------------------------------------------------------------------

    def log_event(self, event_type: str, details: Dict[str, Any]) -> None:
        """
        Persist a structured event to both SQLite and the JSON log.

        Parameters
        ----------
        event_type : str
            One of: EMPLOYEE_PRESENT, PHONE_ABUSE, CASHIER_MISSING,
            BLACKLIST_SPOTTED, CUSTOMER_COUNT_UPDATE  (or any custom string).
        details : dict
            Arbitrary metadata dict.  Must be JSON-serialisable.
        """
        ts      = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"
        payload = {
            "timestamp":  ts,
            "event_type": event_type,
            "details":    details,
        }

        with self._lock:
            self._write_sqlite(payload)
            self._append_json(payload)

        log.debug("Event logged: %s | %s", event_type, details)

    def _write_sqlite(self, payload: Dict) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO telemetry_events (timestamp, event_type, details) VALUES (?,?,?)",
                (payload["timestamp"], payload["event_type"], json.dumps(payload["details"])),
            )
            conn.commit()

    def _append_json(self, payload: Dict) -> None:
        with open(self._json_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")

    # ------------------------------------------------------------------
    # Public API — queries
    # ------------------------------------------------------------------

    def get_recent_events(self, limit: int = 20) -> List[Dict]:
        """Return the `limit` most recent events as dicts."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT timestamp, event_type, details "
                "FROM telemetry_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"timestamp": r[0], "event_type": r[1], "details": json.loads(r[2])}
            for r in rows
        ]

    def get_event_counts(self) -> Dict[str, int]:
        """Return {event_type: count} aggregation over all stored events."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT event_type, COUNT(*) FROM telemetry_events GROUP BY event_type"
            ).fetchall()
        return {r[0]: r[1] for r in rows}

    def get_employee_presence_summary(self) -> Dict[str, float]:
        """
        Return {employee_id: total_presence_seconds} computed from all
        EMPLOYEE_PRESENT events.  Each event carries a `presence_seconds`
        field in its details.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT details FROM telemetry_events WHERE event_type='EMPLOYEE_PRESENT'"
            ).fetchall()

        totals: Dict[str, float] = {}
        for (raw,) in rows:
            d = json.loads(raw)
            eid = d.get("employee_id", "UNKNOWN")
            totals[eid] = totals.get(eid, 0.0) + float(d.get("presence_seconds", 0))
        return totals

    # ------------------------------------------------------------------
    # Blacklist
    # ------------------------------------------------------------------

    def _load_blacklist(self, path: str) -> List[Dict]:
        """
        Load blacklist entries from JSON.  Creates a default file if absent.
        Each entry must have keys: blacklist_id, alias, risk_level,
        mock_embedding (list[float]).
        """
        if not os.path.exists(path):
            log.warning("Blacklist file not found — creating default at %s", path)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(_DEFAULT_BLACKLIST, fh, indent=2)
            return list(_DEFAULT_BLACKLIST)

        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)

        log.info("Loaded %d blacklist entries from %s", len(data), path)
        return data

    @property
    def blacklist(self) -> List[Dict]:
        """Read-only access to the loaded blacklist entries."""
        return self._blacklist

    def reload_blacklist(self, path: str = config.BLACKLIST_PATH) -> None:
        """Hot-reload the blacklist without restarting the engine."""
        with self._lock:
            self._blacklist = self._load_blacklist(path)
        log.info("Blacklist reloaded: %d entries", len(self._blacklist))
