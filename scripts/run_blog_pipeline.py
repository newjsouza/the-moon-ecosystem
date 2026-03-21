"""
CLI entry point for BlogPipeline.
Usage:
    python3 scripts/run_blog_pipeline.py "Topic of the blog post"
    python3 scripts/run_blog_pipeline.py "Topic" --dry-run
    python3 scripts/run_blog_pipeline.py "Topic" --no-telegram
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
    parser = argparse.ArgumentParser(description="Run The Moon Blog Pipeline")
    parser.add_argument("topic", help="Blog post topic")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate content without publishing")
    parser.add_argument("--no-telegram", action="store_true",
                        help="Skip Telegram notification")
    parser.add_argument("--language", default="pt-BR",
                        help="Post language (default: pt-BR)")
    parser.add_argument("--max-words", type=int, default=800,
                        help="Target word count (default: 800)")
    args = parser.parse_args()

    from agents.blog_pipeline_agent import BlogPipelineAgent
    agent = BlogPipelineAgent()

    print(f"\n🌙 The Moon — Blog Pipeline")
    print(f"Topic: {args.topic}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'PUBLISH'}")
    print(f"Language: {args.language}")
    print("-" * 50)

    result = await agent._execute(
        "dry_run" if args.dry_run else "write",
        topic=args.topic,
        language=args.language,
        max_words=args.max_words,
        notify_telegram=not args.no_telegram,
    )

    print("\n" + "=" * 50)
    if result.success:
        print("✅ Pipeline completed successfully")
        data = result.data
        print(f"Steps completed: {data.get('steps_completed', [])}")
        if data.get('steps_failed'):
            print(f"Steps failed:    {data.get('steps_failed', [])}")
        print(f"Eval score:      {data.get('eval_score', 'N/A')}")
        print(f"Execution time:  {data.get('execution_time', 0):.1f}s")
    else:
        print(f"❌ Pipeline failed: {result.error}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())