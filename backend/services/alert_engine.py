"""
Phase 5: Alert Engine

Detects high-impact signals and assigns final alert priority tags.

Combines rule-based thresholds (deterministic) with LLM suggestions:
  - Rules take precedence over LLM for engagement-based alerts
  - LLM provides nuance for content-based alerts (campaigns, EVP shifts)

Alert Levels:
  HIGH PRIORITY — immediate action needed
  MEDIUM — track pattern, potential opportunity
  LOW — routine, no action required
"""

from typing import Any

from config.settings import (
    HIGH_ALERT_ENGAGEMENT_MULTIPLIER,
    MEDIUM_ALERT_ENGAGEMENT_MULTIPLIER,
)
from utils.logger import get_logger

logger = get_logger(__name__)


# ── High-Priority Signal Keywords ────────────────────────────────────────────

HIGH_SIGNAL_KEYWORDS = {
    "major_campaign": [
        "launch", "announcing", "introducing", "proud to announce",
        "first-ever", "new initiative", "unveil", "partnership",
    ],
    "hiring_surge": [
        "hiring spree", "100+ roles", "massive hiring", "recruitment drive",
        "join our team", "multiple openings", "we're hiring",
    ],
    "evp_shift": [
        "new vision", "rebranding", "new chapter", "transformation",
        "repositioning", "strategic shift", "new identity",
    ],
}


# ── Alert Engine ─────────────────────────────────────────────────────────────


def evaluate_alert(
    enriched_post: dict[str, Any],
    llm_alert_tag: str = "LOW",
) -> dict[str, Any]:
    """
    Determine the final alert tag for a post.

    Combines rule-based engagement thresholds with LLM suggestion.
    Rules take precedence for engagement-based alerts.

    Args:
        enriched_post: Dict from preprocessor.preprocess_post() with
                       engagement_features and content_signals.
        llm_alert_tag: The alert tag suggested by the LLM (Phase 4).

    Returns:
        Dict with:
        - alert_tag: "HIGH PRIORITY" | "MEDIUM" | "LOW"
        - alert_reasons: list of reasons that contributed to the tag
        - is_alert: bool (True if HIGH PRIORITY)
    """
    reasons = []
    eng = enriched_post.get("engagement_features", {})
    signals = enriched_post.get("content_signals", [])
    text = enriched_post.get("cleaned_text", enriched_post.get("text", ""))

    baseline_mult = eng.get("baseline_multiplier", 0)
    engagement_score = eng.get("engagement_score", 0)

    # ── Rule 1: Engagement > 2x baseline → HIGH ─────────────────────────
    if baseline_mult >= HIGH_ALERT_ENGAGEMENT_MULTIPLIER:
        reasons.append(
            f"Engagement {baseline_mult:.1f}x above baseline "
            f"(score: {engagement_score}, threshold: {HIGH_ALERT_ENGAGEMENT_MULTIPLIER}x)"
        )

    # ── Rule 2: High-priority content signals → HIGH ────────────────────
    high_content_signals = _detect_high_signals(text)
    if high_content_signals:
        reasons.append(
            f"High-priority signals detected: {', '.join(high_content_signals)}"
        )

    # ── Rule 3: Hiring signal + above-average engagement → HIGH ─────────
    if "hiring" in signals and baseline_mult >= MEDIUM_ALERT_ENGAGEMENT_MULTIPLIER:
        reasons.append(
            f"Hiring signal with above-average engagement ({baseline_mult:.1f}x baseline)"
        )

    # ── Rule 4: Engagement > 1.3x baseline → MEDIUM ────────────────────
    if baseline_mult >= MEDIUM_ALERT_ENGAGEMENT_MULTIPLIER:
        reasons.append(
            f"Engagement {baseline_mult:.1f}x above baseline (moderate alert threshold)"
        )

    # ── Rule 5: Multiple content signals → MEDIUM ───────────────────────
    if len(signals) >= 3:
        reasons.append(
            f"Multiple content themes detected ({len(signals)}): {', '.join(signals)}"
        )

    # ── Determine Final Tag ──────────────────────────────────────────────
    final_tag = _resolve_tag(reasons, llm_alert_tag, baseline_mult)

    result = {
        "alert_tag": final_tag,
        "alert_reasons": reasons,
        "is_alert": final_tag == "HIGH PRIORITY",
        "llm_suggested_tag": llm_alert_tag,
        "baseline_multiplier": baseline_mult,
    }

    if final_tag != "LOW":
        logger.info(
            f"🚨 Alert [{final_tag}] for {enriched_post.get('company', '?')}: "
            f"{'; '.join(reasons[:2])}"
        )

    return result


def _resolve_tag(
    reasons: list[str],
    llm_tag: str,
    baseline_mult: float,
) -> str:
    """
    Resolve the final alert tag from rule reasons and LLM suggestion.

    Priority: engagement rules > content rules > LLM suggestion.
    """
    # Check for HIGH signals
    has_high_engagement = baseline_mult >= HIGH_ALERT_ENGAGEMENT_MULTIPLIER
    has_high_content = any("High-priority signals" in r for r in reasons)
    has_hiring_alert = any("Hiring signal" in r for r in reasons)

    if has_high_engagement or has_high_content or has_hiring_alert:
        return "HIGH PRIORITY"

    # Check for MEDIUM signals
    has_medium_engagement = baseline_mult >= MEDIUM_ALERT_ENGAGEMENT_MULTIPLIER
    has_multiple_themes = any("Multiple content themes" in r for r in reasons)

    if has_medium_engagement or has_multiple_themes:
        return "MEDIUM"

    # Fall back to LLM suggestion (but don't escalate beyond MEDIUM)
    llm_upper = llm_tag.upper().strip()
    if "HIGH" in llm_upper:
        return "MEDIUM"  # LLM can suggest HIGH but rules cap it at MEDIUM
    if "MEDIUM" in llm_upper:
        return "MEDIUM"

    return "LOW"


def _detect_high_signals(text: str) -> list[str]:
    """Detect high-priority content signals from text."""
    if not text:
        return []

    text_lower = text.lower()
    detected = []

    for signal_type, keywords in HIGH_SIGNAL_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                detected.append(signal_type)
                break

    return detected


# ── Batch Alert Processing ───────────────────────────────────────────────────


def evaluate_batch_alerts(
    enriched_posts: list[dict[str, Any]],
    llm_tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Evaluate alerts for a batch of posts.

    Args:
        enriched_posts: List of preprocessed post dicts.
        llm_tags: Optional list of LLM-suggested tags (same order as posts).

    Returns:
        List of alert result dicts.
    """
    if llm_tags is None:
        llm_tags = ["LOW"] * len(enriched_posts)

    results = []
    for post, tag in zip(enriched_posts, llm_tags):
        result = evaluate_alert(post, tag)
        results.append(result)

    # Summary
    high_count = sum(1 for r in results if r["alert_tag"] == "HIGH PRIORITY")
    medium_count = sum(1 for r in results if r["alert_tag"] == "MEDIUM")
    low_count = sum(1 for r in results if r["alert_tag"] == "LOW")

    logger.info(
        f"Alert summary: {high_count} HIGH | {medium_count} MEDIUM | {low_count} LOW "
        f"(out of {len(results)} posts)"
    )

    return results


def get_alert_summary(alerts: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate a summary of alerts for dashboard display."""
    high = [a for a in alerts if a["alert_tag"] == "HIGH PRIORITY"]
    medium = [a for a in alerts if a["alert_tag"] == "MEDIUM"]

    return {
        "total_posts": len(alerts),
        "high_priority_count": len(high),
        "medium_count": len(medium),
        "low_count": len(alerts) - len(high) - len(medium),
        "high_priority_alerts": high,
        "requires_attention": len(high) > 0,
    }
