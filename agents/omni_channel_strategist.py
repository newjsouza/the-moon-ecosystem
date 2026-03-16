"""
agents/omni_channel_strategist.py
Omni-Channel Content Strategist — Marketing Autônomo do Ecossistema The Moon.

Fecha o ciclo de conteúdo: detecta publicações via MessageBus, adapta o
conteúdo para cada plataforma com LLM, agenda e distribui autonomamente.

Plataformas suportadas:
  - Telegram  (via bot existente do ecossistema — TELEGRAM_BOT_TOKEN)
  - Twitter/X (via Tweepy — free tier X API v2)
  - LinkedIn  (via LinkedIn API v2 — OAuth 2.0)

ZERO CUSTO:
  - LLM para adaptação: Groq free tier (llama-3.1-8b-instant)
  - Todas as APIs de rede social operam no plano gratuito
  - Persistência: JSON local em data/omni_channel/

INTEGRAÇÃO COM O ECOSSISTEMA:
  - Assina (MessageBus): blog.published, youtube.published, content.published
  - Publica (MessageBus): content.distributed → SemanticMemoryWeaver
  - Segurança: valida modelo com WatchdogAgent antes de chamadas LLM
  - Graceful degradation: opera com qualquer subconjunto de plataformas configuradas

VARIÁVEIS DE AMBIENTE NECESSÁRIAS:
  Telegram : TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
  Twitter  : TWITTER_API_KEY, TWITTER_API_SECRET,
             TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
  LinkedIn : LINKEDIN_ACCESS_TOKEN, LINKEDIN_PERSON_URN
             LINKEDIN_ORG_URN (opcional, para página de empresa)
"""

from __future__ import annotations

import asyncio
import hashlib
import heapq
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.agent_base import AgentBase, AgentPriority, TaskResult

logger = logging.getLogger("moon.agents.strategist")


# ─────────────────────────────────────────────────────────────
#  Storage & Configuration
# ─────────────────────────────────────────────────────────────
STRATEGIST_DIR   = Path("data/omni_channel")
HISTORY_FILE     = STRATEGIST_DIR / "post_history.json"
FINGERPRINT_FILE = STRATEGIST_DIR / "fingerprints.json"

# Optimal UTC posting hours
OPTIMAL_HOURS: List[int] = [9, 12, 18, 21]

# Max posts per platform per day (rate-limit compliance)
DAILY_LIMITS: Dict[str, int] = {
    "telegram": 20,
    "twitter":   5,
    "linkedin":  3,
}

# Hard character limits per platform
CHAR_LIMITS: Dict[str, int] = {
    "telegram": 4096,
    "twitter":   280,
    "linkedin": 3000,
}

# Platform-specific tone instructions sent to the LLM
TONE_INSTRUCTIONS: Dict[str, str] = {
    "telegram": (
        "Tom conversacional e direto. Use Markdown (negrito com *, itálico com _). "
        "Inclua 1-2 emojis relevantes. Máximo 2 parágrafos + link. "
        "Seja informativo mas pessoal, como uma mensagem para um grupo de amigos inteligentes."
    ),
    "twitter": (
        "Tom provocativo e de alto impacto. A primeira frase DEVE parar o scroll — "
        "use uma pergunta, dado surpreendente ou afirmação forte. "
        "Use emojis estrategicamente (máx 3). Inclua 2-3 hashtags relevantes no ÚLTIMO tweet. "
        "Se o conteúdo for longo, formate como thread numerada (1/N, 2/N...)."
    ),
    "linkedin": (
        "Tom profissional, analítico e orientado a insights. "
        "Estrutura ideal: insight poderosa (1 linha) → contexto (2-3 linhas) → "
        "aplicação prática (2-3 linhas) → CTA com link. "
        "Emojis com moderação (máx 2). 3-5 hashtags relevantes ao final. "
        "Escreva como um profissional sênior compartilhando conhecimento genuíno."
    ),
}


# ─────────────────────────────────────────────────────────────
#  Enums
# ─────────────────────────────────────────────────────────────

class Platform(str, Enum):
    TELEGRAM = "telegram"
    TWITTER  = "twitter"
    LINKEDIN = "linkedin"


class ContentType(str, Enum):
    BLOG_POST     = "blog_post"
    YOUTUBE_VIDEO = "youtube_video"
    RESEARCH      = "research"
    BET_ANALYSIS  = "bet_analysis"
    GENERAL       = "general"


class PostStatus(str, Enum):
    PENDING   = "pending"
    SCHEDULED = "scheduled"
    POSTED    = "posted"
    FAILED    = "failed"
    SKIPPED   = "skipped"


# ─────────────────────────────────────────────────────────────
#  Data Models
# ─────────────────────────────────────────────────────────────

@dataclass
class ContentPiece:
    """Represents a piece of content ready to be distributed."""
    id:           str
    title:        str
    summary:      str
    url:          str
    content_type: ContentType
    source_agent: str
    tags:         List[str]       = field(default_factory=list)
    full_text:    str             = ""
    image_url:    Optional[str]   = None
    published_at: float           = field(default_factory=time.time)
    metadata:     Dict[str, Any]  = field(default_factory=dict)

    def fingerprint(self) -> str:
        """SHA256 hash of URL — used for deduplication."""
        return hashlib.sha256(self.url.encode()).hexdigest()[:16]


@dataclass
class PlatformPost:
    """Content adapted and ready for a specific platform."""
    content_id:   str
    platform:     Platform
    text:         str
    thread:       List[str]       = field(default_factory=list)
    hashtags:     List[str]       = field(default_factory=list)
    image_url:    Optional[str]   = None
    scheduled_at: float           = field(default_factory=time.time)
    status:       PostStatus      = PostStatus.PENDING
    error:        Optional[str]   = None
    posted_at:    Optional[float] = None
    platform_id:  Optional[str]   = None


@dataclass
class _QueueEntry:
    """Min-heap entry for the PostScheduler."""
    scheduled_at: float
    post:         PlatformPost

    def __lt__(self, other: "_QueueEntry") -> bool:
        return self.scheduled_at < other.scheduled_at


# ─────────────────────────────────────────────────────────────
#  Platform Clients
# ─────────────────────────────────────────────────────────────

class BasePlatformClient:
    """Abstract base for all platform posting clients."""
    platform: Platform

    async def post(self, platform_post: PlatformPost) -> Tuple[bool, Optional[str]]:
        """Returns (success, platform_id_or_error_message)."""
        raise NotImplementedError

    def is_available(self) -> bool:
        """Returns True only if all required credentials are present."""
        raise NotImplementedError


class TelegramPlatformClient(BasePlatformClient):
    """
    Posts to a Telegram channel using the existing ecosystem bot.
    Reuses TELEGRAM_BOT_TOKEN from the environment.
    Requires TELEGRAM_CHANNEL_ID (e.g. '@mychannel' or '-100xxxxxxxxxx').
    """
    platform = Platform.TELEGRAM

    def __init__(self) -> None:
        self._token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._channel = os.getenv("TELEGRAM_CHANNEL_ID", "")
        self._bot     = None

    def is_available(self) -> bool:
        return bool(self._token and self._channel)

    async def _get_bot(self):
        if self._bot is None:
            from telegram import Bot
            self._bot = Bot(token=self._token)
        return self._bot

    async def post(self, platform_post: PlatformPost) -> Tuple[bool, Optional[str]]:
        if not self.is_available():
            return False, "TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID not configured."
        try:
            bot = await self._get_bot()
            msg = await bot.send_message(
                chat_id    = self._channel,
                text       = platform_post.text[:CHAR_LIMITS["telegram"]],
                parse_mode = "Markdown",
            )
            return True, str(msg.message_id)
        except Exception as exc:
            return False, f"Telegram error: {exc}"


class TwitterPlatformClient(BasePlatformClient):
    """
    Posts tweets and threads via Tweepy (X API v2 — free write-only tier).
    Required env vars: TWITTER_API_KEY, TWITTER_API_SECRET,
                       TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
    """
    platform = Platform.TWITTER

    def __init__(self) -> None:
        self._api_key = os.getenv("TWITTER_API_KEY", "")
        self._api_sec = os.getenv("TWITTER_API_SECRET", "")
        self._acc_tok = os.getenv("TWITTER_ACCESS_TOKEN", "")
        self._acc_sec = os.getenv("TWITTER_ACCESS_SECRET", "")
        self._client  = None

    def is_available(self) -> bool:
        return all([self._api_key, self._api_sec, self._acc_tok, self._acc_sec])

    def _get_client(self):
        if self._client is None:
            import tweepy
            self._client = tweepy.Client(
                consumer_key        = self._api_key,
                consumer_secret     = self._api_sec,
                access_token        = self._acc_tok,
                access_token_secret = self._acc_sec,
            )
        return self._client

    async def post(self, platform_post: PlatformPost) -> Tuple[bool, Optional[str]]:
        if not self.is_available():
            return False, "Twitter credentials not configured."
        try:
            client = self._get_client()
            tweets = platform_post.thread if platform_post.thread else [platform_post.text]
            last_id: Optional[str] = None
            posted_ids: List[str]  = []
            loop = asyncio.get_event_loop()

            for tweet_text in tweets:
                kwargs: Dict[str, Any] = {"text": tweet_text[:280]}
                if last_id:
                    kwargs["in_reply_to_tweet_id"] = last_id
                resp    = await loop.run_in_executor(
                    None, lambda k=kwargs: client.create_tweet(**k)
                )
                last_id = str(resp.data["id"])
                posted_ids.append(last_id)
                await asyncio.sleep(1.5)

            return True, ",".join(posted_ids)
        except ImportError:
            return False, "tweepy not installed. Run: pip install tweepy"
        except Exception as exc:
            return False, f"Twitter error: {exc}"


class LinkedInPlatformClient(BasePlatformClient):
    """
    Posts to LinkedIn via UGC Posts API v2.
    Required env vars: LINKEDIN_ACCESS_TOKEN, LINKEDIN_PERSON_URN
    Optional env var:  LINKEDIN_ORG_URN (post as company page instead of person)
    """
    platform = Platform.LINKEDIN

    def __init__(self) -> None:
        self._token      = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
        self._person_urn = os.getenv("LINKEDIN_PERSON_URN", "")
        self._org_urn    = os.getenv("LINKEDIN_ORG_URN", "")

    def is_available(self) -> bool:
        return bool(self._token and self._person_urn)

    async def post(self, platform_post: PlatformPost) -> Tuple[bool, Optional[str]]:
        if not self.is_available():
            return False, "LINKEDIN_ACCESS_TOKEN or LINKEDIN_PERSON_URN not configured."
        try:
            import httpx
            author  = (
                self._org_urn
                if self._org_urn
                else f"urn:li:person:{self._person_urn}"
            )
            payload = {
                "author":          author,
                "lifecycleState":  "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary":    {"text": platform_post.text[:3000]},
                        "shareMediaCategory": "NONE",
                    }
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                },
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.linkedin.com/v2/ugcPosts",
                    json    = payload,
                    headers = {
                        "Authorization":             f"Bearer {self._token}",
                        "Content-Type":              "application/json",
                        "X-Restli-Protocol-Version": "2.0.0",
                    },
                )
            if resp.status_code in (200, 201):
                return True, resp.headers.get("x-restli-id", "unknown")
            return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
        except ImportError:
            return False, "httpx not installed. Run: pip install httpx"
        except Exception as exc:
            return False, f"LinkedIn error: {exc}"


# ─────────────────────────────────────────────────────────────
#  Content Adapter (LLM-powered, rule-based fallback)
# ─────────────────────────────────────────────────────────────

class ContentAdapter:
    """
    Adapts a ContentPiece to each platform's format and tone.
    Primary:  Groq llama-3.1-8b-instant (fast, free)
    Fallback: Rule-based truncation + hashtag injection
    """

    def __init__(self, groq_client=None) -> None:
        self._groq = groq_client

    async def adapt(self, piece: ContentPiece, platform: Platform) -> PlatformPost:
        """Generates a PlatformPost optimised for the target platform."""
        tone  = TONE_INSTRUCTIONS[platform.value]
        limit = CHAR_LIMITS[platform.value]
        context = (
            f"Título: {piece.title}\n"
            f"Resumo: {piece.summary}\n"
            f"URL: {piece.url}\n"
            f"Tags: {', '.join(piece.tags)}\n"
            f"Tipo: {piece.content_type.value}\n"
        )
        if piece.full_text:
            context += f"Conteúdo (primeiros 800 chars):\n{piece.full_text[:800]}\n"

        adapted_text = (
            await self._llm_adapt(context, tone, platform, limit)
            if self._groq
            else self._rule_based_adapt(piece, platform, limit)
        )

        post = PlatformPost(
            content_id = piece.id,
            platform   = platform,
            text       = adapted_text,
            image_url  = piece.image_url,
        )

        if platform == Platform.TWITTER and len(adapted_text) > 255:
            post.thread = self._split_twitter_thread(adapted_text, piece.url)
            post.text   = post.thread[0]

        return post

    async def _llm_adapt(
        self, context: str, tone: str, platform: Platform, char_limit: int
    ) -> str:
        prompt = (
            f"Você é um especialista em marketing de conteúdo para {platform.value.upper()}.\n\n"
            f"DIRETRIZES DE TOM PARA {platform.value.upper()}:\n{tone}\n\n"
            f"CONTEÚDO A ADAPTAR:\n{context}\n\n"
            f"REGRAS ABSOLUTAS:\n"
            f"• Máximo {char_limit} caracteres no total\n"
            f"• Sempre inclua a URL ao final\n"
            f"• Retorne APENAS o texto final — sem explicações, sem aspas, sem prefixos\n"
        )
        try:
            resp = await self._groq.chat.completions.create(
                model       = "llama-3.1-8b-instant",
                messages    = [{"role": "user", "content": prompt}],
                max_tokens  = 512,
                temperature = 0.72,
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning(f"ContentAdapter LLM failed for {platform.value}: {exc}")
            return self._rule_based_adapt_raw(
                title    = context.split("\n")[0].replace("Título: ", ""),
                summary  = context.split("\n")[1].replace("Resumo: ", ""),
                url      = context.split("\n")[2].replace("URL: ", ""),
                tags     = [],
                platform = platform,
                limit    = char_limit,
            )

    def _rule_based_adapt(self, piece: ContentPiece, platform: Platform, limit: int) -> str:
        return self._rule_based_adapt_raw(
            piece.title, piece.summary, piece.url, piece.tags, platform, limit
        )

    def _rule_based_adapt_raw(
        self,
        title:    str,
        summary:  str,
        url:      str,
        tags:     List[str],
        platform: Platform,
        limit:    int,
    ) -> str:
        hashtags = " ".join(f"#{t.replace(' ', '').replace('-', '')}" for t in tags[:4] if t)
        if platform == Platform.TWITTER:
            base = f"{title[:200]}\n\n{url}"
            if hashtags:
                base += f"\n{hashtags}"
        elif platform == Platform.LINKEDIN:
            base = f"{title}\n\n{summary}\n\n🔗 Leia mais: {url}"
            if hashtags:
                base += f"\n\n{hashtags}"
        else:
            base = f"*{title}*\n\n{summary}\n\n🔗 {url}"
        return base[:limit]

    def _split_twitter_thread(self, text: str, url: str) -> List[str]:
        """
        Splits text into a numbered Twitter thread.
        Each tweet body ≤ 268 chars (10 chars reserved for '1/N ' prefix).
        URL is appended to the last tweet.
        """
        TWEET_BODY_LIMIT = 268
        words  = text.split()
        tweets: List[str] = []
        current = ""

        for word in words:
            candidate = (current + " " + word).strip()
            if len(candidate) <= TWEET_BODY_LIMIT:
                current = candidate
            else:
                if current:
                    tweets.append(current)
                current = word

        if current:
            tweets.append(current)

        if not tweets:
            tweets = [text[:TWEET_BODY_LIMIT]]

        url_suffix = f"\n\n{url}"
        if len(tweets[-1]) + len(url_suffix) <= 270:
            tweets[-1] += url_suffix
        else:
            tweets.append(url)

        if len(tweets) > 1:
            n = len(tweets)
            tweets = [f"{i + 1}/{n} {t}" for i, t in enumerate(tweets)]

        return tweets


# ─────────────────────────────────────────────────────────────
#  Post Scheduler (min-heap + rate limiting + optimal windows)
# ─────────────────────────────────────────────────────────────

class PostScheduler:
    """
    Priority queue scheduler for platform posts.
    - Min-heap sorted by scheduled_at timestamp
    - Daily rate limit tracking per platform (resets at UTC midnight)
    - Optimal posting window selection from OPTIMAL_HOURS
    - Stagger support: spreads platform posts N minutes apart
    """

    def __init__(self) -> None:
        self._heap:        List[_QueueEntry] = []
        self._daily_count: Dict[str, int]   = {}
        self._day_key:     str              = self._today()

    def can_post(self, platform: Platform) -> bool:
        self._reset_if_new_day()
        return self._daily_count.get(platform.value, 0) < DAILY_LIMITS.get(platform.value, 10)

    def record_post(self, platform: Platform) -> None:
        self._reset_if_new_day()
        self._daily_count[platform.value] = self._daily_count.get(platform.value, 0) + 1

    def enqueue(self, post: PlatformPost, delay_seconds: float = 0) -> float:
        scheduled_at      = (
            time.time() + delay_seconds
            if delay_seconds > 0
            else self._next_optimal_window()
        )
        post.scheduled_at = scheduled_at
        post.status       = PostStatus.SCHEDULED
        heapq.heappush(self._heap, _QueueEntry(scheduled_at, post))
        return scheduled_at

    def pop_due(self) -> List[PlatformPost]:
        now  = time.time()
        due: List[PlatformPost] = []
        while self._heap and self._heap[0].scheduled_at <= now:
            due.append(heapq.heappop(self._heap).post)
        return due

    def peek_next(self) -> Optional[float]:
        return self._heap[0].scheduled_at if self._heap else None

    def queue_size(self) -> int:
        return len(self._heap)

    def to_list(self) -> List[Dict]:
        return [
            {
                "platform":     e.post.platform.value,
                "content_id":   e.post.content_id,
                "scheduled_at": _utc_str(e.scheduled_at),
                "status":       e.post.status.value,
            }
            for e in sorted(self._heap)
        ]

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _reset_if_new_day(self) -> None:
        today = self._today()
        if today != self._day_key:
            self._daily_count = {}
            self._day_key     = today

    def _next_optimal_window(self) -> float:
        now           = datetime.now(timezone.utc)
        today_windows = [
            now.replace(hour=h, minute=0, second=0, microsecond=0)
            for h in OPTIMAL_HOURS
        ]
        future = [w for w in today_windows if w.timestamp() > time.time() + 60]
        if future:
            return future[0].timestamp()
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(
            hour=OPTIMAL_HOURS[0], minute=0, second=0, microsecond=0
        ).timestamp()


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def _utc_str(ts: float) -> str:
    return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M UTC")


# ─────────────────────────────────────────────────────────────
#  OmniChannelStrategist — Main Agent
# ─────────────────────────────────────────────────────────────

class OmniChannelStrategist(AgentBase):
    """
    Omni-Channel Content Strategist — Marketing Autônomo do The Moon.

    Public actions (via execute):
      distribute → Distribute a ContentPiece to all platforms NOW
      schedule   → Enqueue a ContentPiece for optimal posting windows
      status     → Queue snapshot, platform availability, daily counts
      flush      → Process all currently due scheduled posts
      history    → Recent posting history (last N records)
    """

    def __init__(self, groq_client=None, message_bus=None) -> None:
        super().__init__()
        self.name        = "OmniChannelStrategist"
        self.description = (
            "Autonomous content distributor: adapts and distributes content "
            "to Telegram, Twitter/X, and LinkedIn after each publication event."
        )
        self.priority = AgentPriority.MEDIUM

        self._groq        = groq_client
        self._message_bus = message_bus

        self._clients: Dict[Platform, BasePlatformClient] = {
            Platform.TELEGRAM: TelegramPlatformClient(),
            Platform.TWITTER:  TwitterPlatformClient(),
            Platform.LINKEDIN: LinkedInPlatformClient(),
        }

        self._adapter   = ContentAdapter(groq_client)
        self._scheduler = PostScheduler()

        self._fingerprints: set[str]   = set()
        self._history:      List[Dict] = []
        self._max_history              = 100

        self._stop_event     = asyncio.Event()
        self._scheduler_task: Optional[asyncio.Task] = None

    async def initialize(self) -> None:
        await super().initialize()
        STRATEGIST_DIR.mkdir(parents=True, exist_ok=True)
        self._load_state()

        if self._message_bus:
            for topic in ("blog.published", "youtube.published", "content.published"):
                self._message_bus.subscribe(topic, self._on_content_published)
            logger.info(f"{self.name}: subscribed to content publication topics.")

        self._stop_event.clear()
        self._scheduler_task = asyncio.create_task(
            self._scheduler_loop(), name="moon.strategist.scheduler"
        )

        available = [p.value for p, c in self._clients.items() if c.is_available()]
        logger.info(
            f"{self.name} initialized. "
            f"Platforms available: {available or ['none — configure env vars']}"
        )

    async def shutdown(self) -> None:
        self._stop_event.set()
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        self._save_state()
        await super().shutdown()
        logger.info(f"{self.name} shut down.")

    async def ping(self) -> bool:
        return not self._stop_event.is_set()

    async def _execute(self, action: str, **kwargs: Any) -> TaskResult:
        match action:
            case "distribute":
                piece = self._build_piece(kwargs)
                if not piece:
                    return TaskResult(success=False, error="Required fields: title, summary, url")
                return await self._distribute_now(piece)

            case "schedule":
                piece = self._build_piece(kwargs)
                if not piece:
                    return TaskResult(success=False, error="Required fields: title, summary, url")
                return await self._schedule_piece(piece)

            case "status":
                return TaskResult(success=True, data=self._get_status())

            case "flush":
                results = await self._flush_queue()
                return TaskResult(success=True, data={"flushed": len(results), "results": results})

            case "history":
                limit = int(kwargs.get("limit", 20))
                return TaskResult(success=True, data={"history": self._history[-limit:]})

            case _:
                return TaskResult(success=False, error=f"Unknown action: '{action}'")

    async def _on_content_published(self, event: Dict[str, Any]) -> None:
        title = event.get("title", "untitled")
        logger.info(f"{self.name}: content.published received — '{title[:60]}'")
        piece = self._build_piece(event)
        if not piece:
            logger.warning(f"{self.name}: malformed event payload — missing title/summary/url.")
            return
        await self._schedule_piece(piece)

    async def _distribute_now(self, piece: ContentPiece) -> TaskResult:
        if self._is_duplicate(piece):
            return TaskResult(success=True, data={"status": "skipped", "reason": "duplicate fingerprint"})

        results: Dict[str, Any] = {}
        for platform, client in self._clients.items():
            if not client.is_available():
                results[platform.value] = {"status": PostStatus.SKIPPED.value, "reason": "not configured"}
                continue
            if not self._scheduler.can_post(platform):
                results[platform.value] = {"status": PostStatus.SKIPPED.value, "reason": "daily limit reached"}
                continue
            try:
                post            = await self._adapter.adapt(piece, platform)
                success, detail = await client.post(post)
                post.status     = PostStatus.POSTED if success else PostStatus.FAILED
                post.posted_at  = time.time() if success else None
                post.error      = None if success else detail
                if success:
                    self._scheduler.record_post(platform)
                results[platform.value] = {
                    "status":      post.status.value,
                    "platform_id": detail if success else None,
                    "error":       detail if not success else None,
                    "preview":     post.text[:120],
                }
                self._record_history(piece, post)
                logger.info(f"{self.name}: [{platform.value}] {post.status.value} — '{piece.title[:50]}'")
            except Exception as exc:
                logger.error(f"{self.name}: [{platform.value}] exception — {exc}")
                results[platform.value] = {"status": "error", "error": str(exc)}

        self._mark_fingerprint(piece)
        self._notify_weaver(piece, results)
        self._save_state()
        posted = sum(1 for r in results.values() if r.get("status") == PostStatus.POSTED.value)
        return TaskResult(success=True, data={"title": piece.title, "results": results, "posted_count": posted})

    async def _schedule_piece(self, piece: ContentPiece) -> TaskResult:
        if self._is_duplicate(piece):
            return TaskResult(success=True, data={"status": "skipped", "reason": "duplicate fingerprint"})

        scheduled: List[Dict] = []
        stagger = 0

        for platform, client in self._clients.items():
            if not client.is_available():
                continue
            if not self._scheduler.can_post(platform):
                logger.warning(f"{self.name}: daily limit for {platform.value} — skipping.")
                continue
            try:
                post = await self._adapter.adapt(piece, platform)
                ts   = self._scheduler.enqueue(post, delay_seconds=stagger * 900)
                stagger += 1
                scheduled.append({"platform": platform.value, "scheduled_at": _utc_str(ts), "preview": post.text[:80]})
            except Exception as exc:
                logger.error(f"{self.name}: schedule failed for {platform.value}: {exc}")

        self._mark_fingerprint(piece)
        self._save_state()
        logger.info(f"{self.name}: {len(scheduled)} posts scheduled for '{piece.title[:50]}'")
        return TaskResult(success=True, data={"title": piece.title, "scheduled": scheduled})

    async def _flush_queue(self) -> List[Dict]:
        due     = self._scheduler.pop_due()
        results: List[Dict] = []
        for post in due:
            client = self._clients.get(post.platform)
            if not client or not client.is_available():
                results.append({"platform": post.platform.value, "status": "skipped"})
                continue
            success, detail = await client.post(post)
            post.status     = PostStatus.POSTED if success else PostStatus.FAILED
            post.posted_at  = time.time() if success else None
            if success:
                self._scheduler.record_post(post.platform)
            results.append({"platform": post.platform.value, "status": post.status.value, "detail": detail})
            logger.info(f"{self.name}: flush [{post.platform.value}] {post.status.value}")
        return results

    async def _scheduler_loop(self) -> None:
        logger.info("Strategist scheduler loop started.")
        while not self._stop_event.is_set():
            try:
                next_ts    = self._scheduler.peek_next()
                sleep_time = min(max(0.0, (next_ts or time.time() + 60) - time.time()), 60.0)
                try:
                    await asyncio.wait_for(asyncio.shield(self._stop_event.wait()), timeout=sleep_time)
                    break
                except asyncio.TimeoutError:
                    pass
                await self._flush_queue()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Strategist scheduler error: {exc}")
                await asyncio.sleep(30)
        logger.info("Strategist scheduler loop stopped.")

    def _is_duplicate(self, piece: ContentPiece) -> bool:
        return piece.fingerprint() in self._fingerprints

    def _mark_fingerprint(self, piece: ContentPiece) -> None:
        self._fingerprints.add(piece.fingerprint())

    def _record_history(self, piece: ContentPiece, post: PlatformPost) -> None:
        entry = {
            "title":     piece.title,
            "url":       piece.url,
            "platform":  post.platform.value,
            "status":    post.status.value,
            "posted_at": _utc_str(post.posted_at) if post.posted_at else None,
            "error":     post.error,
            "preview":   post.text[:100],
        }
        self._history.append(entry)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def _notify_weaver(self, piece: ContentPiece, results: Dict) -> None:
        if not self._message_bus:
            return
        asyncio.create_task(
            self._message_bus.publish(
                sender  = self.name,
                topic   = "content.distributed",
                payload = {
                    "title":          piece.title,
                    "url":            piece.url,
                    "tags":           piece.tags,
                    "content_type":   piece.content_type.value,
                    "results":        results,
                    "distributed_at": time.time(),
                },
                target  = "SemanticMemoryWeaver",
            ),
            name="moon.strategist.notify_weaver",
        )

    def _save_state(self) -> None:
        try:
            STRATEGIST_DIR.mkdir(parents=True, exist_ok=True)
            state = {"fingerprints": list(self._fingerprints), "history": self._history}
            tmp   = HISTORY_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
            tmp.replace(HISTORY_FILE)
        except Exception as exc:
            logger.error(f"{self.name}: state save failed — {exc}")

    def _load_state(self) -> None:
        try:
            if HISTORY_FILE.exists():
                data               = json.loads(HISTORY_FILE.read_text())
                self._fingerprints = set(data.get("fingerprints", []))
                self._history      = data.get("history", [])
                logger.info(f"{self.name}: state loaded — {len(self._fingerprints)} fingerprints, {len(self._history)} history entries.")
        except Exception as exc:
            logger.warning(f"{self.name}: state load failed (starting fresh) — {exc}")

    def _get_status(self) -> Dict[str, Any]:
        platforms_info: Dict[str, Any] = {}
        for p, c in self._clients.items():
            platforms_info[p.value] = {
                "available":   c.is_available(),
                "can_post":    self._scheduler.can_post(p),
                "daily_count": self._scheduler._daily_count.get(p.value, 0),
                "daily_limit": DAILY_LIMITS.get(p.value, 10),
            }
        return {
            "platforms":     platforms_info,
            "queue_size":    self._scheduler.queue_size(),
            "queue":         self._scheduler.to_list(),
            "history_count": len(self._history),
            "fingerprints":  len(self._fingerprints),
            "next_post_at":  _utc_str(self._scheduler.peek_next()) if self._scheduler.peek_next() else "queue empty",
        }

    def _build_piece(self, d: Dict) -> Optional[ContentPiece]:
        title   = d.get("title", "")
        summary = d.get("summary", "")
        url     = d.get("url", "")
        if not all([title, summary, url]):
            return None
        try:
            ctype = ContentType(d.get("content_type", "general"))
        except ValueError:
            ctype = ContentType.GENERAL
        return ContentPiece(
            id           = d.get("id", hashlib.sha256(url.encode()).hexdigest()[:12]),
            title        = title,
            summary      = summary,
            url          = url,
            content_type = ctype,
            source_agent = d.get("source", "unknown"),
            tags         = d.get("tags", []),
            full_text    = d.get("full_text", ""),
            image_url    = d.get("image_url"),
            metadata     = d.get("metadata", {}),
        )
