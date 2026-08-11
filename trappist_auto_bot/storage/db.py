"""SQLite persistence for generations, payments and deduplication."""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class GenerationRecord:
    id: int
    created_at: datetime
    prompt: str
    image_url: str
    amount_motes: int
    cost_usd: str
    cost_cspr: str
    pay_to: str
    telegram_message_id: int | None


class Database:
    """Lightweight SQLite store for the autonomous bot."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_tables(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    prompt TEXT NOT NULL,
                    image_url TEXT NOT NULL,
                    amount_motes INTEGER NOT NULL,
                    cost_usd TEXT,
                    cost_cspr TEXT,
                    pay_to TEXT,
                    telegram_message_id INTEGER
                );

                CREATE TABLE IF NOT EXISTS posted_links (
                    link TEXT PRIMARY KEY,
                    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS scheduler_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_generations_created
                    ON generations(created_at);
                """
            )

    def record_generation(
        self,
        prompt: str,
        image_url: str,
        amount_motes: int,
        cost_usd: str,
        cost_cspr: str,
        pay_to: str,
        telegram_message_id: int | None = None,
    ) -> int:
        """Persist a successful generation."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO generations
                    (prompt, image_url, amount_motes, cost_usd, cost_cspr, pay_to, telegram_message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (prompt, image_url, amount_motes, cost_usd, cost_cspr, pay_to, telegram_message_id),
            )
            logger.info("Recorded generation id=%s", cursor.lastrowid)
            return cursor.lastrowid

    def record_posted_link(self, link: str) -> None:
        """Mark an RSS link as already posted to avoid duplicates."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO posted_links (link) VALUES (?)",
                (link,),
            )

    def is_link_posted(self, link: str) -> bool:
        """Return True if the link has already been posted."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM posted_links WHERE link = ?", (link,)
            ).fetchone()
            return row is not None

    def get_state(self, key: str) -> str | None:
        """Return the last stored scheduler state value for a key."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM scheduler_state WHERE key = ?", (key,)
            ).fetchone()
            return row[0] if row else None

    def set_state(self, key: str, value: str) -> None:
        """Store or update a scheduler state value."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO scheduler_state (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, value),
            )

    def daily_spend_motes(self) -> int:
        """Return the total amount spent in the last 24 hours."""
        since = datetime.utcnow() - timedelta(days=1)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(amount_motes), 0) FROM generations WHERE created_at > ?",
                (since.isoformat(),),
            ).fetchone()
            return row[0] if row else 0

    def recent_generations(self, limit: int = 10) -> list[GenerationRecord]:
        """Return recent generation records ordered by most recent first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM generations ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [GenerationRecord(**dict(row)) for row in rows]

    def stats(self) -> dict[str, Any]:
        """Return aggregate bot statistics."""
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(amount_motes), 0) FROM generations"
            ).fetchone()
            today = conn.execute(
                "SELECT COUNT(*) FROM generations WHERE created_at > datetime('now', '-1 day')"
            ).fetchone()
            images = self.get_burn_counter()
            burned = round(images * 0.1, 1)
            return {
                "total_generations": total[0],
                "total_spent_motes": total[1],
                "generations_last_24h": today[0],
                "burn_counter_images": images,
                "burn_counter_cspr": burned,
            }

    def get_burn_counter(self) -> int:
        """Return the number of TrappistAI generations counted for CSPR burn."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM scheduler_state WHERE key = 'burn_counter_images'"
            ).fetchone()
            return int(row[0]) if row and row[0] is not None else 0

    def increment_burn_counter(self) -> int:
        """Increment and return the TrappistAI generation counter."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO scheduler_state (key, value)
                VALUES ('burn_counter_images', '1')
                ON CONFLICT(key) DO UPDATE SET
                    value = CAST(value AS INTEGER) + 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
            )
            row = conn.execute(
                "SELECT value FROM scheduler_state WHERE key = 'burn_counter_images'"
            ).fetchone()
            return int(row[0]) if row else 0

    def reset_burn_counter(self) -> None:
        """Reset the burn counter to zero."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO scheduler_state (key, value)
                VALUES ('burn_counter_images', '0')
                ON CONFLICT(key) DO UPDATE SET
                    value = '0',
                    updated_at = CURRENT_TIMESTAMP
                """,
            )
            logger.info("Burn counter reset to zero")
