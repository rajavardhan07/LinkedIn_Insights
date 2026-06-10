"""
Phase 3: Preprocessing + Metrics Engine

Prepares post data for LLM intelligence generation by:
  1. Cleaning text (remove noise, normalize)
  2. Computing engagement features (score, rate, baseline multiplier)
  3. Detecting content signals (hiring, innovation, culture, CSR, etc.)
  4. Producing an enriched post dict ready for the LLM prompt

Input:  PostData (Pydantic) or PostRow (SQLAlchemy)
Output: Enriched dict with original fields + computed features + signals
"""

import re
from typing import Any

from models.post import PostData
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Signal Keywords ──────────────────────────────────────────────────────────

SIGNAL_KEYWORDS: dict[str, list[str]] = {
    "hiring": [
        "hiring", "join us", "we're looking", "we are looking", "open roles",
        "career", "apply now", "job opening", "recruitment", "talent acquisition",
        "we're hiring", "join our team", "opportunity",
    ],
    "innovation": [
        "innovation", "artificial intelligence", " AI ", "launch", "first-ever",
        "breakthrough", "patent", "research", "technology", "digital transformation",
        "machine learning", "cloud", "platform", "framework", "lab",
    ],
    "culture": [
        "culture", "team", "celebration", "together", "values", "wellbeing",
        "wellness", "fun", "company day", "festival", "offsite", "team building",
        "engagement", "colleagues", "workplace",
    ],
    "csr": [
        "CSR", "community", "NGO", "sustainability", "volunteer", "impact",
        "carbon", "environment", "social responsibility", "green", "charitable",
        "nirmaan", "vocational",
    ],
    "leadership": [
        "CEO", "CTO", "CIO", "managing director", "general counsel",
        "leadership", "vision", "strategy", "keynote", "executive",
        "senior leader", "head of", "director",
    ],
    "awards": [
        "award", "recognition", "certified", "ranked", "top employer",
        "great place to work", "best company", "excellence", "honored",
        "achievement", "milestone",
    ],
    "dei": [
        "diversity", "inclusion", "equity", "women in", "international women",
        "IWD", "gender", "belonging", "empowerment", "equal opportunity",
    ],
}

# ── Content Classification Categories ────────────────────────────────────────

CLASSIFICATION_MAP: dict[str, str] = {
    "hiring": "Talent Hiring",
    "innovation": "Business / Capability Showcase",
    "culture": "Culture / Employee Stories",
    "csr": "CSR / Community",
    "leadership": "Leadership / Thought Leadership",
    "awards": "Awards / Recognition",
    "dei": "Employer Branding",
}


# ── Text Cleaning ────────────────────────────────────────────────────────────


def clean_text(text: str) -> str:
    """
    Clean LinkedIn post text for analysis.

    - Collapse excessive newlines
    - Normalize whitespace
    - Remove zero-width characters and Unicode noise
    - Preserve meaningful formatting
    """
    if not text:
        return ""

    # Remove zero-width characters
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)

    # Replace non-breaking spaces with regular spaces
    text = text.replace("\u00a0", " ")

    # Collapse 3+ consecutive newlines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Collapse multiple spaces into one
    text = re.sub(r" {2,}", " ", text)

    # Strip leading/trailing whitespace on each line
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    # Final trim
    return text.strip()


def extract_mentioned_people(text: str) -> list[str]:
    """Extract names of mentioned people from LinkedIn post text."""
    if not text:
        return []

    # LinkedIn mentions often appear as proper names (capitalized words in sequence)
    # Look for patterns like "Firstname Lastname" or "Firstname Lastname, Title"
    # This is a heuristic — not perfect but good enough for signal detection
    names = []

    # Common LinkedIn mention patterns
    patterns = [
        r"(?:welcome|welcoming|hosted by|joined by|led by|with)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text)
        names.extend(matches)

    return list(set(names))


# ── Content Signal Detection ─────────────────────────────────────────────────


def detect_content_signals(text: str) -> list[str]:
    """
    Detect content signal categories from post text.

    Returns:
        List of detected signal categories (e.g., ["culture", "leadership", "dei"]).
    """
    if not text:
        return []

    text_lower = text.lower()
    detected = []

    for category, keywords in SIGNAL_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                detected.append(category)
                break  # One match per category is enough

    return detected


def suggest_classification(signals: list[str], text: str) -> str:
    """
    Suggest a content classification based on detected signals.

    Priority order matters — if multiple signals detected, pick the most
    strategic one (hiring > innovation > leadership > dei > culture > csr > awards).
    """
    priority = ["hiring", "innovation", "leadership", "dei", "culture", "csr", "awards"]

    for signal in priority:
        if signal in signals:
            return CLASSIFICATION_MAP.get(signal, "Employer Branding")

    # Default fallback
    return "Employer Branding"


# ── Engagement Feature Engineering ───────────────────────────────────────────


def compute_engagement_features(
    likes: int,
    comments: int,
    shares: int,
    follower_count: int,
    baseline: float,
) -> dict[str, Any]:
    """
    Compute engagement metrics relative to a company baseline.

    Args:
        likes: Total reactions/likes.
        comments: Number of comments.
        shares: Number of reposts.
        follower_count: Company follower count.
        baseline: Average engagement score of last N posts.

    Returns:
        Dict of computed engagement features.
    """
    engagement_score = likes + comments + shares

    engagement_rate = 0.0
    if follower_count > 0:
        engagement_rate = (engagement_score / follower_count) * 100

    baseline_multiplier = 0.0
    if baseline > 0:
        baseline_multiplier = engagement_score / baseline

    return {
        "engagement_score": engagement_score,
        "engagement_rate_pct": round(engagement_rate, 2),
        "follower_count": follower_count,
        "baseline_avg": round(baseline, 1),
        "baseline_multiplier": round(baseline_multiplier, 2),
        "is_above_baseline": engagement_score > baseline,
        "is_high_performer": baseline_multiplier > 2.0,
        "performance_label": _engagement_label(baseline_multiplier),
    }


def _engagement_label(multiplier: float) -> str:
    """Human-readable label for engagement performance."""
    if multiplier >= 3.0:
        return "EXCEPTIONAL (3x+ baseline)"
    elif multiplier >= 2.0:
        return "HIGH (2x+ baseline)"
    elif multiplier >= 1.3:
        return "ABOVE AVERAGE (1.3x+ baseline)"
    elif multiplier >= 0.7:
        return "AVERAGE"
    elif multiplier > 0:
        return "BELOW AVERAGE"
    else:
        return "NO BASELINE"


# ── Post Enrichment (Main Pipeline Function) ─────────────────────────────────


def preprocess_post(
    post: PostData | dict,
    baseline: float = 0.0,
) -> dict[str, Any]:
    """
    Enrich a post with cleaned text, engagement features, and content signals.

    This is the main entry point for Phase 3. The output dict is designed to be
    passed directly to the LLM intelligence engine (Phase 4).

    Args:
        post: A PostData object or dict (from PostRow.to_dict()).
        baseline: Average engagement score for the company (from storage).

    Returns:
        Enriched dict ready for LLM prompt construction.
    """
    # Handle both PostData and dict inputs
    if isinstance(post, PostData):
        data = post.to_dict()
    elif isinstance(post, dict):
        data = dict(post)
    else:
        raise TypeError(f"Expected PostData or dict, got {type(post)}")

    # ── Clean Text ───────────────────────────────────────────────────────
    cleaned_text = clean_text(data.get("text", ""))
    data["cleaned_text"] = cleaned_text

    # ── Content Signals ──────────────────────────────────────────────────
    signals = detect_content_signals(cleaned_text)
    data["content_signals"] = signals
    data["suggested_classification"] = suggest_classification(signals, cleaned_text)

    # ── Engagement Features ──────────────────────────────────────────────
    engagement_features = compute_engagement_features(
        likes=data.get("likes", 0),
        comments=data.get("comments", 0),
        shares=data.get("shares", 0),
        follower_count=data.get("follower_count", 0),
        baseline=baseline,
    )
    data["engagement_features"] = engagement_features

    # ── Mentioned People ─────────────────────────────────────────────────
    data["mentioned_people"] = extract_mentioned_people(cleaned_text)

    # ── Post Age ─────────────────────────────────────────────────────────
    from datetime import datetime, timezone
    ts = data.get("timestamp")
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            ts = None
    if ts:
        # Ensure timezone-aware comparison
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        days_ago = (datetime.now(timezone.utc) - ts).days
        data["days_ago"] = days_ago
        data["recency_label"] = _recency_label(days_ago)
    else:
        data["days_ago"] = None
        data["recency_label"] = "unknown"

    logger.debug(
        f"Preprocessed post for {data.get('company')}: "
        f"signals={signals}, engagement={engagement_features['performance_label']}"
    )

    return data


def preprocess_batch(
    posts: list[PostData | dict],
    baseline: float = 0.0,
) -> list[dict[str, Any]]:
    """Preprocess a batch of posts."""
    return [preprocess_post(post, baseline) for post in posts]


def _recency_label(days: int) -> str:
    """Human-readable recency label."""
    if days <= 1:
        return "today"
    elif days <= 3:
        return "this week"
    elif days <= 7:
        return "last week"
    elif days <= 14:
        return "last 2 weeks"
    elif days <= 30:
        return "last month"
    else:
        return f"{days} days ago"
