"""
Database CRUD service for LinkedIn Analytics.

Handles all database operations:
  - Storing posts with deduplication
  - Querying recent posts
  - Computing engagement baselines
  - Storing and retrieving LLM analyses
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from models.database import (
    AnalysisRow,
    PostRow,
    get_session_factory,
    init_db as _init_db,
)
from models.post import PostData
from utils.logger import get_logger

logger = get_logger(__name__)

# Module-level session factory (lazy-initialized)
_SessionFactory = None


def _get_session():
    """Get a database session."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = get_session_factory()
    return _SessionFactory()


def init_db() -> None:
    """Initialize database tables."""
    _init_db()


# ── Post Storage ─────────────────────────────────────────────────────────────


def store_posts(posts: list[PostData]) -> int:
    """
    Store a batch of posts to the database with deduplication.

    Posts are deduplicated by post_urn. If a post with the same URN already
    exists, it is silently skipped.

    Args:
        posts: List of normalized PostData objects from Phase 1.

    Returns:
        Number of NEW posts inserted (excludes duplicates).
    """
    if not posts:
        return 0

    session = _get_session()
    new_count = 0

    try:
        for post in posts:
            # Check for duplicate by post_urn
            if post.post_urn:
                existing = session.execute(
                    select(PostRow.id).where(PostRow.post_urn == post.post_urn)
                ).scalar_one_or_none()

                if existing is not None:
                    logger.debug(f"Skipping duplicate post: {post.post_urn}")
                    continue

            # Also check by text + timestamp as fallback dedup
            if not post.post_urn:
                existing = session.execute(
                    select(PostRow.id).where(
                        PostRow.company == post.company,
                        PostRow.text == post.text,
                        PostRow.timestamp == post.timestamp,
                    )
                ).scalar_one_or_none()

                if existing is not None:
                    logger.debug(f"Skipping duplicate post (text+timestamp match)")
                    continue

            # Create row from PostData
            row = PostRow(
                company=post.company,
                text=post.text,
                post_type=post.post_type,
                timestamp=post.timestamp,
                likes=post.likes,
                comments=post.comments,
                shares=post.shares,
                engagement_score=post.engagement_score,
                engagement_rate=round(post.engagement_rate, 2),
                reactions_json=json.dumps(post.reactions.model_dump()),
                hashtags_json=json.dumps(post.hashtags),
                media_description=post.media_description,
                post_url=post.post_url,
                post_urn=post.post_urn,
                media_urls_json=json.dumps(post.media_urls),
                follower_count=post.follower_count,
                is_repost=post.is_repost,
                is_edited=post.is_edited,
                author_name=post.author_name,
            )

            session.add(row)
            new_count += 1

        session.commit()
        logger.info(f"Stored {new_count} new posts (skipped {len(posts) - new_count} duplicates)")
        return new_count

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to store posts: {e}")
        raise
    finally:
        session.close()


# ── Post Queries ─────────────────────────────────────────────────────────────


def get_recent_posts(
    company: str | None = None,
    days: int = 7,
) -> list[PostRow]:
    """
    Fetch posts from the last N days.

    Args:
        company: Filter by company name (None = all companies).
        days: Number of days to look back (default: 7).

    Returns:
        List of PostRow objects, ordered by timestamp descending.
    """
    session = _get_session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        query = select(PostRow).where(PostRow.timestamp >= cutoff)

        if company:
            query = query.where(PostRow.company == company)

        query = query.order_by(PostRow.timestamp.desc())
        result = session.execute(query).scalars().all()
        return list(result)
    finally:
        session.close()


def get_all_posts(company: str | None = None) -> list[PostRow]:
    """
    Fetch all stored posts.

    Args:
        company: Filter by company name (None = all companies).

    Returns:
        List of PostRow objects, ordered by timestamp descending.
    """
    session = _get_session()
    try:
        query = select(PostRow)

        if company:
            query = query.where(PostRow.company == company)

        query = query.order_by(PostRow.timestamp.desc())
        result = session.execute(query).scalars().all()
        return list(result)
    finally:
        session.close()


def get_post_by_id(post_id: int) -> PostRow | None:
    """Fetch a single post by ID."""
    session = _get_session()
    try:
        return session.get(PostRow, post_id)
    finally:
        session.close()


def get_company_baseline(company: str, n: int = 10) -> float:
    """
    Compute the average engagement score of the last N posts for a company.

    This is the baseline used for engagement rate comparisons and alert thresholds.

    Args:
        company: Company name.
        n: Number of recent posts to average (default: 10).

    Returns:
        Average engagement score, or 0.0 if no posts exist.
    """
    session = _get_session()
    try:
        # Get last N engagement scores for this company
        query = (
            select(PostRow.engagement_score)
            .where(PostRow.company == company)
            .order_by(PostRow.timestamp.desc())
            .limit(n)
        )
        scores = session.execute(query).scalars().all()

        if not scores:
            return 0.0

        return sum(scores) / len(scores)
    finally:
        session.close()


def get_post_count(company: str | None = None) -> int:
    """Get total number of stored posts."""
    session = _get_session()
    try:
        query = select(func.count(PostRow.id))
        if company:
            query = query.where(PostRow.company == company)
        return session.execute(query).scalar_one()
    finally:
        session.close()


def get_stored_companies() -> list[str]:
    """Get list of all companies with stored posts."""
    session = _get_session()
    try:
        query = select(PostRow.company).distinct().order_by(PostRow.company)
        return list(session.execute(query).scalars().all())
    finally:
        session.close()


# ── Analysis Storage ─────────────────────────────────────────────────────────


def store_analysis(post_id: int, analysis: dict[str, Any]) -> AnalysisRow:
    """
    Store an LLM-generated analysis for a post.

    If an analysis already exists for this post, it is updated.

    Args:
        post_id: ID of the post this analysis belongs to.
        analysis: Dict with keys matching the 9-section output format.

    Returns:
        The created or updated AnalysisRow.
    """
    session = _get_session()
    try:
        # Check for existing analysis
        existing = session.execute(
            select(AnalysisRow).where(AnalysisRow.post_id == post_id)
        ).scalar_one_or_none()

        if existing:
            # Update existing analysis
            existing.executive_snapshot = analysis.get("executive_snapshot", "")
            existing.content_classification = analysis.get("content_classification", "")
            existing.strategic_intent = analysis.get("strategic_intent", "")
            existing.engagement_analysis = analysis.get("engagement_analysis", "")
            existing.creative_breakdown = analysis.get("creative_breakdown", "")
            existing.competitive_insight = analysis.get("competitive_insight", "")
            existing.recommended_action = analysis.get("recommended_action", "")
            existing.alert_tag = analysis.get("alert_tag", "LOW")
            existing.trend_signal = analysis.get("trend_signal", "")
            existing.raw_analysis_json = json.dumps(analysis)
            existing.analyzed_at = datetime.now(timezone.utc)
            session.commit()
            logger.info(f"Updated analysis for post {post_id}")
            return existing
        else:
            # Create new analysis
            row = AnalysisRow(
                post_id=post_id,
                executive_snapshot=analysis.get("executive_snapshot", ""),
                content_classification=analysis.get("content_classification", ""),
                strategic_intent=analysis.get("strategic_intent", ""),
                engagement_analysis=analysis.get("engagement_analysis", ""),
                creative_breakdown=analysis.get("creative_breakdown", ""),
                competitive_insight=analysis.get("competitive_insight", ""),
                recommended_action=analysis.get("recommended_action", ""),
                alert_tag=analysis.get("alert_tag", "LOW"),
                trend_signal=analysis.get("trend_signal", ""),
                raw_analysis_json=json.dumps(analysis),
            )
            session.add(row)
            session.commit()
            logger.info(f"Stored new analysis for post {post_id}")
            return row

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to store analysis for post {post_id}: {e}")
        raise
    finally:
        session.close()


def get_analysis_for_post(post_id: int) -> AnalysisRow | None:
    """Fetch the analysis for a specific post."""
    session = _get_session()
    try:
        return session.execute(
            select(AnalysisRow).where(AnalysisRow.post_id == post_id)
        ).scalar_one_or_none()
    finally:
        session.close()


def get_all_analyses() -> dict[int, AnalysisRow]:
    """
    Fetch ALL analysis rows in a single query and return them keyed by post_id.

    Use this in the dashboard instead of calling get_analysis_for_post() in a loop.
    Eliminates the N+1 query problem (30 posts → 30 round-trips → 1 round-trip).

    Returns:
        Dict mapping post_id → AnalysisRow.
    """
    session = _get_session()
    try:
        rows = session.execute(select(AnalysisRow)).scalars().all()
        return {row.post_id: row for row in rows}
    finally:
        session.close()


def get_posts_without_analysis(company: str | None = None) -> list[PostRow]:
    """
    Find posts that don't have an LLM analysis yet.

    Useful for batch-analyzing new posts.
    """
    session = _get_session()
    try:
        # Left outer join to find posts without analysis
        query = (
            select(PostRow)
            .outerjoin(AnalysisRow, PostRow.id == AnalysisRow.post_id)
            .where(AnalysisRow.id.is_(None))
        )

        if company:
            query = query.where(PostRow.company == company)

        query = query.order_by(PostRow.timestamp.desc())
        return list(session.execute(query).scalars().all())
    finally:
        session.close()
