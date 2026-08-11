"""Autonomous generation scheduler."""

import asyncio
import concurrent.futures
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from trappist_auto_bot.config import Config
from trappist_auto_bot.crypto_prices import PriceProviderError, fetch_prices
from trappist_auto_bot.fear_greed import build_caption as build_fear_greed_caption
from trappist_auto_bot.fear_greed import create_gauge_image, fetch_index
from trappist_auto_bot.burn_counter import BurnCounter
from trappist_auto_bot.formatting import (
    build_caption,
    build_prompt_from_article,
    visual_score,
)
from trappist_auto_bot.image.generator import TrappistImageGenerator
from trappist_auto_bot.image.pollinations_generator import PollinationsError, PollinationsImageGenerator
from trappist_auto_bot.image.wavespeed_generator import WaveSpeedError, WaveSpeedImageGenerator
from trappist_auto_bot.price_poster import post_price_update
from trappist_auto_bot.translation import generate_price_hashtags
from trappist_auto_bot.rss.fetcher import RssFetcher
from trappist_auto_bot.storage.db import Database
from trappist_auto_bot.telegram.poster import TelegramPoster
from trappist_auto_bot.utils.logger import get_logger
from trappist_auto_bot.wallet import WalletService
from trappist_auto_bot.x402.client import X402Error

# Cycles for the 2h/4h price watch posts.
PRICE_CYCLES = [
    ["BTC", "CSPR", "DOGE"],
    ["ETH", "ALGO", "SOL"],
]

logger = get_logger(__name__)


class GenerationScheduler:
    """Run the autonomous image-generation loop."""

    def __init__(
        self,
        config: Config,
        generator: TrappistImageGenerator | WaveSpeedImageGenerator | PollinationsImageGenerator,
        poster: TelegramPoster,
        fetcher: RssFetcher,
        database: Database,
        wallet_service: WalletService | None = None,
        summarize: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.config = config
        self.generator = generator
        self.poster = poster
        self.fetcher = fetcher
        self.db = database
        self.burn_counter = BurnCounter(
            database=database,
            poster=poster,
            generator=generator if isinstance(generator, TrappistImageGenerator) else None,
            milestone_interval=config.burn_update_every_n_images,
            logo_path=config.logo_path,
        )
        self.wallet = wallet_service or WalletService(
            casper_public_key=config.wallet_public_key,
            solana_public_key=config.solana_public_key,
            node_url=config.casper_node_url,
        )
        self.summarize = summarize

    async def run_once(self) -> list[dict[str, Any]]:
        """Execute a single generation cycle."""
        results: list[dict[str, Any]] = []

        # Optional Fear & Greed post (max once per hour, cheap, no Trappist payment).
        if getattr(self.config, "post_fear_greed", True):
            try:
                await self._maybe_post_fear_greed()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Fear & Greed post failed: %s", exc)

        # Balance check
        if self.config.min_balance_motes:
            has_balance = await asyncio.get_event_loop().run_in_executor(
                None,
                self.wallet.has_sufficient_casper_balance,
                self.config.min_balance_motes,
            )
            if not has_balance:
                logger.error(
                    "Casper balance below minimum (%s motes). Skipping cycle.",
                    self.config.min_balance_motes,
                )
                return results

        # Budget check
        if self.config.daily_budget_motes:
            spent = self.db.daily_spend_motes()
            if spent >= self.config.daily_budget_motes:
                logger.warning(
                    "Daily budget exhausted (%s / %s motes). Skipping cycle.",
                    spent,
                    self.config.daily_budget_motes,
                )
                return results

        # Determine articles
        if self.config.use_rss_prompts:
            articles = self.fetcher.get_articles(
                limit=self.config.max_articles_per_cycle,
                database_path=self.config.database_path,
            )
        else:
            articles = [
                {"title": p.strip()}
                for p in self.config.fallback_prompts.split(",")
                if p.strip()
            ][: self.config.max_articles_per_cycle]

        logger.info("Starting cycle with %s article(s)", len(articles))

        image_every = self.config.image_every_n_articles
        for index, article in enumerate(articles, start=1):
            # image_every=0 -> text-only (no images, no cost)
            # image_every=1 -> every article illustrated
            # image_every=3 -> 1 image every 3 articles, etc.
            with_image = image_every > 0 and ((index - 1) % image_every) == 0
            try:
                result = await self._generate_and_post(article, with_image=with_image)
                results.append(result)
                # Small delay between posts to avoid hammering Telegram
                await asyncio.sleep(10)
            except (X402Error, WaveSpeedError, PollinationsError) as exc:
                logger.error("Generation failed for article '%s': %s", article.get("title", ""), exc)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unexpected error for article '%s': %s", article.get("title", ""), exc)

        return results

    async def _generate_and_post(
        self, article: dict[str, Any], *, with_image: bool = True
    ) -> dict[str, Any]:
        """Generate one image (or text-only) and post it to Telegram."""
        prompt = build_prompt_from_article(article)

        # Summarize article for the caption (blocking, run in executor)
        if self.summarize:
            loop = asyncio.get_event_loop()
            translation = await loop.run_in_executor(
                None, self.summarize, article
            )
        else:
            translation = {}

        caption_en = build_caption(article, translation, lang="en")
        caption_fr = build_caption(article, translation, lang="fr")

        if not with_image:
            logger.info("Posting text-only for: %s", article.get("title", ""))
            telegram_result = await self.poster.post_text(
                caption_en=caption_en,
                caption_fr=caption_fr,
            )
            return {
                "prompt": prompt,
                "image_url": "",
                "caption": caption_en,
                "telegram_message_id": telegram_result.get("message_id"),
            }

        logger.info("Generating image for: %s", prompt)

        if self.config.image_backend in ("wavespeed", "pollinations"):
            api_response = await asyncio.get_event_loop().run_in_executor(
                None, self.generator.generate, prompt
            )
            image_url = api_response.get("imageUrl") or api_response.get("url", "")
            amount_motes = 0
            cost_usd = "0"
            cost_cspr = "0"
            pay_to = ""
        else:
            # x402 paid flow via TrappistAI
            generation_result = await asyncio.get_event_loop().run_in_executor(
                None, self.generator.generate, prompt
            )
            api_response = generation_result["api_response"]
            payment = generation_result["payment_details"]
            image_url = api_response.get("imageUrl") or api_response.get("url", "")
            amount_motes = payment.amount_motes or 0
            cost_usd = str(payment.cost_usd or "")
            cost_cspr = str(payment.cost_cspr or "")
            pay_to = payment.pay_to or ""

        if not image_url:
            raise X402Error(f"No image URL in response: {api_response}")

        telegram_result = await self.poster.post_image(
            image_url=image_url,
            caption_en=caption_en,
            caption_fr=caption_fr,
            add_logo=self.config.add_logo,
            logo_path=self.config.logo_path,
        )

        # Persist
        self.db.record_generation(
            prompt=prompt,
            image_url=image_url,
            amount_motes=amount_motes,
            cost_usd=cost_usd,
            cost_cspr=cost_cspr,
            pay_to=pay_to,
            telegram_message_id=telegram_result.get("message_id"),
        )

        # Track CSPR burned for paid TrappistAI (x402) generations.
        if amount_motes > 0 and getattr(self.config, "post_burn_updates", True):
            images, burned = self.burn_counter.record_generation()
            await self.burn_counter.maybe_post_milestone(images, burned)

        # Mark RSS link as posted only after a successful Telegram post.
        if article.get("link"):
            RssFetcher.mark_article_posted(
                article["link"], self.config.database_path
            )

        return {
            "prompt": prompt,
            "image_url": image_url,
            "caption": caption_en,
            "telegram_message_id": telegram_result["message_id"],
            "text_only": not with_image,
        }

    async def _maybe_post_fear_greed(self, force: bool = False) -> dict[str, Any] | None:
        """Fetch and post the Fear & Greed index image, at most once every 3 hours.

        Args:
            force: If True, ignore the three-hour throttle. Useful on first boot.
        """
        now = datetime.utcnow()
        cooldown_seconds = 3 * 3600
        if not force:
            last_raw = self.db.get_state("last_fear_greed_post")
            if last_raw:
                try:
                    last = datetime.fromisoformat(last_raw)
                    if (now - last).total_seconds() < cooldown_seconds:
                        logger.info("Fear & Greed already posted within the last 3 hours")
                        return None
                except ValueError:
                    pass

        data = await asyncio.get_event_loop().run_in_executor(None, fetch_index)
        image_bytes = await asyncio.get_event_loop().run_in_executor(
            None,
            create_gauge_image,
            data,
            self.config.logo_path,
            str(Path(self.config.logo_path).parent / "telegram-logo.png")
            if self.config.logo_path
            else None,
            "@piranewz",
        )
        caption = build_fear_greed_caption(data)
        result = await self.poster.post_image_bytes(
            image_bytes=image_bytes,
            caption_en=caption,
            add_logo=False,
            logo_path="",
        )
        self.db.set_state("last_fear_greed_post", now.isoformat())
        logger.info("Posted Fear & Greed index: %s", data.get("value"))
        return {"type": "fear_greed", "value": data.get("value"), **result}

    async def run_forever(self) -> None:
        """Run the scheduler in queued mode (matches tele1000 architecture).

        Two concurrent coroutines:
        - rss_scheduler(): fetches RSS every POST_INTERVAL_MINUTES and pushes
          new articles into an async queue.
        - article_processor(): consumes the queue continuously, posting one
          article every DELAY_BETWEEN_POSTS seconds. Image generation is
          serialized behind a lock; if an image is already being generated,
          the article is posted as text-only.
        """
        interval = self.config.post_interval_minutes
        delay = self.config.delay_between_posts
        logger.info(
            "Scheduler started (queued mode). RSS check every %s min, post delay %s s",
            interval,
            delay,
        )

        self._article_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._image_lock = asyncio.Lock()
        self._posted_ids: set[str] = set()
        self._cycle_count = 0
        self._first_rss_cycle = True

        await asyncio.gather(
            self._rss_scheduler(interval),
            self._article_processor(delay),
            self._price_scheduler(),
            return_exceptions=True,
        )

    async def _rss_scheduler(self, interval_minutes: int) -> None:
        """Fetch RSS feeds periodically and add new articles to the queue."""
        while True:
            try:
                logger.info("RSS fetch cycle starting...")

                # Optional Fear & Greed on its own cadence (not blocking).
                # On the first cycle we force-post it so a redeploy does not
                # get blocked by the persisted "posted within the last hour" state.
                if getattr(self.config, "post_fear_greed", True):
                    try:
                        await self._maybe_post_fear_greed(force=self._first_rss_cycle)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Fear & Greed post failed: %s", exc)

                # Post an initial burn update on the very first cycle so the
                # channel sees the milestone message right away.
                if self._first_rss_cycle and getattr(self.config, "post_burn_updates", True):
                    try:
                        await self._maybe_post_initial_burn_update()
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Initial burn update failed: %s", exc)

                self._first_rss_cycle = False

                raw_articles = self.fetcher.get_articles(
                    limit=self.config.max_articles_per_cycle,
                    database_path=self.config.database_path,
                )

                articles = []
                for article in raw_articles:
                    aid = article.get("link") or article.get("title", "")
                    if aid in self._posted_ids:
                        continue
                    articles.append(article)
                    self._posted_ids.add(aid)

                # Choose one article to illustrate in this cycle; the rest are text-only.
                illustrated = self._select_article_to_illustrate(articles)
                for article in articles:
                    article["_illustrate_this_cycle"] = article is illustrated

                for article in articles:
                    await self._article_queue.put(article)

                if articles:
                    logger.info(
                        "%s article(s) added to queue (queue size: %s); illustrate=%s",
                        len(articles),
                        self._article_queue.qsize(),
                        illustrated.get("title", "")[:50] if illustrated else "none",
                    )
                else:
                    logger.info("No new articles to add")

                self._cycle_count += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("RSS scheduler error: %s", exc)

            logger.info("Next RSS check in %s minutes", interval_minutes)
            await asyncio.sleep(interval_minutes * 60)

    async def _article_processor(self, delay_seconds: int) -> None:
        """Consume the article queue continuously, one post at a time."""
        while True:
            article = await self._article_queue.get()
            try:
                await self._process_single_article(article)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Error processing article '%s': %s",
                    article.get("title", ""),
                    exc,
                )
            finally:
                self._article_queue.task_done()

            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)

    async def _price_scheduler(self) -> None:
        """Post a crypto price update every N hours, alternating coin cycles.

        Posts immediately on startup so the channel sees a price update right
        away, then waits for the configured interval before the next cycle.
        """
        interval_hours = getattr(self.config, "price_post_interval_hours", 2)
        interval_seconds = interval_hours * 3600
        cycle_index = 0

        while True:
            symbols = PRICE_CYCLES[cycle_index % len(PRICE_CYCLES)]
            cycle_index += 1
            try:
                cmc_key = getattr(self.config, "cmc_api_key", "")
                prices = fetch_prices(symbols, cmc_api_key=cmc_key)

                hashtags = await asyncio.get_event_loop().run_in_executor(
                    None,
                    generate_price_hashtags,
                    symbols,
                    getattr(self.config, "groq_api_key", ""),
                )

                await post_price_update(
                    self.poster,
                    prices,
                    logo_path=self.config.logo_path,
                    hashtags=hashtags,
                )
                logger.info("Posted price update for %s", ", ".join(symbols))
            except PriceProviderError as exc:
                logger.warning("Price update failed: %s", exc)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unexpected error posting price update: %s", exc)

            await asyncio.sleep(interval_seconds)

    def _select_article_to_illustrate(
        self, articles: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Pick the one article that will receive an image this cycle.

        Selection alternates each cycle between random and visual-score so the
        feed never feels robotic.
        """
        if not articles:
            return None

        # Alternate: even cycles -> random, odd cycles -> best visual score.
        if self._cycle_count % 2 == 0:
            logger.info("Selecting illustrated article by random choice")
            return random.choice(articles)

        logger.info("Selecting illustrated article by visual score")
        scored = [(visual_score(a.get("title", "")), i, a) for i, a in enumerate(articles)]
        scored.sort(reverse=True)
        return scored[0][2]

    async def _process_single_article(self, article: dict[str, Any]) -> None:
        """Translate, generate image if possible, and post one article."""
        logger.info(
            "Processing: %s... (queue: %s remaining)",
            article.get("title", "")[:50],
            self._article_queue.qsize(),
        )

        # In queued mode we illustrate exactly one article per RSS cycle.
        # image_every_n_articles is ignored here; only the cycle flag matters.
        attempt_image = article.pop("_illustrate_this_cycle", False)

        # If the image generator is busy, post text-only to keep the flow.
        with_image = False
        if attempt_image and not self._image_lock.locked():
            async with self._image_lock:
                try:
                    await self._generate_and_post(article, with_image=True)
                    with_image = True
                    logger.info("Posted with image: %s", article.get("title", ""))
                except (X402Error, WaveSpeedError, PollinationsError) as exc:
                    logger.warning(
                        "Image generation failed for '%s': %s. Falling back to text.",
                        article.get("title", ""),
                        exc,
                    )

        if not with_image:
            await self._generate_and_post(article, with_image=False)
            logger.info("Posted text-only: %s", article.get("title", ""))

    async def _maybe_post_initial_burn_update(self) -> dict[str, Any] | None:
        """Post a burn update immediately on first boot.

        Piranewz has already burned more than 5 CSPR historically, so we seed
        the counter at 10 images / 1 CSPR. The next milestone will be at 20
        images / 2 CSPR, and so on.
        """
        images, burned = self.burn_counter.get_stats()
        logger.info("Initial burn update check: %s images, %s $CSPR burned", images, burned)
        if images < 10:
            # Seed the counter so the first burn post shows at least 1 CSPR burned.
            needed = 10 - images
            logger.info("Seeding burn counter by %s to reach 10", needed)
            for _ in range(needed):
                self.db.increment_burn_counter()
            images, burned = self.burn_counter.get_stats()
            logger.info("Seeded burn counter at %s images, %s $CSPR burned", images, burned)

        logger.info("Posting initial burn update: %s images, %s $CSPR burned", images, burned)
        return await self.burn_counter.post_burn_update(images, burned)
