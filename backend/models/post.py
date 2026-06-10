"""
Pydantic models for normalized LinkedIn post data.

This is the ONLY schema that leaves Phase 1 — no raw API data downstream.
"""

from datetime import datetime
from pydantic import BaseModel, Field, field_validator
import re


class ReactionBreakdown(BaseModel):
    """Detailed reaction counts by type."""

    like: int = Field(default=0, ge=0)
    praise: int = Field(default=0, ge=0, description="Clap reaction")
    empathy: int = Field(default=0, ge=0, description="Heart reaction")
    interest: int = Field(default=0, ge=0, description="Insightful reaction")
    appreciation: int = Field(default=0, ge=0, description="Support reaction")
    entertainment: int = Field(default=0, ge=0, description="Funny reaction")

    @field_validator("*", mode="before")
    @classmethod
    def ensure_non_negative(cls, v) -> int:
        if v is None:
            return 0
        try:
            return max(int(v), 0)
        except (ValueError, TypeError):
            return 0


class MediaItem(BaseModel):
    """A single media attachment (image, video, document)."""

    type: str = Field(default="unknown", description="image, video, document")
    url: str = Field(default="", description="Direct CDN download URL")
    description: str = Field(default="", description="Alt text or media description")


class PostData(BaseModel):
    """
    Normalized LinkedIn post record.
    This schema is the contract between Phase 1 (fetch) and Phase 2+ (storage/analysis).
    """

    # ── Core Fields ───────────────────────────────────────────────────────
    company: str = Field(..., description="Display name of the company")
    text: str = Field(default="", description="Post body text")
    post_type: str = Field(
        default="text",
        description="Content type: text, image, video, article, document, poll, repost",
    )
    timestamp: datetime = Field(
        ..., description="When the post was published"
    )

    # ── Engagement Metrics ────────────────────────────────────────────────
    likes: int = Field(default=0, ge=0, description="Total reactions (all types)")
    comments: int = Field(default=0, ge=0, description="Number of comments")
    shares: int = Field(default=0, ge=0, description="Number of reposts")
    reactions: ReactionBreakdown = Field(
        default_factory=ReactionBreakdown,
        description="Breakdown of reactions by type (LIKE, PRAISE, EMPATHY, etc.)",
    )

    # ── Content Metadata ──────────────────────────────────────────────────
    hashtags: list[str] = Field(
        default_factory=list, description="Extracted hashtags"
    )
    media_description: str = Field(
        default="", description="Summary description of attached media"
    )

    # ── New Fields (Phase 1 Enhancement) ──────────────────────────────────
    post_url: str = Field(
        default="", description="Direct LinkedIn URL to the post"
    )
    post_urn: str = Field(
        default="", description="LinkedIn unique identifier (urn:li:activity:...)"
    )
    media_urls: list[str] = Field(
        default_factory=list,
        description="Direct CDN URLs for all attached images/videos/docs",
    )
    media_items: list[MediaItem] = Field(
        default_factory=list,
        description="Detailed media attachments with type and URL",
    )
    follower_count: int = Field(
        default=0, ge=0, description="Company follower count at time of fetch"
    )
    is_repost: bool = Field(
        default=False, description="Whether this is a reshared post"
    )
    is_edited: bool = Field(
        default=False, description="Whether the post was edited after publishing"
    )
    author_name: str = Field(
        default="", description="Author display name"
    )
    author_urn: str = Field(
        default="", description="Author's LinkedIn URN"
    )

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("text", "media_description", "post_url", "post_urn",
                     "author_name", "author_urn", mode="before")
    @classmethod
    def clean_text(cls, v: str | None) -> str:
        """Strip whitespace and handle null."""
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("hashtags", mode="before")
    @classmethod
    def normalize_hashtags(cls, v: list | None) -> list[str]:
        """Ensure lowercase, deduplicated hashtags."""
        if v is None:
            return []
        if isinstance(v, list):
            return list(dict.fromkeys(tag.lower().strip("#").strip() for tag in v if tag))
        return []

    @field_validator("post_type", mode="before")
    @classmethod
    def normalize_post_type(cls, v: str | None) -> str:
        """Map raw API types to our standard set."""
        if v is None:
            return "text"
        mapping = {
            "image": "image",
            "photo": "image",
            "video": "video",
            "article": "article",
            "document": "document",
            "poll": "poll",
            "celebration": "text",
            "native_document": "document",
            "repost": "repost",
        }
        return mapping.get(v.lower().strip(), "text")

    @field_validator("likes", "comments", "shares", "follower_count", mode="before")
    @classmethod
    def ensure_non_negative_int(cls, v) -> int:
        """Handle null or negative values."""
        if v is None:
            return 0
        try:
            val = int(v)
            return max(val, 0)
        except (ValueError, TypeError):
            return 0

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def extract_hashtags(text: str) -> list[str]:
        """Extract hashtags from post text."""
        if not text:
            return []
        return list(dict.fromkeys(
            tag.lower() for tag in re.findall(r"#(\w+)", text)
        ))

    @property
    def engagement_score(self) -> int:
        """Total engagement = likes + comments + shares."""
        return self.likes + self.comments + self.shares

    @property
    def engagement_rate(self) -> float:
        """Engagement rate as percentage of followers."""
        if self.follower_count == 0:
            return 0.0
        return (self.engagement_score / self.follower_count) * 100

    @property
    def has_media(self) -> bool:
        """Whether the post has any media attachments."""
        return len(self.media_urls) > 0

    @property
    def media_count(self) -> int:
        """Number of media attachments."""
        return len(self.media_urls)

    def to_dict(self) -> dict:
        """Serialize to dict with ISO timestamp."""
        data = self.model_dump()
        data["timestamp"] = self.timestamp.isoformat()
        # Add computed properties
        data["engagement_score"] = self.engagement_score
        data["engagement_rate"] = round(self.engagement_rate, 2)
        data["has_media"] = self.has_media
        data["media_count"] = self.media_count
        return data
