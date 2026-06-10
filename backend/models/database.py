"""
SQLAlchemy ORM models for the LinkedIn Analytics database.

Two tables:
  - posts: Stores all fetched LinkedIn posts with engagement metrics
  - analyses: Stores LLM-generated intelligence reports linked to posts

Uses SQLite by default — can switch to PostgreSQL by changing DATABASE_URL.
"""

import json
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    relationship,
    sessionmaker,
)

from config.settings import DATABASE_URL
from utils.logger import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""
    pass


class PostRow(Base):
    """
    Persistent storage for LinkedIn posts.

    Mirrors the PostData Pydantic model with database-friendly types.
    Deduplication is handled via unique constraint on post_urn.
    """

    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ── Core Fields ──────────────────────────────────────────────────────
    company = Column(String(255), nullable=False, index=True)
    text = Column(Text, default="")
    post_type = Column(String(50), default="text")
    timestamp = Column(DateTime(timezone=True), nullable=False)

    # ── Engagement Metrics ───────────────────────────────────────────────
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    engagement_score = Column(Integer, default=0)
    engagement_rate = Column(Float, default=0.0)

    # ── Reaction Breakdown (stored as JSON string) ───────────────────────
    reactions_json = Column(Text, default="{}")

    # ── Content Metadata ─────────────────────────────────────────────────
    hashtags_json = Column(Text, default="[]")
    media_description = Column(Text, default="")

    # ── Post Identity ────────────────────────────────────────────────────
    post_url = Column(String(512), default="")
    post_urn = Column(String(255), default="", unique=True)

    # ── Media (stored as JSON string) ────────────────────────────────────
    media_urls_json = Column(Text, default="[]")

    # ── Author / Company Metadata ────────────────────────────────────────
    follower_count = Column(Integer, default=0)
    is_repost = Column(Boolean, default=False)
    is_edited = Column(Boolean, default=False)
    author_name = Column(String(255), default="")

    # ── Timestamps ───────────────────────────────────────────────────────
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ────────────────────────────────────────────────────
    analyses = relationship("AnalysisRow", back_populates="post", cascade="all, delete-orphan")

    # ── Indexes ──────────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_company_timestamp", "company", "timestamp"),
    )

    # ── Helpers ──────────────────────────────────────────────────────────

    @property
    def hashtags(self) -> list[str]:
        """Deserialize hashtags from JSON."""
        try:
            return json.loads(self.hashtags_json or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    @property
    def media_urls(self) -> list[str]:
        """Deserialize media URLs from JSON."""
        try:
            return json.loads(self.media_urls_json or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    @property
    def reactions(self) -> dict:
        """Deserialize reactions from JSON."""
        try:
            return json.loads(self.reactions_json or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}

    def to_dict(self) -> dict:
        """Convert row to dict for downstream processing."""
        return {
            "id": self.id,
            "company": self.company,
            "text": self.text,
            "post_type": self.post_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else "",
            "likes": self.likes,
            "comments": self.comments,
            "shares": self.shares,
            "engagement_score": self.engagement_score,
            "engagement_rate": self.engagement_rate,
            "reactions": self.reactions,
            "hashtags": self.hashtags,
            "media_description": self.media_description,
            "post_url": self.post_url,
            "post_urn": self.post_urn,
            "media_urls": self.media_urls,
            "follower_count": self.follower_count,
            "is_repost": self.is_repost,
            "is_edited": self.is_edited,
            "author_name": self.author_name,
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }

    def __repr__(self) -> str:
        text_preview = (self.text or "")[:50]
        return f"<PostRow(id={self.id}, company='{self.company}', text='{text_preview}...')>"


class AnalysisRow(Base):
    """
    LLM-generated intelligence report for a post.

    Each post can have one analysis (one-to-one via post_id FK).
    Stores both structured fields and the raw JSON for flexibility.
    """

    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, unique=True)

    # ── 9-Section Intelligence Output ────────────────────────────────────
    executive_snapshot = Column(Text, default="")
    content_classification = Column(String(100), default="")
    strategic_intent = Column(Text, default="")
    engagement_analysis = Column(Text, default="")
    creative_breakdown = Column(Text, default="")
    competitive_insight = Column(Text, default="")
    recommended_action = Column(Text, default="")
    alert_tag = Column(String(50), default="LOW")
    trend_signal = Column(Text, default="")

    # ── Raw LLM Output ───────────────────────────────────────────────────
    raw_analysis_json = Column(Text, default="{}")

    # ── Timestamps ───────────────────────────────────────────────────────
    analyzed_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ────────────────────────────────────────────────────
    post = relationship("PostRow", back_populates="analyses")

    def to_dict(self) -> dict:
        """Convert analysis to dict."""
        return {
            "id": self.id,
            "post_id": self.post_id,
            "executive_snapshot": self.executive_snapshot,
            "content_classification": self.content_classification,
            "strategic_intent": self.strategic_intent,
            "engagement_analysis": self.engagement_analysis,
            "creative_breakdown": self.creative_breakdown,
            "competitive_insight": self.competitive_insight,
            "recommended_action": self.recommended_action,
            "alert_tag": self.alert_tag,
            "trend_signal": self.trend_signal,
            "analyzed_at": self.analyzed_at.isoformat() if self.analyzed_at else "",
        }

    def __repr__(self) -> str:
        return f"<AnalysisRow(id={self.id}, post_id={self.post_id}, alert='{self.alert_tag}')>"


# ── Engine & Session Factory ────────────────────────────────────────────────


def get_engine():
    """Create SQLAlchemy engine from config."""
    connect_args = {}
    if DATABASE_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(
        DATABASE_URL,
        echo=False,
        connect_args=connect_args,
    )
    return engine


def get_session_factory():
    """Create a session factory bound to the engine."""
    engine = get_engine()
    return sessionmaker(bind=engine)


def init_db():
    """Create all tables if they don't exist."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info(f"Database initialized: {DATABASE_URL}")
