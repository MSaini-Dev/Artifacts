"""
data_store.py — APIStore adapter interacting with SQLite database API_Store.db.
"""

import os
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from ..db_updater import DEFAULT_DB_FILE, get_connection, seed_default_data
from ..api_caller import reactivate_expired_cooldowns


class APIStore:
    def __init__(self, db_file=DEFAULT_DB_FILE):
        self.db_file = db_file
        self._lock = threading.Lock()
        seed_default_data(self.db_file)

    @property
    def data(self) -> Dict[str, Any]:
        """Dynamically build a nested dictionary view of SQLite DB for compatibility."""
        reactivate_expired_cooldowns(self.db_file)
        out = {}
        with get_connection(self.db_file) as conn:
            providers = conn.execute("SELECT * FROM providers").fetchall()
            for p in providers:
                pid = p["id"]
                pname = p["name"]
                out[pname] = {
                    "status": p["status"],
                    "rate_limit": p["rate_limit"],
                    "models": {},
                    "api_data": {},
                }
                models = conn.execute("SELECT * FROM models WHERE provider_id = ?", (pid,)).fetchall()
                for m in models:
                    out[pname]["models"][m["name"]] = {
                        "status": m["status"],
                        "size": m["model_size"],
                        "RPM": m["RPM"],
                        "RPD": m["RPD"],
                        "TPM": m["TPM"],
                        "TPD": m["TPD"],
                        "disabled_reason": m["disabled_reason"],
                    }
                keys = conn.execute("SELECT * FROM api_keys WHERE provider_id = ?", (pid,)).fetchall()
                for k in keys:
                    out[pname]["api_data"][k["unique_name"]] = {
                        "status": k["status"],
                        "rate_limit": k["rate_limit"],
                        "disabled_reason": k["disabled_reason"],
                        "env_key": k["env_key"],
                    }
        return out

    def reactivate_expired_cooldowns(self) -> bool:
        return reactivate_expired_cooldowns(self.db_file)

    def provider_exists(self, provider: str) -> bool:
        with get_connection(self.db_file) as conn:
            row = conn.execute("SELECT 1 FROM providers WHERE LOWER(name) = LOWER(?)", (provider,)).fetchone()
            return row is not None

    def get_active_providers(self) -> List[str]:
        reactivate_expired_cooldowns(self.db_file)
        with get_connection(self.db_file) as conn:
            rows = conn.execute("SELECT name FROM providers WHERE status = 'active'").fetchall()
            return [r["name"] for r in rows]

    def set_provider_status(self, provider: str, status: str, cooldown_until: Optional[str] = None):
        with self._lock:
            with get_connection(self.db_file) as conn:
                conn.execute(
                    "UPDATE providers SET status = ?, rate_limit = ?, last_modify = ? WHERE LOWER(name) = LOWER(?)",
                    (status, cooldown_until, datetime.now().isoformat(), provider)
                )
                conn.commit()

    def update_provider_status(self, provider: str, status: str, cooldown_until: Optional[str] = None):
        return self.set_provider_status(provider, status, cooldown_until)

    def disable_model(self, provider: str, model: str, reason: str = "deprecated"):
        with self._lock:
            with get_connection(self.db_file) as conn:
                conn.execute(
                    """
                    UPDATE models
                    SET status = 'disabled', disabled_reason = ?, last_modify = ?
                    WHERE provider_id = (SELECT id FROM providers WHERE LOWER(name) = LOWER(?))
                      AND LOWER(name) = LOWER(?)
                    """,
                    (reason, datetime.now().isoformat(), provider, model)
                )
                conn.commit()

    def update_model_status(self, provider: str, model: str, status: str):
        with self._lock:
            with get_connection(self.db_file) as conn:
                conn.execute(
                    """
                    UPDATE models
                    SET status = ?, last_modify = ?
                    WHERE provider_id = (SELECT id FROM providers WHERE LOWER(name) = LOWER(?))
                      AND LOWER(name) = LOWER(?)
                    """,
                    (status, datetime.now().isoformat(), provider, model)
                )
                conn.commit()

    def disable_api(self, provider: str, key_name: str, reason: str = "missing_env_var"):
        with self._lock:
            with get_connection(self.db_file) as conn:
                conn.execute(
                    """
                    UPDATE api_keys
                    SET status = 'disabled', disabled_reason = ?, last_modify = ?
                    WHERE provider_id = (SELECT id FROM providers WHERE LOWER(name) = LOWER(?))
                      AND (LOWER(unique_name) = LOWER(?) OR LOWER(env_key) = LOWER(?))
                    """,
                    (reason, datetime.now().isoformat(), provider, key_name, key_name)
                )
                conn.commit()

    def cooldown_api(self, provider: str, key_name: str, seconds: int = 60):
        cooldown_until = (datetime.now() + timedelta(seconds=seconds)).isoformat()
        with self._lock:
            with get_connection(self.db_file) as conn:
                conn.execute(
                    """
                    UPDATE api_keys
                    SET status = 'cooldown', rate_limit = ?, last_modify = ?
                    WHERE provider_id = (SELECT id FROM providers WHERE LOWER(name) = LOWER(?))
                      AND (LOWER(unique_name) = LOWER(?) OR LOWER(env_key) = LOWER(?))
                    """,
                    (cooldown_until, datetime.now().isoformat(), provider, key_name, key_name)
                )
                conn.commit()

    def update_api_status(self, provider: str, key_name: str, status: str, cooldown_until: Optional[str] = None, reason: Optional[str] = None):
        with self._lock:
            with get_connection(self.db_file) as conn:
                conn.execute(
                    """
                    UPDATE api_keys
                    SET status = ?, rate_limit = ?, disabled_reason = ?, last_modify = ?
                    WHERE provider_id = (SELECT id FROM providers WHERE LOWER(name) = LOWER(?))
                      AND (LOWER(unique_name) = LOWER(?) OR LOWER(env_key) = LOWER(?))
                    """,
                    (status, cooldown_until, reason, datetime.now().isoformat(), provider, key_name, key_name)
                )
                conn.commit()