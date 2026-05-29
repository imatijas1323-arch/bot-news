from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from .ai_client import BaseAIClient, AIClientError
from .config import Settings
from .filter import is_topic_candidate
from .models import ArticleCandidate, ArticleRecord, ArticleStatus
from .rss_reader import fetch_rss_candidates
from .storage import SQLiteStorage, start_of_local_day_utc, utc_now
from .writer import build_feedback_context, build_recent_published_context


logger = logging.getLogger(__name__)

DraftCallback = Callable[[ArticleRecord], Awaitable[None]]

_pipeline_lock = asyncio.Lock()


class NewsPipeline:
    def __init__(
        self,
        *,
        settings: Settings,
        storage: SQLiteStorage,
        ai_client: BaseAIClient,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.ai_client = ai_client

    async def run_once(
        self,
        on_draft: DraftCallback | None = None,
        *,
        breaking: bool = False,
    ) -> list[ArticleRecord]:
        if _pipeline_lock.locked():
            logger.info("News pipeline already running")
            return []
        async with _pipeline_lock:
            return await self._run_once_unlocked(on_draft=on_draft, breaking=breaking)

    async def _run_once_unlocked(
        self,
        on_draft: DraftCallback | None = None,
        *,
        breaking: bool = False,
    ) -> list[ArticleRecord]:
        self.storage.init_db()
        day_start = start_of_local_day_utc(self.settings.timezone)

        if breaking:
            if self.storage.count_breaking_published_since(day_start) >= self.settings.max_breaking_posts_per_day:
                logger.info("Daily breaking publication limit reached")
                return []
        else:
            if self.storage.count_published_since(day_start) >= self.settings.max_posts_per_day:
                logger.info("Daily publication limit reached")
                return []
            if self.storage.count_drafts_since(day_start) >= self.settings.max_drafts_per_day:
                logger.info("Daily draft limit reached")
                return []

        candidates = await fetch_rss_candidates(
            self.settings.rss_feeds,
            timeout_seconds=self.settings.http_timeout_seconds,
        )

        if breaking:
            age_cutoff = utc_now() - timedelta(hours=self.settings.breaking_max_age_hours)
            candidates = [
                c for c in candidates
                if c.published_at is not None and c.published_at >= age_cutoff
            ]

        drafted: list[ArticleRecord] = []
        processed = 0
        preview_cap = self.settings.max_previews_per_run

        logger.info(
            "Pipeline start: %d candidates from RSS (preview cap %d)",
            len(candidates),
            preview_cap,
        )
        for candidate in candidates:
            if preview_cap and len(drafted) >= preview_cap:
                logger.info("Reached per-run preview cap of %d", preview_cap)
                break
            if processed >= self.settings.max_candidates_per_run:
                break

            article, inserted = self.storage.upsert_found(candidate)
            if not inserted and article.status != ArticleStatus.FOUND:
                continue

            if not is_topic_candidate(candidate):
                self.storage.mark_filtered(article.id)
                continue

            processed += 1
            logger.info("Curating [%d/%d]: %s", processed, self.settings.max_candidates_per_run, candidate.original_title[:60])
            draft = await self._process_candidate(article.id, candidate, breaking=breaking)
            if draft is None:
                continue
            drafted.append(draft)
            if on_draft is not None:
                await on_draft(draft)

        logger.info("Pipeline done: %d drafted from %d processed", len(drafted), processed)

        return drafted

    async def _process_candidate(
        self,
        article_id: int,
        candidate: ArticleCandidate,
        *,
        breaking: bool = False,
    ) -> ArticleRecord | None:
        recent_rated = self.storage.get_recent_rated(limit=20)
        feedback_context = build_feedback_context(recent_rated)
        recent_published = self.storage.get_recent_published(limit=12)
        diversity_context = build_recent_published_context(recent_published)
        try:
            decision = await asyncio.wait_for(
                self.ai_client.curate(candidate, feedback_context, diversity_context),
                timeout=self.settings.ai_candidate_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "AI curator timed out for article_id=%s after %.1fs",
                article_id,
                self.settings.ai_candidate_timeout_seconds,
            )
            self.storage.mark_rejected(article_id, category="ai_timeout", ai_score=0)
            return None
        except AIClientError:
            logger.exception("AI curator failed for article_id=%s", article_id)
            return None

        min_score = self.settings.breaking_min_ai_score if breaking else self.settings.min_ai_score
        if not decision.accept or decision.score < min_score:
            logger.info("  rejected: score=%d accept=%s reason=%s", decision.score, decision.accept, decision.reason[:60])
            self.storage.mark_rejected(
                article_id,
                category=decision.category,
                ai_score=decision.score,
            )
            return None
        logger.info("  accepted: score=%d category=%s title_ru=%s", decision.score, decision.category, decision.title_ru[:40])

        return self.storage.save_preview(article_id, decision, is_breaking=breaking)
