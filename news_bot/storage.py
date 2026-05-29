from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, time, timezone
from pathlib import Path

from .models import ArticleCandidate, ArticleRecord, ArticleStatus, CuratorDecision


class SQLiteStorage:
    def __init__(self, database_path: Path, timezone_name: str = "Europe/Moscow") -> None:
        self.database_path = database_path
        self.timezone_name = timezone_name
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.database_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        return self._conn

    def init_db(self) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_title TEXT NOT NULL,
                    original_url TEXT NOT NULL UNIQUE,
                    source_name TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    category TEXT,
                    image_url TEXT,
                    status TEXT NOT NULL,
                    ai_score INTEGER,
                    generated_text TEXT,
                    is_breaking INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    published_at TEXT,
                    user_rating INTEGER,
                    rating_reason TEXT,
                    summary_ru TEXT NOT NULL DEFAULT ""
                )
                """
            )
            try:
                self.conn.execute(
                    "ALTER TABLE articles ADD COLUMN is_breaking INTEGER NOT NULL DEFAULT 0"
                )
            except Exception:
                pass
            try:
                self.conn.execute(
                    "ALTER TABLE articles ADD COLUMN user_rating INTEGER"
                )
            except Exception:
                pass
            try:
                self.conn.execute(
                    "ALTER TABLE articles ADD COLUMN summary_ru TEXT NOT NULL DEFAULT ''"
                )
            except Exception:
                pass
            try:
                self.conn.execute(
                    "ALTER TABLE articles ADD COLUMN rating_reason TEXT"
                )
            except Exception:
                pass
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at)"
            )

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def upsert_found(self, candidate: ArticleCandidate) -> tuple[ArticleRecord, bool]:
        now = utc_now_iso()
        with self._lock, self.conn:
            cursor = self.conn.execute(
                """
                INSERT OR IGNORE INTO articles (
                    original_title,
                    original_url,
                    source_name,
                    summary,
                    image_url,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.original_title,
                    candidate.original_url,
                    candidate.source_name,
                    candidate.summary,
                    candidate.image_url,
                    ArticleStatus.FOUND.value,
                    now,
                    now,
                ),
            )
            inserted = cursor.rowcount == 1
            row = self.conn.execute(
                "SELECT * FROM articles WHERE original_url = ?",
                (candidate.original_url,),
            ).fetchone()
        return row_to_record(row), inserted

    def get_article(self, article_id: int) -> ArticleRecord | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        return row_to_record(row) if row else None

    def set_status(
        self,
        article_id: int,
        status: ArticleStatus,
        *,
        category: str | None = None,
        ai_score: int | None = None,
    ) -> ArticleRecord:
        now = utc_now_iso()
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE articles
                   SET status = ?,
                       category = COALESCE(?, category),
                       ai_score = COALESCE(?, ai_score),
                       updated_at = ?
                 WHERE id = ?
                """,
                (status.value, category, ai_score, now, article_id),
            )
        record = self.get_article(article_id)
        if record is None:
            raise KeyError(f"Article not found: {article_id}")
        return record

    def save_preview(
        self,
        article_id: int,
        decision: CuratorDecision,
        *,
        is_breaking: bool = False,
    ) -> ArticleRecord:
        now = utc_now_iso()
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE articles
                   SET status = ?,
                       category = ?,
                       ai_score = ?,
                       generated_text = ?,
                       summary_ru = ?,
                       is_breaking = ?,
                       updated_at = ?
                 WHERE id = ?
                """,
                (
                    ArticleStatus.DRAFTED.value,
                    decision.category,
                    decision.score,
                    decision.title_ru or None,
                    decision.summary_ru or None,
                    int(is_breaking),
                    now,
                    article_id,
                ),
            )
        record = self.get_article(article_id)
        if record is None:
            raise KeyError(f"Article not found: {article_id}")
        return record

    def save_draft(
        self,
        article_id: int,
        decision: CuratorDecision,
        generated_text: str,
        *,
        is_breaking: bool = False,
    ) -> ArticleRecord:
        now = utc_now_iso()
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE articles
                   SET status = ?,
                       category = ?,
                       ai_score = ?,
                       generated_text = ?,
                       is_breaking = ?,
                       updated_at = ?
                 WHERE id = ?
                """,
                (
                    ArticleStatus.DRAFTED.value,
                    decision.category,
                    decision.score,
                    generated_text,
                    int(is_breaking),
                    now,
                    article_id,
                ),
            )
        record = self.get_article(article_id)
        if record is None:
            raise KeyError(f"Article not found: {article_id}")
        return record

    def set_image_url(self, article_id: int, image_url: str) -> None:
        if not image_url:
            return
        now = utc_now_iso()
        with self._lock, self.conn:
            self.conn.execute(
                "UPDATE articles SET image_url = ?, updated_at = ? WHERE id = ?",
                (image_url, now, article_id),
            )

    def save_rating(self, article_id: int, rating: int, reason: str | None = None) -> None:
        now = utc_now_iso()
        with self._lock, self.conn:
            self.conn.execute(
                "UPDATE articles SET user_rating = ?, rating_reason = ?, updated_at = ? WHERE id = ?",
                (max(1, min(10, rating)), reason, now, article_id),
            )

    def get_recent_published(self, limit: int = 12) -> list[ArticleRecord]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM articles
                 WHERE status = ?
                   AND published_at IS NOT NULL
                 ORDER BY published_at DESC
                 LIMIT ?
                """,
                (ArticleStatus.PUBLISHED.value, limit),
            ).fetchall()
        return [row_to_record(row) for row in rows]

    def get_recent_rated(self, limit: int = 20) -> list[ArticleRecord]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM articles
                 WHERE user_rating IS NOT NULL
                 ORDER BY updated_at DESC
                 LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [row_to_record(row) for row in rows]

    def mark_approved(self, article_id: int) -> ArticleRecord:
        return self.set_status(article_id, ArticleStatus.APPROVED)

    def mark_skipped(self, article_id: int) -> ArticleRecord:
        return self.set_status(article_id, ArticleStatus.SKIPPED)

    def mark_rejected(
        self,
        article_id: int,
        *,
        category: str | None = None,
        ai_score: int | None = None,
    ) -> ArticleRecord:
        return self.set_status(
            article_id,
            ArticleStatus.REJECTED,
            category=category,
            ai_score=ai_score,
        )

    def mark_filtered(self, article_id: int) -> ArticleRecord:
        return self.set_status(article_id, ArticleStatus.FILTERED)

    def mark_published(self, article_id: int) -> ArticleRecord:
        now = utc_now_iso()
        with self._lock, self.conn:
            self.conn.execute(
                """
                UPDATE articles
                   SET status = ?,
                       published_at = ?,
                       updated_at = ?
                 WHERE id = ?
                """,
                (ArticleStatus.PUBLISHED.value, now, now, article_id),
            )
        record = self.get_article(article_id)
        if record is None:
            raise KeyError(f"Article not found: {article_id}")
        return record

    def count_published_since(self, since_utc: datetime) -> int:
        return self._count_since(
            "published_at",
            [ArticleStatus.PUBLISHED],
            since_utc,
        )

    def count_breaking_published_since(self, since_utc: datetime) -> int:
        placeholders = "?"
        query = """
            SELECT COUNT(*) AS total
              FROM articles
             WHERE status = ?
               AND is_breaking = 1
               AND published_at IS NOT NULL
               AND published_at >= ?
        """
        with self._lock:
            row = self.conn.execute(
                query, (ArticleStatus.PUBLISHED.value, since_utc.isoformat())
            ).fetchone()
        return int(row["total"])

    def count_drafts_since(self, since_utc: datetime) -> int:
        return self._count_since(
            "updated_at",
            [
                ArticleStatus.DRAFTED,
                ArticleStatus.APPROVED,
                ArticleStatus.PUBLISHED,
                ArticleStatus.SKIPPED,
            ],
            since_utc,
        )


    def count_by_status(self) -> dict[ArticleStatus, int]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT status, COUNT(*) AS total FROM articles GROUP BY status"
            ).fetchall()
        return {ArticleStatus(str(row["status"])): int(row["total"]) for row in rows}

    def recent_drafts(self, limit: int = 5) -> list[ArticleRecord]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT *
                  FROM articles
                 WHERE status IN (?, ?, ?, ?)
                 ORDER BY updated_at DESC
                 LIMIT ?
                """,
                (
                    ArticleStatus.DRAFTED.value,
                    ArticleStatus.APPROVED.value,
                    ArticleStatus.PUBLISHED.value,
                    ArticleStatus.SKIPPED.value,
                    limit,
                ),
            ).fetchall()
        return [row_to_record(row) for row in rows]

    def _count_since(
        self,
        column: str,
        statuses: list[ArticleStatus],
        since_utc: datetime,
    ) -> int:
        placeholders = ", ".join("?" for _ in statuses)
        query = f"""
            SELECT COUNT(*) AS total
              FROM articles
             WHERE status IN ({placeholders})
               AND {column} IS NOT NULL
               AND {column} >= ?
        """
        params = [status.value for status in statuses]
        params.append(since_utc.isoformat())
        with self._lock:
            row = self.conn.execute(query, params).fetchone()
        return int(row["total"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def start_of_local_day_utc(tz) -> datetime:
    local_now = utc_now().astimezone(tz)
    local_start = datetime.combine(local_now.date(), time.min, tzinfo=tz)
    return local_start.astimezone(timezone.utc)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def row_to_record(row: sqlite3.Row) -> ArticleRecord:
    return ArticleRecord(
        id=int(row["id"]),
        original_title=str(row["original_title"]),
        original_url=str(row["original_url"]),
        source_name=str(row["source_name"]),
        summary=str(row["summary"] or ""),
        category=row["category"],
        image_url=row["image_url"],
        status=ArticleStatus(str(row["status"])),
        ai_score=row["ai_score"],
        generated_text=row["generated_text"],
        is_breaking=bool(row["is_breaking"]),
        created_at=parse_dt(row["created_at"]) or utc_now(),
        updated_at=parse_dt(row["updated_at"]) or utc_now(),
        published_at=parse_dt(row["published_at"]),
        user_rating=row["user_rating"],
        rating_reason=row["rating_reason"],
        summary_ru=str(row["summary_ru"] or ""),
    )

