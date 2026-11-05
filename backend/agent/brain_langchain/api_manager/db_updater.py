"""
db_updater.py — SQLite database initialization and update routines for API Store.
"""

import os
import sqlite3
from datetime import datetime
from typing import Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEFAULT_DB_FILE = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data", "API_Store.db")
)


def get_connection(file_path: str = DEFAULT_DB_FILE):
    conn = sqlite3.connect(file_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_database(file_path: str = DEFAULT_DB_FILE):
    with get_connection(file_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                base_url TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                rate_limit TEXT,
                created_at TEXT NOT NULL,
                last_modify TEXT NOT NULL
            )
        """)
        _ensure_column(conn, "providers", "rate_limit", "rate_limit TEXT")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                preference TEXT,
                model_size REAL,
                RPM INTEGER,
                RPD INTEGER,
                TPM INTEGER,
                TPD INTEGER,
                disabled_reason TEXT,
                rate_limit TEXT,
                created_at TEXT NOT NULL,
                last_modify TEXT NOT NULL,
                FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE,
                UNIQUE(provider_id, name)
            )
        """)
        _ensure_column(conn, "models", "disabled_reason", "disabled_reason TEXT")
        _ensure_column(conn, "models", "rate_limit", "rate_limit TEXT")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id INTEGER NOT NULL,
                unique_name TEXT NOT NULL,
                env_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active',
                rate_limit TEXT,
                disabled_reason TEXT,
                created_at TEXT NOT NULL,
                last_modify TEXT NOT NULL,
                FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE,
                UNIQUE(provider_id, unique_name)
            )
        """)

    from .sqlite_logger import init_logging_schema
    init_logging_schema(conn)
    conn.commit()


def provider_generator(
    base_url: str,
    provider_name: str,
    file_path: str = DEFAULT_DB_FILE,
):
    now = datetime.now().isoformat()
    init_database(file_path)
    with get_connection(file_path) as conn:
        existing = conn.execute(
            "SELECT id FROM providers WHERE name = ?",
            (provider_name,),
        ).fetchone()

        if existing:
            return {
                "id": existing["id"],
                "name": provider_name,
                "base_url": base_url,
                "status": "active",
            }

        cursor = conn.execute(
            """
            INSERT INTO providers (name, base_url, status, created_at, last_modify)
            VALUES (?, ?, 'active', ?, ?)
            """,
            (provider_name, base_url, now, now),
        )
        provider_id = cursor.lastrowid
        conn.commit()

    return {
        "id": provider_id,
        "name": provider_name,
        "base_url": base_url,
        "status": "active",
        "created_at": now,
        "last_modify": now,
    }


def model_generator(
    provider_name: str,
    model_name: str,
    preference: Optional[str] = None,
    model_size: Optional[float] = None,
    RPM: Optional[int] = None,
    RPD: Optional[int] = None,
    TPM: Optional[int] = None,
    TPD: Optional[int] = None,
    file_path: str = DEFAULT_DB_FILE,
):
    now = datetime.now().isoformat()
    init_database(file_path)
    with get_connection(file_path) as conn:
        provider = conn.execute(
            "SELECT id FROM providers WHERE name = ?",
            (provider_name,),
        ).fetchone()

        if not provider:
            raise ValueError(f"Provider '{provider_name}' does not exist")

        provider_id = provider["id"]

        existing = conn.execute(
            "SELECT id FROM models WHERE provider_id = ? AND name = ?",
            (provider_id, model_name),
        ).fetchone()

        if existing:
            return {"id": existing["id"], "provider": provider_name, "name": model_name}

        cursor = conn.execute(
            """
            INSERT INTO models (
                provider_id, name, status, preference, model_size,
                RPM, RPD, TPM, TPD, created_at, last_modify
            )
            VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (provider_id, model_name, preference, model_size, RPM, RPD, TPM, TPD, now, now),
        )
        model_id = cursor.lastrowid

        conn.execute(
            "UPDATE providers SET last_modify = ? WHERE id = ?",
            (now, provider_id),
        )
        conn.commit()

    return {
        "id": model_id,
        "provider": provider_name,
        "name": model_name,
        "status": "active",
        "preference": preference,
        "model_size": model_size,
        "RPM": RPM,
        "RPD": RPD,
        "TPM": TPM,
        "TPD": TPD,
        "created_at": now,
        "last_modify": now,
    }


def _parse_env_key(env_key: str) -> Tuple[Optional[str], Optional[str]]:
    clean_key = env_key
    if clean_key.startswith("LLM_"):
        clean_key = clean_key[4:]
    if not clean_key.startswith("API_KEY_"):
        return None, None
    parts = clean_key.split("_", 3)
    if len(parts) == 3:
        _, _, provider_name = parts
        unique_name = "MAIN"
    elif len(parts) >= 4:
        _, _, provider_name, unique_name = parts
    else:
        return None, None
    return provider_name.lower(), unique_name.upper()


def update_api_keys(file_path: str = DEFAULT_DB_FILE):
    now = datetime.now().isoformat()
    init_database(file_path)

    with get_connection(file_path) as conn:
        for env_key, val in os.environ.items():
            if not val or not val.strip():
                continue

            provider_name, unique_name = _parse_env_key(env_key)
            if not provider_name or not unique_name:
                continue

            provider = conn.execute(
                "SELECT id FROM providers WHERE LOWER(name) = ?",
                (provider_name,),
            ).fetchone()

            if not provider:
                continue

            provider_id = provider["id"]

            existing = conn.execute(
                "SELECT id FROM api_keys WHERE env_key = ?",
                (env_key,),
            ).fetchone()

            if existing:
                continue

            existing_name = conn.execute(
                "SELECT id FROM api_keys WHERE provider_id = ? AND unique_name = ?",
                (provider_id, unique_name),
            ).fetchone()

            if existing_name:
                conn.execute(
                    """
                    UPDATE api_keys
                    SET env_key = ?, status = 'active', disabled_reason = NULL, last_modify = ?
                    WHERE id = ?
                    """,
                    (env_key, now, existing_name["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO api_keys (
                        provider_id, unique_name, env_key, status,
                        rate_limit, disabled_reason, created_at, last_modify
                    )
                    VALUES (?, ?, ?, 'active', NULL, NULL, ?, ?)
                    """,
                    (provider_id, unique_name, env_key, now, now),
                )

            conn.execute(
                "UPDATE providers SET last_modify = ? WHERE id = ?",
                (now, provider_id),
            )

        conn.commit()


def seed_default_data(file_path: str = DEFAULT_DB_FILE):
    init_database(file_path)

    providers_def = [
        ("groq", "https://api.groq.com/openai/v1/chat/completions"),
        ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"),
        ("cerebras", "https://api.cerebras.ai/v1/chat/completions"),
    ]
    for pname, url in providers_def:
        provider_generator(url, pname, file_path)

    models_def = [
        ("gemini", "gemini-3.5-flash-lite", 200, 15, 1500, 1000000, 2000000),
        ("groq", "openai/gpt-oss-120b", 120, 30, 1000, 8000, 200000),
        ("groq", "qwen/qwen3.6-27b", 27, 30, 1000, 8000, 200000),
        ("groq", "openai/gpt-oss-20b", 20, 30, 1000, 8000, 200000),
        ("groq", "openai/gpt-oss-safeguard-20b", 20, 30, 1000, 8000, 200000),
        ("cerebras", "gpt-oss-120b", 120, None, None, None, None),
        ("cerebras", "gemma-4-31b", 31, None, None, None, None),
    ]

    for pname, mname, msize, rpm, rpd, tpm, tpd in models_def:
        try:
            model_generator(
                provider_name=pname,
                model_name=mname,
                model_size=msize,
                RPM=rpm, RPD=rpd, TPM=tpm, TPD=tpd,
                file_path=file_path,
            )
        except ValueError:
            pass

    update_api_keys(file_path)


if __name__ == "__main__":
    seed_default_data()
    print("DB_Updater completed!")
