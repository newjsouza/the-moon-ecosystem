"""
YouTubeAgent — autonomous YouTube content creation pipeline.

Pipeline:
  1. Trending analysis (NexusIntelligence + YouTubeClient)
  2. Script generation (LLM — structured, timestamped)
  3. SEO optimization (title, description, tags)
  4. Thumbnail generation (ffmpeg harness — text overlay)
  5. Repurpose script → blog post (BlogPipeline)
  6. Cross-post notification (OmniChannelStrategist)
  7. RAG indexing of script

Commands:
  'script'    → generate script for given topic
  'trending'  → fetch trending topics for domain
  'seo'       → optimize existing title/description
  'repurpose' → convert existing blog post → video script
  'pipeline'  → full end-to-end (trending → script → seo → blog)
"""
import asyncio
import logging
from core.agent_base import AgentBase, TaskResult
from core.observability.decorators import observe_agent
from core.llm import LLMRouter
from core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from core.youtube_config import (
    YOUTUBE_DOMAINS, DEFAULT_DOMAINS, ScriptConfig, SCRIPT_SECTIONS
)


@observe_agent
class YouTubeAgent(AgentBase):
    """
    Autonomous YouTube content pipeline.
    Zero cost: YouTube Data API v3 free tier (10k units/day).
    All generation via Groq (free tier).
    """

    AGENT_ID = "youtube"

    def __init__(self):
        super().__init__()
        self.llm = LLMRouter()
        self._api_cb = CircuitBreaker(
            "youtube_data_api",
            CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout=120.0,
                timeout=15.0,
            )
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Execute YouTube pipeline command.
        kwargs:
            topic (str): video topic
            domain (str): content domain (tech, economy, sports...)
            dry_run (bool): skip publishing/notifications
            language (str): script language (default pt-BR)
            repurpose_to_blog (bool): also publish as blog post
            notify_telegram (bool): send Telegram notification
        """
        start = asyncio.get_event_loop().time()
        cmd = task.lower().strip()

        config = ScriptConfig(
            topic=kwargs.get("topic", ""),
            domain=kwargs.get("domain", DEFAULT_DOMAINS[0]),
            language=kwargs.get("language", "pt-BR"),
            tone=kwargs.get("tone", "analytical"),
            dry_run=kwargs.get("dry_run", False),
            repurpose_to_blog=kwargs.get("repurpose_to_blog", True),
            notify_telegram=kwargs.get("notify_telegram", True),
            target_keywords=kwargs.get("keywords", []),
        )

        try:
            if cmd == "pipeline":
                return await self._run_full_pipeline(config, start)
            elif cmd == "script":
                if not config.topic:
                    return TaskResult(
                        success=False,
                        error="'topic' kwarg required for script command"
                    )
                return await self._generate_script(config, start)
            elif cmd == "trending":
                return await self._get_trending(config, start)
            elif cmd == "seo":
                return await self._optimize_seo(config, kwargs, start)
            elif cmd == "repurpose":
                return await self._repurpose_blog_to_script(config, kwargs, start)
            elif cmd == "quota":
                from skills.youtube import YouTubeClient
                client = YouTubeClient()
                return TaskResult(
                    success=True,
                    data=client.get_quota_status(),
                    execution_time=asyncio.get_event_loop().time() - start
                )
            else:
                return TaskResult(
                    success=False,
                    error=(
                        f"Unknown command: '{cmd}'. "
                        "Valid: pipeline, script, trending, seo, repurpose, quota"
                    )
                )
        except Exception as e:
            self.logger.error(f"YouTubeAgent._execute error: {e}", exc_info=True)
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=asyncio.get_event_loop().time() - start
            )

    async def _run_full_pipeline(
        self, config: ScriptConfig, start: float
    ) -> TaskResult:
        """Full pipeline: trending → pick topic → script → seo → blog → notify."""
        pipeline_data = {"steps": [], "domain": config.domain}

        # Step 1: Get trending topics
        if not config.topic:
            trending = await self._fetch_trending(config)
            if trending:
                config.topic = trending[0].title
                pipeline_data["trending"] = [
                    {"title": t.title, "score": t.relevance_score}
                    for t in trending[:5]
                ]
                pipeline_data["steps"].append("trending")
                self.logger.info(
                    f"Selected topic from trending: {config.topic}"
                )
            else:
                return TaskResult(
                    success=False,
                    error="No trending topics found — provide topic explicitly"
                )

        # Step 2: Generate script
        script_result = await self._generate_script_data(config)
        if not script_result.get("script"):
            return TaskResult(
                success=False,
                error="Script generation failed"
            )
        pipeline_data["script"] = script_result
        pipeline_data["steps"].append("script")

        # Step 3: SEO optimization
        seo_result = await self._run_seo_optimization(
            config=config,
            script_content=script_result.get("script", ""),
        )
        pipeline_data["seo"] = seo_result
        pipeline_data["steps"].append("seo")

        # Step 4: Thumbnail generation
        if not config.dry_run:
            thumb_result = await self._generate_thumbnail(
                title=seo_result.get("optimized_title", config.topic),
                config=config,
            )
            if thumb_result.get("thumbnail_path"):
                pipeline_data["thumbnail"] = thumb_result
                pipeline_data["steps"].append("thumbnail")

        # Step 5: Repurpose to blog
        if config.repurpose_to_blog and not config.dry_run:
            blog_result = await self._repurpose_script_to_blog(
                config=config,
                script=script_result.get("script", ""),
                seo=seo_result,
            )
            if blog_result.success:
                pipeline_data["blog_post"] = blog_result.data
                pipeline_data["steps"].append("blog_repurposed")

        # Step 6: RAG indexing
        if not config.dry_run:
            await self._index_script_to_rag(config, script_result, seo_result)
            pipeline_data["steps"].append("rag_indexed")

        # Step 7: Telegram notification
        if config.notify_telegram and not config.dry_run:
            await self._send_telegram_notification(config, pipeline_data)
            pipeline_data["steps"].append("telegram_notified")

        return TaskResult(
            success=True,
            data=pipeline_data,
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _generate_script(
        self, config: ScriptConfig, start: float
    ) -> TaskResult:
        """Generate script only (no SEO, no blog)."""
        data = await self._generate_script_data(config)
        return TaskResult(
            success=bool(data.get("script")),
            data=data,
            error=None if data.get("script") else "Script generation returned empty",
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _generate_script_data(self, config: ScriptConfig) -> dict:
        """Core script generation via LLM."""
        domain_context = YOUTUBE_DOMAINS.get(config.domain, [])
        keywords_hint = (
            f"\nTarget keywords: {', '.join(config.target_keywords)}"
            if config.target_keywords else ""
        )
        sections_format = "\n".join(
            [f"## {s.upper()}" for s in SCRIPT_SECTIONS]
        )

        prompt = f"""You are a {config.language} YouTube content creator for "The Moon" channel.
Write a complete video script about: {config.topic}

Domain context: {', '.join(domain_context)}{keywords_hint}
Target duration: {config.target_duration_min} minutes
Tone: {config.tone}

Script structure (use these exact sections):
{sections_format}

Requirements:
- Language: {config.language}
- Hook: compelling question or shocking fact in first 15 seconds
- Include [TIMESTAMP] markers at each section (e.g. [0:00], [0:15], [1:30])
- Data points section: include 3-5 real statistics or facts
- CTA: ask viewers to like, subscribe, and comment their opinion
- Total word count: {config.target_duration_min * 130}-{config.target_duration_min * 150} words
- Tone: {config.tone}, authoritative, engaging

Write the complete script now:"""

        try:
            script = await self.llm.complete(prompt, task_type="complex")
            word_count = len(script.split()) if script else 0
            estimated_duration = round(word_count / 140, 1)

            return {
                "topic": config.topic,
                "script": script,
                "word_count": word_count,
                "estimated_duration_min": estimated_duration,
                "language": config.language,
                "domain": config.domain,
                "sections": SCRIPT_SECTIONS,
            }
        except Exception as e:
            self.logger.error(f"Script generation failed: {e}")
            return {"topic": config.topic, "script": "", "error": str(e)}

    async def _run_seo_optimization(
        self, config: ScriptConfig, script_content: str
    ) -> dict:
        """Generate SEO-optimized title, description and tags."""
        prompt = f"""You are a YouTube SEO expert. Analyze this script and generate:

Script topic: {config.topic}
Script excerpt (first 500 chars): {script_content[:500]}

Generate in JSON format:
{{
  "optimized_title": "compelling title under 60 chars with main keyword",
  "description": "first 150 chars hook + full description 300-500 chars total",
  "tags": ["tag1", "tag2", ...] (max {config.max_tags} tags),
  "main_keyword": "primary SEO keyword",
  "secondary_keywords": ["kw1", "kw2", "kw3"],
  "thumbnail_text": "3-5 words max for thumbnail overlay"
}}

Language: {config.language}
Respond ONLY with valid JSON:"""

        try:
            import json
            response = await self.llm.complete(prompt, task_type="fast")
            # Extract JSON from response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                seo_data = json.loads(response[start:end])
            else:
                raise ValueError("No JSON found in LLM response")
            return seo_data
        except Exception as e:
            self.logger.warning(f"SEO optimization failed: {e} — using fallback")
            return {
                "optimized_title": config.topic[:60],
                "description": f"Vídeo sobre {config.topic}.",
                "tags": config.topic.lower().split()[:config.max_tags],
                "main_keyword": config.topic.split()[0] if config.topic else "",
                "secondary_keywords": [],
                "thumbnail_text": config.topic[:30],
            }

    async def _generate_thumbnail(self, title: str, config: ScriptConfig) -> dict:
        """Generate thumbnail using ffmpeg harness (text overlay)."""
        try:
            from agents.moon_cli_agent import MoonCLIAgent
            cli_agent = MoonCLIAgent()

            # Use ffmpeg to create a simple thumbnail with text overlay
            output_path = f"data/youtube/thumbnails/{config.topic[:30].replace(' ', '_')}.jpg"
            import os
            os.makedirs("data/youtube/thumbnails", exist_ok=True)

            # ffmpeg command: black background 1280x720 + white text
            ffmpeg_cmd = (
                f"ffmpeg -f lavfi -i color=black:size=1280x720:rate=1 "
                f"-vf \"drawtext=text='{title[:40]}':fontcolor=white:"
                f"fontsize=60:x=(w-text_w)/2:y=(h-text_h)/2\" "
                f"-vframes 1 -y {output_path}"
            )

            result = await cli_agent._execute(
                "run",
                harness="ffmpeg",
                command=ffmpeg_cmd,
            )

            if result.success:
                return {"thumbnail_path": output_path, "title": title}
            else:
                self.logger.warning(f"Thumbnail generation failed: {result.error}")
                return {"thumbnail_path": "", "error": result.error}
        except Exception as e:
            self.logger.warning(f"Thumbnail skipped: {e}")
            return {"thumbnail_path": "", "error": str(e)}

    async def _repurpose_script_to_blog(
        self, config: ScriptConfig, script: str, seo: dict
    ) -> TaskResult:
        """Repurpose video script as a blog post via BlogPipeline."""
        try:
            from blog.pipeline import BlogPipeline
            pipeline = BlogPipeline()

            # Convert script to blog-friendly topic
            blog_topic = (
                f"{seo.get('optimized_title', config.topic)} "
                f"[adaptado do roteiro YouTube]"
            )
            return await pipeline.run(
                topic=blog_topic,
                language=config.language,
                notify_telegram=False,
                dry_run=config.dry_run,
                context=script[:800],
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def _fetch_trending(self, config: ScriptConfig) -> list:
        """Fetch trending topics via YouTubeClient (circuit breaker protected)."""
        try:
            from skills.youtube import YouTubeClient
            client = YouTubeClient()

            keywords = YOUTUBE_DOMAINS.get(config.domain, [config.domain])
            query = " ".join(keywords[:2])

            trending = await self._api_cb.call(
                client.search_trending,
                query=query,
                max_results=10,
                region_code="BR",
                relevance_language="pt",
            )
            return trending or []
        except Exception as e:
            self.logger.warning(f"Trending fetch failed: {e}")
            return []

    async def _get_trending(
        self, config: ScriptConfig, start: float
    ) -> TaskResult:
        """Return trending topics for domain."""
        trending = await self._fetch_trending(config)
        return TaskResult(
            success=True,
            data={
                "domain": config.domain,
                "topics": [
                    {
                        "title": t.title,
                        "channel": t.channel_title,
                        "score": t.relevance_score,
                        "keywords": t.keywords[:5],
                    }
                    for t in trending
                ],
                "count": len(trending),
            },
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _optimize_seo(
        self, config: ScriptConfig, kwargs: dict, start: float
    ) -> TaskResult:
        """SEO optimization command."""
        content = kwargs.get("content", config.topic)
        seo = await self._run_seo_optimization(config, content)
        return TaskResult(
            success=True,
            data=seo,
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _repurpose_blog_to_script(
        self, config: ScriptConfig, kwargs: dict, start: float
    ) -> TaskResult:
        """Convert existing blog post content to video script."""
        blog_content = kwargs.get("content", "")
        if not blog_content:
            return TaskResult(
                success=False,
                error="'content' kwarg required for repurpose command"
            )

        prompt = f"""Convert this blog post to a YouTube video script in {config.language}.

Blog content:
{blog_content[:2000]}

Requirements:
- Add [TIMESTAMP] markers
- Add hook in first 15 seconds
- Add CTA at the end
- Tone: {config.tone}
- Adapt for spoken delivery (not written text)

Write the adapted video script:"""

        try:
            script = await self.llm.complete(prompt, task_type="complex")
            return TaskResult(
                success=True,
                data={
                    "script": script,
                    "word_count": len(script.split()),
                    "source": "blog_repurpose",
                    "original_topic": config.topic,
                },
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def _index_script_to_rag(
        self, config: ScriptConfig, script_data: dict, seo: dict
    ) -> None:
        """Index script into RAG for future reference and anti-repetition."""
        try:
            from core.rag import RAGEngine
            rag = RAGEngine()
            await rag.ingest(
                content=script_data.get("script", ""),
                metadata={
                    "type": "youtube_script",
                    "topic": config.topic,
                    "domain": config.domain,
                    "title": seo.get("optimized_title", config.topic),
                    "tags": seo.get("tags", []),
                    "word_count": script_data.get("word_count", 0),
                },
                collection="youtube_scripts",
            )
        except Exception as e:
            self.logger.debug(f"RAG indexing skipped: {e}")

    async def _send_telegram_notification(
        self, config: ScriptConfig, pipeline_data: dict
    ) -> None:
        """Send pipeline completion notification via Telegram."""
        try:
            seo = pipeline_data.get("seo", {})
            title = seo.get("optimized_title", config.topic)
            steps = pipeline_data.get("steps", [])
            duration = pipeline_data.get(
                "script", {}
            ).get("estimated_duration_min", "?")

            message = (
                f"🎬 *YouTube Script Gerado*\n\n"
                f"📌 *{title}*\n"
                f"🕐 Duração estimada: {duration} min\n"
                f"✅ Steps: {' → '.join(steps)}\n"
                f"🏷 Tags: {', '.join(seo.get('tags', [])[:5])}"
            )
            from telegram.bot import send_notification
            await send_notification(message)
        except Exception as e:
            self.logger.debug(f"Telegram notification skipped: {e}")
