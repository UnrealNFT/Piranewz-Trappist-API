"""Fetch crypto news from RSS feeds and turn headlines into image prompts."""

import random
from typing import Any

import feedparser
import requests

# Shorter socket timeout so slow feeds don't block the whole cycle.
feedparser.PREFERRED_XML_PARSERS = ["lxml", "xml", "drv_libxml2", "sgmllib3k"]

import re
from difflib import SequenceMatcher

from trappist_auto_bot.rss.cleaner import clean_content
from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)

# Keywords used to keep only crypto-related articles and drop politics/war noise.
CRYPTO_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto", "blockchain", "nft",
    "defi", "web3", "token", "coin", "altcoin", "mining", "wallet",
    "exchange", "binance", "coinbase", "solana", "cardano", "xrp",
    "ripple", "polkadot", "avalanche", "polygon", "chainlink", "uniswap",
    "stablecoin", "usdt", "usdc", "satoshi", "hash", "node", "consensus",
    "proof of stake", "proof of work", "smart contract", "metaverse",
    "dapp", "dao", "yield", "staking", "airdrop", "ico", "ido", "dex",
    "cex", "layer 2", "rollup", "erc", "brc", "memo", "ledger",
]

EXCLUDE_KEYWORDS = [
    "republican", "democrat", "election", "trump", "biden", "congress vote",
    "senate vote", "bombing", "missile", "iran", "israel", "palestine",
    "ukraine", "russia", "war", "military", "islamophobia", "racist",
]

DEFAULT_FALLBACK_PROMPTS = [
    "a futuristic crypto city glowing at night",
    "a cyberpunk bull holding a glowing bitcoin coin",
    "an astronaut standing on a moon made of ethereum coins",
    "a neon trading desk with floating charts and candles",
]

# Source list ported from the original tele1000 / @piranewz bot.
DEFAULT_CRYPTO_RSS_SOURCES = [
    # Major crypto outlets
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
    # Mainstream / tech
    "https://www.theguardian.com/technology/cryptocurrencies/rss",
    "https://www.forbes.com/crypto-blockchain/feed/",
    "https://www.cnbc.com/id/10000115/device/rss/rss.html",
    "https://blockchain.news/RSS",
    "https://cryptodaily.co.uk/feed",
    "https://coinjournal.net/feed/",
    "https://feeds.reuters.com/reuters/topNews",
    "http://rss.cnn.com/rss/cnn_topstories.rss",
    "https://news.google.com/rss",
]


class RssFetcher:
    """Fetch RSS headlines and convert them into image generation prompts."""

    def __init__(self, feed_urls: list[str]) -> None:
        self.feed_urls = [url.strip() for url in feed_urls if url.strip()]

    def fetch_headlines(self, limit: int = 5) -> list[dict[str, Any]]:
        """Return the latest cleaned crypto headlines from all configured feeds."""
        headlines: list[dict[str, Any]] = []
        for url in self.feed_urls:
            try:
                logger.info("Fetching RSS feed: %s", url)
                # Fetch with a short HTTP timeout; feedparser then parses the bytes.
                resp = requests.get(url, timeout=12, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                resp.raise_for_status()
                parsed = feedparser.parse(resp.content)
                for entry in parsed.entries[:limit]:
                    title = clean_content(entry.get("title", ""))
                    summary = clean_content(entry.get("summary", ""))
                    # Skip items that are just images/galleries.
                    if len(summary.strip()) < 20 or "image" in title.lower():
                        continue
                    article = {
                        "title": title,
                        "summary": summary,
                        "link": entry.get("link", ""),
                        "source": clean_content(parsed.feed.get("title", url)),
                    }
                    if not self._is_crypto_related(article):
                        continue
                    headlines.append(article)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to parse feed %s: %s", url, exc)
        return headlines

    @staticmethod
    def _is_crypto_related(article: dict[str, Any]) -> bool:
        """Return True if the article is crypto-related and not excluded."""
        text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
        for keyword in EXCLUDE_KEYWORDS:
            if keyword in text:
                return False
        for keyword in CRYPTO_KEYWORDS:
            if keyword in text:
                return True
        return False

    @staticmethod
    def _build_prompt_from_headline(headline: dict[str, Any]) -> str:
        """Convert a news headline into an image prompt."""
        title = headline["title"].strip()
        # Simple heuristic: if the title is already evocative, use it directly
        if len(title) > 10:
            return (
                f"A dramatic cinematic illustration representing the crypto news: {title}. "
                "Cyberpunk style, neon lighting, high detail."
            )
        return random.choice(DEFAULT_FALLBACK_PROMPTS)

    def get_articles(
        self, limit: int = 3, database_path: str | None = None
    ) -> list[dict[str, Any]]:
        """Return recent RSS articles for posting, skipping duplicates."""
        headlines = self.fetch_headlines(limit=limit)
        # Dedupe identical links within the batch itself.
        seen_links: set[str] = set()
        unique_headlines = []
        for h in headlines:
            link = h.get("link", "")
            if link in seen_links:
                continue
            seen_links.add(link)
            unique_headlines.append(h)
        headlines = unique_headlines
        if not database_path:
            return headlines
        try:
            from trappist_auto_bot.storage.db import Database

            db = Database(path=database_path)
            new_headlines = []
            seen_titles: list[str] = []
            for h in headlines:
                if not h.get("link") or db.is_link_posted(h["link"]):
                    continue
                if self._is_title_duplicate(h.get("title", ""), seen_titles):
                    continue
                new_headlines.append(h)
                seen_titles.append(h["title"])
            return new_headlines[:limit]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not deduplicate articles: %s", exc)
            return headlines

    @staticmethod
    def mark_article_posted(link: str, database_path: str) -> None:
        """Mark an article link as posted after a successful Telegram post."""
        try:
            from trappist_auto_bot.storage.db import Database

            db = Database(path=database_path)
            db.record_posted_link(link)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not mark article as posted: %s", exc)

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normalize title for similarity comparison."""
        normalized = title.lower()
        normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by",
        }
        words = [w for w in normalized.split() if w not in stop_words and len(w) > 2]
        return " ".join(words)

    @classmethod
    def _title_similarity(cls, title1: str, title2: str) -> float:
        """Calculate similarity between two titles (0-1)."""
        norm1 = cls._normalize_title(title1)
        norm2 = cls._normalize_title(title2)
        if not norm1 or not norm2:
            return 0.0
        return SequenceMatcher(None, norm1, norm2).ratio()

    @classmethod
    def _is_title_duplicate(
        cls, title: str, seen_titles: list[str], threshold: float = 0.80
    ) -> bool:
        """Return True if title is similar to an already-seen title."""
        for seen in seen_titles:
            if cls._title_similarity(title, seen) >= threshold:
                return True
        return False

    def get_prompts(self, limit: int = 3) -> list[str]:
        """Return a list of image prompts derived from recent headlines."""
        headlines = self.fetch_headlines(limit=limit)
        if not headlines:
            logger.warning("No RSS headlines found, using fallback prompts")
            return random.sample(DEFAULT_FALLBACK_PROMPTS, k=min(limit, len(DEFAULT_FALLBACK_PROMPTS)))
        return [self._build_prompt_from_headline(h) for h in headlines[:limit]]


def fetch_with_requests(url: str) -> str:
    """Fallback raw RSS fetcher if feedparser has issues with a feed."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text
