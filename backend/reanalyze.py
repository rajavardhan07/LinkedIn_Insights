"""
reanalyze.py — Force re-analyze posts with missing / fallback data.

Usage:
    # Re-analyze only posts with failed/empty analysis (safe default)
    python reanalyze.py

    # Re-analyze ALL posts for a specific company
    python reanalyze.py --company "Lloyds Technology Centre India"

    # Re-analyze every single post in the DB (full refresh)
    python reanalyze.py --all

    # Preview which posts would be re-analyzed (dry run)
    python reanalyze.py --dry-run
"""

import sys, os

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import argparse
import asyncio
from sqlalchemy import select, delete

from models.database import get_session_factory, init_db, AnalysisRow, PostRow
from services.intelligence import analyze_post, get_fallback_analysis
from services.preprocessor import preprocess_post
from services.alert_engine import evaluate_alert
from services.storage import (
    init_db as storage_init_db,
    get_company_baseline,
    store_analysis,
    get_analysis_for_post,
)
from utils.logger import get_logger

logger = get_logger("reanalyze")

_FALLBACK_SNAPSHOTS = {
    "Analysis failed or API key missing.",
    "Analysis failed",
    "",
}

_FALLBACK_INTENTS = {"N/A", "", None}


def _is_fallback(analysis) -> bool:
    """Return True if this analysis is a known fallback / failed result."""
    if analysis is None:
        return True
    snap = (analysis.executive_snapshot or "").strip()
    intent = (analysis.strategic_intent or "").strip()
    if snap in _FALLBACK_SNAPSHOTS or snap.startswith("Analysis failed"):
        return True
    if intent in _FALLBACK_INTENTS:
        return True
    return False


def collect_targets(company: str | None, force_all: bool) -> list[PostRow]:
    """Return the list of PostRow objects that need re-analysis."""
    factory = get_session_factory()
    session = factory()
    try:
        query = select(PostRow)
        if company:
            query = query.where(PostRow.company == company)
        query = query.order_by(PostRow.company, PostRow.timestamp.desc())
        all_posts = list(session.execute(query).scalars().all())

        if force_all:
            return all_posts

        targets = []
        for post in all_posts:
            analysis = session.execute(
                select(AnalysisRow).where(AnalysisRow.post_id == post.id)
            ).scalar_one_or_none()

            if _is_fallback(analysis):
                targets.append(post)
            elif not post.text or not post.text.strip():
                # Empty text — re-analyze with media context injection
                targets.append(post)

        return targets
    finally:
        session.close()


def delete_existing_analysis(post_id: int) -> None:
    """Delete any existing analysis rows for a post so store_analysis creates fresh ones."""
    factory = get_session_factory()
    session = factory()
    try:
        session.execute(delete(AnalysisRow).where(AnalysisRow.post_id == post_id))
        session.commit()
    finally:
        session.close()


async def reanalyze_post(post: PostRow) -> dict | None:
    """Run the full analysis pipeline for one post."""
    baseline = get_company_baseline(post.company)
    post_dict = post.to_dict()
    enriched = preprocess_post(post_dict, baseline)
    analysis = await analyze_post(enriched)
    alert = evaluate_alert(enriched, analysis.get("alert_tag", "LOW"))
    analysis["alert_tag"] = alert["alert_tag"]
    return analysis


async def run(company: str | None, force_all: bool, dry_run: bool):
    storage_init_db()

    targets = collect_targets(company, force_all)

    if not targets:
        print("\n  ✅ All posts have good analysis — nothing to re-analyze.\n")
        return

    scope = f"company={company}" if company else ("ALL posts" if force_all else "failed/empty posts")
    print(f"\n  🔍 Found {len(targets)} post(s) to re-analyze ({scope})")

    if dry_run:
        print("\n  [DRY RUN] Posts that would be re-analyzed:")
        for p in targets:
            text_preview = (p.text or "[no text]")[:60].replace("\n", " ")
            print(f"    [{p.id}] {p.company} | {p.timestamp} | {text_preview!r}")
        print()
        return

    print()
    success = 0
    failed = 0

    for i, post in enumerate(targets, 1):
        text_preview = (post.text or "[no text]")[:55].replace("\n", " ")
        print(f"  [{i}/{len(targets)}] {post.company} — {text_preview!r}")

        try:
            # Wipe old analysis so store_analysis saves fresh data
            delete_existing_analysis(post.id)
            analysis = await reanalyze_post(post)

            # Detect if we still got a fallback (e.g., API key missing)
            snap = (analysis.get("executive_snapshot") or "").strip()
            if snap.startswith("Analysis failed"):
                print(f"         ⚠️  Still failed (API issue?) — fallback stored.")
                failed += 1
            else:
                tag = analysis.get("alert_tag", "?")
                print(f"         ✅  [{tag}] {snap[:70]}")
                success += 1

            store_analysis(post.id, analysis)

        except Exception as e:
            logger.error(f"Failed to re-analyze post {post.id}: {e}")
            print(f"         ❌ Error: {e}")
            failed += 1

    print(f"\n  ═══ Done: {success} re-analyzed, {failed} failed ═══\n")


def main():
    parser = argparse.ArgumentParser(
        description="Force re-analyze posts with missing or fallback AI data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--company", type=str, help="Limit re-analysis to one company")
    parser.add_argument("--all", action="store_true", dest="force_all",
                        help="Re-analyze ALL posts (full refresh)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be re-analyzed without making changes")
    args = parser.parse_args()

    asyncio.run(run(args.company, args.force_all, args.dry_run))


if __name__ == "__main__":
    main()
