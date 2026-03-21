"""
CLI entry point for SportsAnalyticsAgent.
Usage:
    python3 scripts/run_sports_report.py brasileirao
    python3 scripts/run_sports_report.py champions_league --dry-run
    python3 scripts/run_sports_report.py premier_league --standings-only
    python3 scripts/run_sports_report.py --list-competitions
"""
import asyncio
import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)


async def main():
    parser = argparse.ArgumentParser(
        description="The Moon — Sports Analytics Report"
    )
    parser.add_argument("competition", nargs="?", default="brasileirao",
                        help="Competition name (default: brasileirao)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and analyze without publishing")
    parser.add_argument("--no-blog", action="store_true",
                        help="Skip blog publishing")
    parser.add_argument("--no-telegram", action="store_true",
                        help="Skip Telegram notification")
    parser.add_argument("--standings-only", action="store_true",
                        help="Only fetch standings")
    parser.add_argument("--matches-only", action="store_true",
                        help="Only fetch recent matches")
    parser.add_argument("--list-competitions", action="store_true",
                        help="List available competitions and exit")
    parser.add_argument("--language", default="pt-BR")
    args = parser.parse_args()

    from agents.sports_analytics_agent import SportsAnalyticsAgent
    from core.sports_config import COMPETITION_IDS

    if args.list_competitions:
        print("\n🌙 Available competitions:")
        for name, code in COMPETITION_IDS.items():
            print(f"  {name:<25} → {code}")
        return

    agent = SportsAnalyticsAgent()

    if args.standings_only:
        cmd = "standings"
    elif args.matches_only:
        cmd = "matches"
    else:
        cmd = "report"

    print(f"\n⚽ The Moon — Sports Analytics")
    print(f"Competition: {args.competition}")
    print(f"Command: {cmd}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("-" * 50)

    result = await agent._execute(
        cmd,
        competition=args.competition,
        publish_blog=not args.no_blog,
        notify_telegram=not args.no_telegram,
        dry_run=args.dry_run,
        language=args.language,
    )

    print("\n" + "=" * 50)
    if result.success:
        print("✅ Report completed")
        data = result.data
        print(f"Steps: {data.get('steps', [])}")
        if data.get("narrative"):
            print(f"\nNarrative preview:")
            print(data["narrative"][:300] + "...")
    else:
        print(f"❌ Report failed: {result.error}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())