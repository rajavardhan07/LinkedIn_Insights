"""
High-level post fetcher — the main service for Phase 1.

Orchestrates: company resolution → post fetch → normalization.
This is the function your spec requires: fetch_linkedin_posts(company_name)
"""

from datetime import datetime, timezone
from typing import Any

from config.companies import get_all_company_names
from config.settings import DEFAULT_POST_COUNT
from models.post import PostData, ReactionBreakdown, MediaItem
from services.company_resolver import resolve_company_id
from services.linkdapi_client import LinkdAPIClient
from utils.logger import get_logger

logger = get_logger(__name__)


async def fetch_linkedin_posts(
    client: LinkdAPIClient,
    company_name: str,
    count: int = DEFAULT_POST_COUNT,
) -> list[PostData]:
    """
    Fetch and normalize recent LinkedIn posts for a company.

    This is the primary entry point for Phase 1.
    No raw API data passes through — everything is validated via Pydantic.

    Args:
        client: Initialized LinkdAPIClient.
        company_name: Display name (e.g., "Vanguard India").
        count: Number of posts to fetch (default: 10).

    Returns:
        List of normalized PostData objects.
    """
    logger.info(f"── Fetching posts for '{company_name}' (count={count}) ──")

    # Step 1: Resolve company ID
    company_id = await resolve_company_id(client, company_name)
    if company_id is None:
        logger.error(f"Skipping '{company_name}' — could not resolve company ID")
        return []

    # Step 2: Fetch raw posts from API
    raw_posts = await _fetch_raw_posts(client, company_id, count)
    if not raw_posts:
        logger.warning(f"No posts returned for '{company_name}' (ID: {company_id})")
        return []

    # Step 3: Normalize each post
    normalized = []
    for i, raw in enumerate(raw_posts[:count]):
        try:
            post = _normalize_post(raw, company_name)
            normalized.append(post)
        except Exception as e:
            logger.warning(
                f"Failed to normalize post {i + 1} for '{company_name}': {e}"
            )
            continue

    logger.info(
        f"✓ Fetched {len(normalized)} posts for '{company_name}' "
        f"(total engagement: {sum(p.engagement_score for p in normalized)})"
    )
    return normalized


async def fetch_all_companies(
    client: LinkdAPIClient,
    count: int = DEFAULT_POST_COUNT,
) -> dict[str, list[PostData]]:
    """
    Fetch posts for ALL registered companies.

    Returns:
        Dict mapping company name → list of PostData.
    """
    all_results: dict[str, list[PostData]] = {}

    for company_name in get_all_company_names():
        posts = await fetch_linkedin_posts(client, company_name, count)
        all_results[company_name] = posts

    total_posts = sum(len(posts) for posts in all_results.values())
    logger.info(f"══ Completed: {total_posts} posts across {len(all_results)} companies ══")
    return all_results


# ── Private Helpers ─────────────────────────────────────────────────────────


async def _fetch_raw_posts(
    client: LinkdAPIClient,
    company_id: int,
    count: int,
) -> list[dict]:
    """Fetch raw post data from LinkdAPI."""
    try:
        response = await client.get(
            "/companies/company/posts",
            params={"id": company_id, "start": 0},
        )

        if isinstance(response, dict):
            data = response.get("data")

            # Handle: { "data": [ ... ] }
            if isinstance(data, list):
                return data[:count]

            # Handle: { "data": { "posts": [ ... ] } }
            if isinstance(data, dict):
                posts = data.get("posts") or data.get("items") or data.get("elements")
                if isinstance(posts, list):
                    return posts[:count]

        logger.warning(f"Unexpected response structure for company {company_id}")
        return []

    except Exception as e:
        logger.error(f"Failed to fetch posts for company {company_id}: {e}")
        return []


def _normalize_post(raw: dict[str, Any], company_name: str) -> PostData:
    """
    Transform a raw LinkdAPI post response into a PostData model.

    Extracts ALL available data from the API response including:
    - Core: text, timestamp, engagement
    - Identity: post URL, URN
    - Engagement detail: reaction breakdown (LIKE, PRAISE, EMPATHY, etc.)
    - Media: URLs, types, descriptions for all attachments
    - Metadata: follower count, is_repost, is_edited, author info
    """
    # ── Text Content ──────────────────────────────────────────────────────
    text = (
        raw.get("text")
        or raw.get("commentary")
        or raw.get("content")
        or raw.get("body")
        or ""
    )
    if isinstance(text, dict):
        text = text.get("text", "")

    # ── Timestamp ─────────────────────────────────────────────────────────
    timestamp = _parse_timestamp(raw)

    # ── Engagement Metrics ────────────────────────────────────────────────
    likes, comments, shares = _extract_metrics(raw)

    # ── Reaction Breakdown ────────────────────────────────────────────────
    reactions = _extract_reaction_breakdown(raw)

    # ── Post Type ─────────────────────────────────────────────────────────
    post_type = _detect_post_type(raw)

    # ── Hashtags ──────────────────────────────────────────────────────────
    hashtags = raw.get("hashtags") or raw.get("tags") or []
    if not hashtags and text:
        hashtags = PostData.extract_hashtags(text)

    # ── Media ─────────────────────────────────────────────────────────────
    media_desc = _extract_media_description(raw)
    media_items = _extract_media_items(raw)
    media_urls = [item.url for item in media_items if item.url]

    # ── Post Identity ─────────────────────────────────────────────────────
    post_url = raw.get("url") or ""
    post_urn = raw.get("urn") or ""

    # ── Author Info ───────────────────────────────────────────────────────
    author = raw.get("author") or {}
    author_name = author.get("name", "") if isinstance(author, dict) else ""
    author_urn = author.get("urn", "") if isinstance(author, dict) else ""

    # ── Follower Count (from author headline like "7,014 followers") ──────
    follower_count = _extract_follower_count(author)

    # ── Flags ─────────────────────────────────────────────────────────────
    is_repost = raw.get("resharedPostContent") is not None
    is_edited = raw.get("edited", False)

    return PostData(
        company=company_name,
        text=text,
        post_type=post_type,
        timestamp=timestamp,
        likes=likes,
        comments=comments,
        shares=shares,
        reactions=reactions,
        hashtags=hashtags,
        media_description=media_desc,
        post_url=post_url,
        post_urn=post_urn,
        media_urls=media_urls,
        media_items=media_items,
        follower_count=follower_count,
        is_repost=is_repost,
        is_edited=is_edited,
        author_name=author_name,
        author_urn=author_urn,
    )


def _parse_timestamp(raw: dict) -> datetime:
    """Extract and parse timestamp from various response formats."""
    # LinkdAPI actual format: { "postedAt": { "timestamp": 1775359861191, "fullDate": "..." } }
    posted_at = raw.get("postedAt")
    if isinstance(posted_at, dict):
        ts = posted_at.get("timestamp")
        if ts is not None:
            if isinstance(ts, (int, float)):
                if ts > 1e12:  # milliseconds
                    ts = ts / 1000
                return datetime.fromtimestamp(ts, tz=timezone.utc)

    # Fallback: direct timestamp field
    ts = (
        raw.get("timestamp")
        or raw.get("created_at")
        or raw.get("publishedAt")
        or raw.get("createdAt")
    )

    if ts is None:
        return datetime.now(timezone.utc)

    # Handle epoch milliseconds
    if isinstance(ts, (int, float)):
        if ts > 1e12:
            ts = ts / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)

    # Handle ISO string
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            pass

    return datetime.now(timezone.utc)


def _extract_metrics(raw: dict) -> tuple[int, int, int]:
    """Extract likes, comments, shares from various response formats."""

    # LinkdAPI actual format:
    # { "engagements": { "totalReactions": 302, "commentsCount": 15, "repostsCount": 0 } }
    engagements = raw.get("engagements")
    if isinstance(engagements, dict):
        likes = engagements.get("totalReactions", 0)
        comments = engagements.get("commentsCount", 0)
        shares = engagements.get("repostsCount", 0)
        return _safe_int(likes), _safe_int(comments), _safe_int(shares)

    # Fallback: { "metrics": { "likes": N, ... } }
    metrics = raw.get("metrics") or raw.get("socialDetail") or {}
    if isinstance(metrics, dict):
        likes = metrics.get("likes") or metrics.get("numLikes") or metrics.get("totalReactionCount") or 0
        comments = metrics.get("comments") or metrics.get("numComments") or metrics.get("totalCommentCount") or 0
        shares = metrics.get("shares") or metrics.get("numShares") or metrics.get("totalShareCount") or 0
        return _safe_int(likes), _safe_int(comments), _safe_int(shares)

    # Fallback: flat fields
    likes = raw.get("likes") or raw.get("numLikes") or raw.get("likeCount") or 0
    comments = raw.get("comments") or raw.get("numComments") or raw.get("commentCount") or 0
    shares = raw.get("shares") or raw.get("numShares") or raw.get("shareCount") or 0
    return _safe_int(likes), _safe_int(comments), _safe_int(shares)


def _detect_post_type(raw: dict) -> str:
    """Determine content type from raw post data."""
    # LinkdAPI actual format: { "mediaContent": [ { "type": "image", ... } ] }
    media_content = raw.get("mediaContent")
    if isinstance(media_content, list) and media_content:
        first_media = media_content[0]
        if isinstance(first_media, dict):
            mtype = first_media.get("type", "").lower()
            if mtype in ("image", "video", "document", "article", "poll"):
                return mtype

    # Explicit type field
    ptype = raw.get("type") or raw.get("postType") or raw.get("contentType")
    if ptype:
        return str(ptype).lower()

    # Check for reshared content
    if raw.get("resharedPostContent"):
        return "repost"

    # Infer from content structure
    if raw.get("video") or raw.get("videoUrl"):
        return "video"
    if raw.get("image") or raw.get("imageUrl") or raw.get("images"):
        return "image"
    if raw.get("article") or raw.get("articleUrl"):
        return "article"
    if raw.get("document") or raw.get("documentUrl"):
        return "document"
    if raw.get("poll"):
        return "poll"

    return "text"


def _extract_media_description(raw: dict) -> str:
    """Extract description of attached media."""
    # LinkdAPI actual format: { "mediaContent": [ { "type": "image", "url": "..." } ] }
    media_content = raw.get("mediaContent")
    if isinstance(media_content, list) and media_content:
        parts = []
        for item in media_content:
            if isinstance(item, dict):
                mtype = item.get("type", "media")
                desc = item.get("description") or item.get("altText", "")
                if desc:
                    parts.append(f"{mtype}: {desc}")
                else:
                    parts.append(mtype)
        if parts:
            return "; ".join(parts)

    # Fallback: dedicated fields
    desc = (
        raw.get("media_description")
        or raw.get("mediaDescription")
        or raw.get("altText")
        or raw.get("description")
    )
    if desc and isinstance(desc, str):
        return desc.strip()

    # Fallback: nested media objects
    media = raw.get("media") or raw.get("images") or raw.get("image")
    if isinstance(media, dict):
        return (media.get("description") or media.get("altText") or "").strip()
    if isinstance(media, list) and media:
        first = media[0]
        if isinstance(first, dict):
            return (first.get("description") or first.get("altText") or "").strip()

    return ""


def _extract_reaction_breakdown(raw: dict) -> ReactionBreakdown:
    """Extract detailed reaction counts by type from engagements.reactions."""
    engagements = raw.get("engagements", {})
    if not isinstance(engagements, dict):
        return ReactionBreakdown()

    reactions_list = engagements.get("reactions", [])
    if not isinstance(reactions_list, list):
        return ReactionBreakdown()

    # Map LinkdAPI reaction types to our model fields
    type_map = {
        "LIKE": "like",
        "PRAISE": "praise",
        "EMPATHY": "empathy",
        "INTEREST": "interest",
        "APPRECIATION": "appreciation",
        "ENTERTAINMENT": "entertainment",
    }

    counts = {}
    for reaction in reactions_list:
        if isinstance(reaction, dict):
            rtype = reaction.get("reactionType", "").upper()
            rcount = reaction.get("reactionCount", 0)
            field = type_map.get(rtype)
            if field:
                counts[field] = _safe_int(rcount)

    return ReactionBreakdown(**counts)


def _extract_media_items(raw: dict) -> list[MediaItem]:
    """Extract structured media items with type, URL, and description."""
    media_content = raw.get("mediaContent")
    if not isinstance(media_content, list):
        return []

    items = []
    for media in media_content:
        if not isinstance(media, dict):
            continue
        items.append(MediaItem(
            type=media.get("type", "unknown"),
            url=media.get("url", ""),
            description=media.get("description") or media.get("altText", ""),
        ))

    return items


def _extract_follower_count(author: dict) -> int:
    """Extract follower count from author headline (e.g., '7,014 followers')."""
    if not isinstance(author, dict):
        return 0

    headline = author.get("headline", "")
    if not headline or "followers" not in headline.lower():
        return 0

    # Parse "7,014 followers" -> 7014
    import re
    match = re.search(r"([\d,]+)\s*followers?", headline, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1).replace(",", ""))
        except ValueError:
            pass

    return 0


def _safe_int(value: Any) -> int:
    """Safely convert to non-negative int."""
    try:
        return max(int(value), 0)
    except (ValueError, TypeError):
        return 0
