import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DATABASE = Path(__file__).parent / "data" / "datawatch.sqlite3"


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize():
    with connect() as database:
        database.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
                format TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                last_checked TEXT, last_status TEXT NOT NULL DEFAULT 'idle',
                last_error TEXT NOT NULL DEFAULT '', entry_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY, label TEXT NOT NULL, kind TEXT NOT NULL,
                value TEXT NOT NULL, severity TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                UNIQUE(kind, value)
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE,
                source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
                rule_id INTEGER REFERENCES rules(id) ON DELETE SET NULL,
                source_name TEXT NOT NULL, rule_label TEXT NOT NULL,
                title TEXT NOT NULL, excerpt TEXT NOT NULL, url TEXT NOT NULL,
                severity TEXT NOT NULL, signals TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new', created_at TEXT NOT NULL, last_seen TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY, kind TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS alerts_created ON alerts(created_at DESC);
        """)
        database.execute(
            "UPDATE sources SET last_status = 'idle' WHERE last_status = 'scanning'"
        )


def log(database, kind, message):
    database.execute(
        "INSERT INTO activity (kind, message, created_at) VALUES (?, ?, ?)",
        (kind, message, now()),
    )


def list_rows(table):
    if table not in ("sources", "rules", "alerts", "activity"):
        raise ValueError("Table inconnue.")
    with connect() as database:
        rows = [
            dict(row)
            for row in database.execute(
                f"SELECT * FROM {table} ORDER BY id DESC LIMIT 2000"
            )
        ]
    for row in rows:
        if "enabled" in row:
            row["enabled"] = bool(row["enabled"])
        if "signals" in row:
            row["signals"] = json.loads(row["signals"])
            row.pop("fingerprint")
    return rows


def state():
    return {
        name: list_rows(name) for name in ("sources", "rules", "alerts", "activity")
    }


def add_source(name, url, format):
    with connect() as database:
        cursor = database.execute(
            "INSERT INTO sources (name, url, format) VALUES (?, ?, ?)",
            (name, url, format),
        )
        log(database, "source", f"Source ajoutée : {name}.")
        return cursor.lastrowid


def add_rule(label, kind, value, severity):
    with connect() as database:
        cursor = database.execute(
            "INSERT INTO rules (label, kind, value, severity) VALUES (?, ?, ?, ?)",
            (label, kind, value, severity),
        )
        log(database, "rule", f"Règle ajoutée : {label}.")
        return cursor.lastrowid


def set_enabled(table, identifier, enabled):
    if table not in ("sources", "rules"):
        raise ValueError("Type inconnu.")
    with connect() as database:
        cursor = database.execute(
            f"UPDATE {table} SET enabled = ? WHERE id = ?", (int(enabled), identifier)
        )
        if not cursor.rowcount:
            raise LookupError("Élément introuvable.")
        log(
            database,
            "settings",
            f'{"Source" if table == "sources" else "Règle"} #{identifier} {"activée" if enabled else "mise en pause"}.',
        )


def set_alert_status(identifier, status):
    with connect() as database:
        cursor = database.execute(
            "UPDATE alerts SET status = ? WHERE id = ?", (status, identifier)
        )
        if not cursor.rowcount:
            raise LookupError("Signalement introuvable.")
        log(database, "alert", f"Signalement #{identifier} : {status}.")


def start_scan(identifier):
    with connect() as database:
        database.execute(
            "UPDATE sources SET last_status = 'scanning', last_error = '' WHERE id = ?",
            (identifier,),
        )
        log(database, "scan", f"Collecte de la source #{identifier} démarrée.")


def finish_scan(identifier, name, entry_count, alerts, error=""):
    timestamp = now()
    with connect() as database:
        inserted = 0
        for alert in alerts:
            cursor = database.execute(
                """
                INSERT INTO alerts (fingerprint, source_id, rule_id, source_name, rule_label, title,
                  excerpt, url, severity, signals, created_at, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO NOTHING
            """,
                (
                    alert["fingerprint"],
                    identifier,
                    alert["rule_id"],
                    name,
                    alert["rule_label"],
                    alert["title"],
                    alert["excerpt"],
                    alert["url"],
                    alert["severity"],
                    json.dumps(alert["signals"]),
                    timestamp,
                    timestamp,
                ),
            )
            inserted += cursor.rowcount
            database.execute(
                "UPDATE alerts SET last_seen = ? WHERE fingerprint = ?",
                (timestamp, alert["fingerprint"]),
            )
        database.execute(
            """UPDATE sources SET last_checked = ?, last_status = ?, last_error = ?, entry_count = ? WHERE id = ?""",
            (
                timestamp,
                "error" if error else "ok",
                error[:300],
                entry_count,
                identifier,
            ),
        )
        message = (
            f"{name} : échec de la collecte — {error[:180]}"
            if error
            else f"{name} : {entry_count} publication(s), {inserted} nouveau(x) signalement(s)."
        )
        log(database, "error" if error else "scan", message)
    return inserted
