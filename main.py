"""Entry point for the TrappistAI autonomous x402 image bot."""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

# Ensure the project root is on PYTHONPATH (needed for Render and other
# environments where the package is not installed).
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Debug: log what the runtime sees in the project root.
import os  # noqa: E402
print("DEBUG project root:", _PROJECT_ROOT, file=sys.stderr)
print("DEBUG cwd:", os.getcwd(), file=sys.stderr)
print("DEBUG contents:", os.listdir(_PROJECT_ROOT), file=sys.stderr)
print("DEBUG trappist dir:", os.listdir(_PROJECT_ROOT / "trappist_auto_bot") if (_PROJECT_ROOT / "trappist_auto_bot").exists() else "MISSING", file=sys.stderr)

from trappist_auto_bot.config import Config
from trappist_auto_bot.image.generator import TrappistImageGenerator
from trappist_auto_bot.rss.fetcher import RssFetcher
from trappist_auto_bot.scheduler import GenerationScheduler
from trappist_auto_bot.translation import summarize_article
from trappist_auto_bot.storage.db import Database
from trappist_auto_bot.telegram.poster import TelegramPoster
from trappist_auto_bot.utils.logger import get_logger
from trappist_auto_bot.x402.signer import (
    ExternalCommandSigner,
    LocalCasperSigner,
    MockSigner,
    Signer,
)


logger = get_logger(__name__)


def build_signer(config: Config) -> Signer:
    """Instantiate the configured signer."""
    if not config.wallet_public_key:
        raise RuntimeError("WALLET_PUBLIC_KEY or CASPER_PUBLIC_KEY is required")

    if config.signer_command:
        logger.info("Using external command signer")
        return ExternalCommandSigner(
            command=config.signer_command,
            wallet=config.wallet_public_key,
            timeout=config.signer_timeout,
        )

    if config.signer_backend == "local" and config.casper_private_key_path:
        logger.info("Using local Casper signer with key: %s", config.casper_private_key_path)
        return LocalCasperSigner(
            key_path=config.casper_private_key_path,
            wallet=config.wallet_public_key,
        )

    logger.warning("No signer configured; falling back to MockSigner")
    return MockSigner(wallet=config.wallet_public_key)


def main() -> int:
    """Run the bot."""
    parser = argparse.ArgumentParser(description="TrappistAI autonomous x402 bot")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single generation cycle and exit",
    )
    args = parser.parse_args()

    try:
        config = Config.from_env()
    except KeyError as exc:
        logger.error("Missing required environment variable: %s", exc)
        return 1

    if config.image_backend == "wavespeed":
        from trappist_auto_bot.image.wavespeed_generator import WaveSpeedImageGenerator

        if not config.wavespeed_api_key:
            raise RuntimeError("WAVESPEED_API_KEY is required when IMAGE_BACKEND=wavespeed")
        generator = WaveSpeedImageGenerator(api_key=config.wavespeed_api_key)
    elif config.image_backend == "pollinations":
        from trappist_auto_bot.image.pollinations_generator import PollinationsImageGenerator

        generator = PollinationsImageGenerator()
    else:
        signer = build_signer(config)
        generator = TrappistImageGenerator(
            api_url=config.trappist_api_url,
            wallet_public_key=config.wallet_public_key,
            signer=signer,
            max_payment_motes=config.max_payment_motes,
        )

    # Telegram is optional for now: create a no-op poster if token/chat is a placeholder.
    if (
        config.telegram_bot_token
        and not config.telegram_bot_token.startswith("123456:")
        and config.telegram_chat_id
        and not config.telegram_chat_id.startswith("-100123456")
    ):
        poster = TelegramPoster(
            bot_token=config.telegram_bot_token,
            chat_id=config.telegram_chat_id,
            chat_id_fr=config.telegram_chat_id_fr,
        )
    else:
        from trappist_auto_bot.telegram.poster import NoOpPoster

        poster = NoOpPoster()

    fetcher = RssFetcher(feed_urls=config.rss_sources.split(","))
    database = Database(path=config.database_path)

    from trappist_auto_bot.wallet import WalletService

    wallet_service = WalletService(
        casper_public_key=config.wallet_public_key,
        solana_public_key=config.solana_public_key,
        node_url=config.casper_node_url,
    )

    def _summarize_with_config(article: dict[str, Any]) -> dict[str, Any]:
        return summarize_article(
            article,
            groq_api_key=config.groq_api_key,
            groq_model="llama-3.1-8b-instant",
        )

    scheduler = GenerationScheduler(
        config=config,
        generator=generator,
        poster=poster,
        fetcher=fetcher,
        database=database,
        wallet_service=wallet_service,
        summarize=_summarize_with_config,
    )

    try:
        if args.once:
            results = asyncio.run(scheduler.run_once())
            logger.info("Cycle complete: %s generation(s)", len(results))
        else:
            asyncio.run(scheduler.run_forever())
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    return 0


if __name__ == "__main__":
    sys.exit(main())
