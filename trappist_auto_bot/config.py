"""Runtime configuration loaded from environment variables."""

import base64
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (one directory above this package).
load_dotenv(Path(__file__).parents[1] / ".env")



@dataclass(frozen=True)
class Config:
    """Application configuration."""

    # Telegram
    telegram_bot_token: str
    telegram_chat_id: str  # main channel (English)
    telegram_chat_id_fr: str = ""  # French channel (optional)

    # TrappistAI API
    trappist_api_url: str = "https://trappist.land"

    # AI / Image generation APIs
    groq_api_key: str = ""
    wavespeed_api_key: str = ""

    # Image generation backend:
    #   "trappist"  = x402 paid generation
    #   "wavespeed" = WaveSpeed API (free if API key available)
    #   "pollinations" = Pollinations.ai (free, no API key)
    image_backend: str = "pollinations"

    # Wallet
    wallet_public_key: str = ""
    casper_private_key_path: str = ""
    solana_private_key: str = ""
    solana_public_key: str = ""

    # Payment / signing
    signer_command: str = ""
    signer_timeout: int = 60
    signer_backend: str = "mock"
    max_payment_motes: int = 0  # 0 = disabled
    daily_budget_motes: int = 0  # 0 = unlimited
    min_balance_motes: int = 0  # 0 = disabled
    casper_node_url: str = "https://node.mainnet.casper.network/rpc"

    # Generation strategy
    generation_interval_minutes: int = 60  # legacy single-cycle mode
    post_interval_minutes: int = 5  # queued mode: RSS check interval
    rss_sources: str = ""  # comma-separated URLs
    max_articles_per_cycle: int = 3  # queued mode: articles added per RSS check
    use_rss_prompts: bool = True
    fallback_prompts: str = ""  # comma-separated fallback prompts

    # Image options
    add_logo: bool = False
    logo_path: str = ""

    # Fear & Greed index posting
    post_fear_greed: bool = True

    # Crypto price update schedule (hours between posts).
    price_post_interval_hours: int = 2

    # CoinMarketCap API key (optional, used as price provider fallback).
    cmc_api_key: str = ""

    # Image ratio: generate an image for every Nth article in the cycle.
    # 0 = text-only, no images (no cost).
    # 1 = every article illustrated.
    # 3 = one image every 3 articles, etc.
    image_every_n_articles: int = 3

    # Delay between consecutive posts when running in queued mode (seconds).
    delay_between_posts: int = 60

    # Storage
    database_path: str = "data/bot.db"

    # Logging
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        casper_private_key_path = _resolve_casper_private_key_path(
            os.environ.get("CASPER_PRIVATE_KEY_PATH", ""),
            os.environ.get("CASPER_PRIVATE_KEY_BASE64", ""),
        )
        return cls(
            telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            telegram_chat_id=os.environ["TELEGRAM_CHAT_ID"],
            telegram_chat_id_fr=os.environ.get("TELEGRAM_CHAT_ID_FR", ""),
            trappist_api_url=os.environ.get("TRAPIST_API_URL", "https://trappist.land"),
            groq_api_key=os.environ.get("GROQ_API_KEY", ""),
            wavespeed_api_key=os.environ.get("WAVESPEED_API_KEY", ""),
            image_backend=os.environ.get("IMAGE_BACKEND", "pollinations").lower(),
            wallet_public_key=os.environ.get("WALLET_PUBLIC_KEY", os.environ.get("CASPER_PUBLIC_KEY", "")),
            casper_private_key_path=casper_private_key_path,
            solana_private_key=os.environ.get("SOLANA_PRIVATE_KEY", ""),
            solana_public_key=os.environ.get("SOLANA_PUBLIC_KEY", ""),
            signer_command=os.environ.get("SIGNER_COMMAND", ""),
            signer_timeout=int(os.environ.get("SIGNER_TIMEOUT", "60")),
            signer_backend=os.environ.get("SIGNER_BACKEND", "mock").lower(),
            max_payment_motes=int(os.environ.get("MAX_PAYMENT_MOTES", "0")),
            daily_budget_motes=int(os.environ.get("DAILY_BUDGET_MOTES", "0")),
            min_balance_motes=int(os.environ.get("MIN_BALANCE_MOTES", "0")),
            casper_node_url=os.environ.get(
                "CASPER_NODE_URL", "https://node.mainnet.casper.network/rpc"
            ),

            generation_interval_minutes=int(
                os.environ.get("GENERATION_INTERVAL_MINUTES", "60")
            ),
            post_interval_minutes=int(
                os.environ.get("POST_INTERVAL_MINUTES", "5")
            ),
            rss_sources=os.environ.get(
                "RSS_SOURCES",
                ",".join(
                    [
                        "https://cointelegraph.com/rss",
                        "https://www.coindesk.com/arc/outboundfeeds/rss/",
                        "https://decrypt.co/feed",
                        "https://www.theblock.co/rss.xml",
                        "https://bitcoinmagazine.com/.rss/full/",
                        "https://cryptoslate.com/feed/",
                        "https://bitcoinist.com/feed/",
                        "https://www.newsbtc.com/feed/",
                        "https://cryptonews.com/news/feed/",
                        "https://news.bitcoin.com/feed/",
                        "https://beincrypto.com/feed/",
                        "https://ambcrypto.com/feed/",
                        "https://u.today/rss",
                        "https://www.theguardian.com/technology/cryptocurrencies/rss",
                        "https://blockchain.news/RSS",
                        "https://cryptodaily.co.uk/feed",
                        "https://coinjournal.net/feed/",
                        "https://feeds.reuters.com/reuters/topNews",
                        "http://rss.cnn.com/rss/cnn_topstories.rss",
                        "https://news.google.com/rss",
                    ]
                ),
            ),
            max_articles_per_cycle=int(os.environ.get("MAX_ARTICLES_PER_CYCLE", "3")),
            use_rss_prompts=os.environ.get("USE_RSS_PROMPTS", "true").lower()
            in ("1", "true", "yes"),
            fallback_prompts=os.environ.get(
                "FALLBACK_PROMPTS",
                "a futuristic crypto city at night,"
                "a cyberpunk bull holding a bitcoin coin",
            ),
            add_logo=os.environ.get("ADD_LOGO", "false").lower()
            in ("1", "true", "yes"),
            logo_path=os.environ.get("LOGO_PATH", ""),
            post_fear_greed=os.environ.get("POST_FEAR_GREED", "true").lower()
            in ("1", "true", "yes"),
            price_post_interval_hours=int(
                os.environ.get("PRICE_POST_INTERVAL_HOURS", "2")
            ),
            cmc_api_key=os.environ.get("CMC_API_KEY", ""),
            image_every_n_articles=int(
                os.environ.get("IMAGE_EVERY_N_ARTICLES", "3")
            ),
            delay_between_posts=int(
                os.environ.get("DELAY_BETWEEN_POSTS", "60")
            ),
            database_path=os.environ.get("DATABASE_PATH", "data/bot.db"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )


def _resolve_casper_private_key_path(path: str, base64_key: str) -> str:
    """Return the private key path, writing a base64-encoded key to disk if needed.

    Render (and similar hosts) do not always support secret files, so users can
    pass the PEM contents as CASPER_PRIVATE_KEY_BASE64. We decode it and write
    it to a temporary file that the local signer can read.
    """
    if path and Path(path).exists():
        return path
    if not base64_key:
        return path
    try:
        raw = base64.b64decode(base64_key)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("CASPER_PRIVATE_KEY_BASE64 is not valid base64") from exc

    if not raw.startswith(b"-----BEGIN"):
        raise ValueError("CASPER_PRIVATE_KEY_BASE64 does not look like a PEM key")

    write_path = path or "/tmp/casper_key.pem"
    Path(write_path).parent.mkdir(parents=True, exist_ok=True)
    Path(write_path).write_bytes(raw)
    return write_path
