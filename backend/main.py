"""
LinkedIn Analytics -- Phase 1: Data Fetch

Entry point for fetching and displaying LinkedIn company posts.

Usage:
    # Fetch posts for all companies (live API)
    python main.py

    # Fetch for a single company
    python main.py --company "Vanguard India"

    # Use mock data (no API calls)
    python main.py --mock

    # Control post count
    python main.py --count 5
"""

import os
import sys

# Fix Windows console encoding for unicode output
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from config.companies import get_all_company_names, COMPANY_REGISTRY
from config.settings import validate_config
from models.post import PostData
from services.linkdapi_client import LinkdAPIClient
from services.post_fetcher import fetch_linkedin_posts, fetch_all_companies
from utils.logger import get_logger

logger = get_logger("main")


# ── Mock Mode ─────────────────────────────────────────────────────────────────

def load_mock_data(company_name: str) -> list[PostData]:
    """Load posts from mock JSON files for development/testing."""
    mock_file = Path(__file__).parent / "tests" / "mock_responses" / "company_posts.json"

    if not mock_file.exists():
        logger.error(f"Mock file not found: {mock_file}")
        return []

    with open(mock_file, "r", encoding="utf-8") as f:
        mock = json.load(f)

    raw_posts = mock.get("data", [])
    normalized = []

    for raw in raw_posts:
        text = raw.get("text", "")
        timestamp_ms = raw.get("timestamp", 0)
        timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        metrics = raw.get("metrics", {})
        hashtags = raw.get("hashtags") or PostData.extract_hashtags(text)

        post = PostData(
            company=company_name,
            text=text,
            post_type=raw.get("type", "text"),
            timestamp=timestamp,
            likes=metrics.get("likes", 0),
            comments=metrics.get("comments", 0),
            shares=metrics.get("shares", 0),
            hashtags=hashtags,
            media_description=_get_mock_media_desc(raw),
        )
        normalized.append(post)

    return normalized


def _get_mock_media_desc(raw: dict) -> str:
    """Extract media description from mock data."""
    for field in ["images", "video", "document"]:
        media = raw.get(field)
        if isinstance(media, list) and media:
            return media[0].get("altText", "") or media[0].get("description", "")
        if isinstance(media, dict):
            return media.get("description", "") or media.get("altText", "")
    return ""


# ── Display ───────────────────────────────────────────────────────────────────

def display_results(results: dict[str, list[PostData]]) -> None:
    """Pretty-print fetched results to console."""
    print("\n" + "=" * 80)
    print("  📊  LINKEDIN ANALYTICS — FETCH RESULTS")
    print("=" * 80)

    for company, posts in results.items():
        follower_info = ""
        if posts and posts[0].follower_count > 0:
            follower_info = f" | {posts[0].follower_count:,} followers"

        print(f"\n{'─' * 70}")
        print(f"  🏢  {company} ({len(posts)} posts{follower_info})")
        print(f"{'─' * 70}")

        if not posts:
            print("     ⚠  No posts found")
            continue

        for i, post in enumerate(posts, 1):
            # Truncate text for display
            text_preview = post.text[:120] + "..." if len(post.text) > 120 else post.text
            text_preview = text_preview.replace("\n", " ")

            # Post header with flags
            flags = []
            if post.is_repost:
                flags.append("REPOST")
            if post.is_edited:
                flags.append("EDITED")
            flag_str = f" [{', '.join(flags)}]" if flags else ""

            print(f"\n  [{i}] {post.timestamp.strftime('%Y-%m-%d')} | {post.post_type.upper()}{flag_str}")
            print(f"      {text_preview}")

            # Engagement line
            eng_parts = [
                f"👍 {post.likes}",
                f"💬 {post.comments}",
                f"🔄 {post.shares}",
            ]
            print(f"      {' '.join(eng_parts)}  │  Score: {post.engagement_score}", end="")
            if post.follower_count > 0:
                print(f"  │  Rate: {post.engagement_rate:.1f}%", end="")
            print()

            # Reaction breakdown (if available)
            r = post.reactions
            reaction_parts = []
            if r.like > 0: reaction_parts.append(f"Like:{r.like}")
            if r.praise > 0: reaction_parts.append(f"Clap:{r.praise}")
            if r.empathy > 0: reaction_parts.append(f"Heart:{r.empathy}")
            if r.interest > 0: reaction_parts.append(f"Insightful:{r.interest}")
            if r.appreciation > 0: reaction_parts.append(f"Support:{r.appreciation}")
            if r.entertainment > 0: reaction_parts.append(f"Funny:{r.entertainment}")
            if reaction_parts:
                print(f"      ♻️  {' | '.join(reaction_parts)}")

            # Media info
            if post.media_urls:
                print(f"      📎 {len(post.media_urls)} media file(s): {post.media_description}")

            # Hashtags
            if post.hashtags:
                print(f"      🏷️  #{' #'.join(post.hashtags[:5])}")

        # Summary stats
        total_engagement = sum(p.engagement_score for p in posts)
        avg_engagement = total_engagement // len(posts) if posts else 0
        media_posts = sum(1 for p in posts if p.has_media)
        repost_count = sum(1 for p in posts if p.is_repost)

        print(f"\n  📈 Total Engagement: {total_engagement:,}  |  Avg: {avg_engagement:,}/post")
        print(f"  📎 Posts with media: {media_posts}/{len(posts)}  |  Reposts: {repost_count}")

    print(f"\n{'=' * 80}")
    print(f"  ✅ Fetch complete at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 80}\n")


def export_json(results: dict[str, list[PostData]], output_file: str = "output.json") -> None:
    """Export results to JSON file."""
    output = {}
    for company, posts in results.items():
        output[company] = [post.to_dict() for post in posts]

    out_path = Path(__file__).parent / output_file
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info(f"Results exported to {out_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def run_live(company: str | None, count: int) -> dict[str, list[PostData]]:
    """Fetch posts from live LinkdAPI."""
    validate_config()

    async with LinkdAPIClient() as client:
        if company:
            posts = await fetch_linkedin_posts(client, company, count)
            return {company: posts}
        else:
            return await fetch_all_companies(client, count)


def run_mock(company: str | None, count: int) -> dict[str, list[PostData]]:
    """Fetch posts from mock data."""
    if company:
        companies = [company]
    else:
        companies = get_all_company_names()

    results = {}
    for name in companies:
        posts = load_mock_data(name)[:count]
        results[name] = posts

    return results


def main():
    parser = argparse.ArgumentParser(
        description="LinkedIn Analytics — Fetch company posts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--company",
        type=str,
        help="Fetch posts for a specific company (default: all)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of posts per company (default: 5)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock data instead of live API",
    )
    parser.add_argument(
        "--export",
        type=str,
        help="Export results to JSON file (e.g., --export output.json)",
    )
    parser.add_argument(
        "--store",
        action="store_true",
        help="Store fetched posts to SQLite database",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run full pipeline: store + preprocess + LLM analyze + alert",
    )

    args = parser.parse_args()

    # --analyze implies --store
    if args.analyze:
        args.store = True

    # Validate company name if provided
    if args.company and args.company not in COMPANY_REGISTRY:
        print(f"\n❌ Unknown company: '{args.company}'")
        print(f"   Available: {', '.join(get_all_company_names())}\n")
        sys.exit(1)

    # Fetch
    if args.mock:
        logger.info("Running in MOCK mode (no API calls)")
        results = run_mock(args.company, args.count)
    else:
        logger.info("Running in LIVE mode (using LinkdAPI)")
        results = asyncio.run(run_live(args.company, args.count))

    # Display
    display_results(results)

    # Store to database
    if args.store:
        from services.storage import init_db, store_posts

        init_db()

        # Flatten all posts into a single list
        all_posts = []
        for company_posts in results.values():
            all_posts.extend(company_posts)

        new_count = store_posts(all_posts)
        print(f"\n  💾 Database: stored {new_count} new posts ({len(all_posts) - new_count} duplicates skipped)")

    # Analyze (full pipeline)
    if args.analyze:
        from services.storage import get_all_posts, get_company_baseline, store_analysis, get_analysis_for_post
        from services.preprocessor import preprocess_post
        from services.intelligence import analyze_post
        from services.alert_engine import evaluate_alert

        print(f"\n  🧠 Running intelligence analysis...")

        for company, posts_list in results.items():
            baseline = get_company_baseline(company)
            stored_posts = get_all_posts(company)

            # Only analyze posts that don't have analysis yet
            for post_row in stored_posts[:len(posts_list)]:
                existing = get_analysis_for_post(post_row.id)
                if existing:
                    continue

                enriched = preprocess_post(post_row.to_dict(), baseline)
                analysis = asyncio.run(analyze_post(enriched))
                alert = evaluate_alert(enriched, analysis.get("alert_tag", "LOW"))
                analysis["alert_tag"] = alert["alert_tag"]

                store_analysis(post_row.id, analysis)

                tag_emoji = "🔴" if alert["alert_tag"] == "HIGH PRIORITY" else "🟡" if alert["alert_tag"] == "MEDIUM" else "🟢"
                print(f"     {tag_emoji} [{alert['alert_tag']}] {post_row.text[:60].replace(chr(10), ' ')}...")

        print(f"\n  ✅ Analysis complete!")

    # Export
    if args.export:
        export_json(results, args.export)


if __name__ == "__main__":
    main()
