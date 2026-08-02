"""Format Telegram captions and overlays in the Piranewz style."""

import random
import re
from typing import Any

# Matches the tele10001 style.
CRYPTO_EMOJIS = ["🚀", "📈", "💎", "⚡", "🌟", "🔥", "🌙", "💰"]
DEFAULT_HASHTAGS = ["#Crypto", "#Blockchain", "#Bitcoin"]


def build_caption(article: dict[str, Any], translation: dict[str, Any], lang: str = "fr") -> str:
    """Build a Telegram caption in French or English.

    @piranewz receives English captions; @piranewz_fr receives French captions.
    """
    emoji = random.choice(CRYPTO_EMOJIS)
    if lang == "fr":
        title = translation.get("title_fr") or article.get("title", "")
        summary = translation.get("summary_fr") or translation.get("summary_en", "")
        description = translation.get("description_fr") or translation.get("description_en", "")
    else:
        title = translation.get("title_en") or article.get("title", "")
        summary = translation.get("summary_en") or translation.get("summary", "")
        description = translation.get("description_en") or translation.get("description", "")

    hashtags = translation.get("hashtags", DEFAULT_HASHTAGS)

    # Truncate description to leave room for hashtags and source link.
    if len(description) > 250:
        description = description[:247] + "..."

    source_name = _clean_source_name(article.get("source", "Source"))
    article_url = article.get("link", "")
    source_link = f"[📰 {source_name}]({article_url})" if article_url else f"📰 {source_name}"

    caption = (
        f"{emoji} **{title}**\n\n"
        f"{summary}\n\n"
        f"{description}\n\n"
        f"{' '.join(hashtags)}\n\n"
        f"{source_link}"
    )
    return caption


def _clean_source_name(name: str) -> str:
    """Strip verbose taglines from RSS feed titles, e.g. 'U.Today - Actualités...'."""
    name = name.split(" - ")[0].split(" | ")[0].strip()
    name = name.split(".")[0].strip()
    return name or "Source"


def build_prompt_from_article(article: dict[str, Any]) -> str:
    """Create an image generation prompt from the article title + summary.

    The original @piranewz bot mixed the title/keywords with a dark cyberpunk
    anime suffix. Adding the cleaned summary and explicit entity keywords helps
    the model illustrate the actual article subject instead of defaulting to a
    generic Bitcoin logo.
    """
    title = article.get("title", "").strip()
    summary = article.get("summary", "").strip()
    # Pull out crypto/company/tech entities from the title to force the visual.
    entities = _extract_visual_entities(title)

    # Original @piranewz / tele1000 suffixes, cycled for visual variety.
    suffixes = [
        "dark technology anime, manga art style, glowing crypto symbols, cinematic composition, ultra detailed, 8k",
        "dark cyberpunk anime, manga art style, dramatic neon lighting, deep shadows, glowing crypto symbols, cinematic composition, ultra detailed, 8k",
        "futuristic anime, holographic data streams, sharp ink lines, glowing blockchain network, dramatic lighting, cinematic, ultra detailed, 8k",
        "dark anime fantasy, glowing thug, manga, crypto coins, mysterious atmosphere, cinematic composition, ultra detailed, 8k",
        "noir anime, manga art style, electric neon accents, deep contrast shadows, glowing crypto charts, cinematic, ultra detailed, 8k",
    ]
    suffix = _cycle_suffix(suffixes)

    parts = [p for p in [title, summary[:200], entities] if p]
    if len(title) > 10:
        return ". ".join(parts) + ". " + suffix
    return random.choice(
        [
            "a futuristic crypto city glowing at night, dark cyberpunk anime, manga art style, ultra detailed, 8k, no text",
            "a cyberpunk bull holding a glowing bitcoin coin, manga art style, dramatic neon lighting, ultra detailed, 8k, no text",
            "an astronaut standing on a moon made of ethereum coins, cyberpunk anime, deep shadows, ultra detailed, 8k, no text",
            "a neon trading desk with floating charts and candles, manga art style, glowing crypto symbols, ultra detailed, 8k, no text",
        ]
    )


def visual_score(title: str) -> int:
    """Score how visually anchorable an article title is.

    Higher score = more concrete crypto entities to illustrate.
    """
    entities = _extract_visual_entities(title)
    # Each matched entity adds a comma-separated visual phrase.
    return entities.count(",") + 1 if entities else 0


def _extract_visual_entities(title: str) -> str:
    """Extract brand/coin/entity names from the title to anchor the image."""
    known = {
        "uniswap": "Uniswap logo and decentralized exchange interface",
        "uni": "Uniswap UNI token",
        "bitcoin": "Bitcoin BTC coin",
        "btc": "Bitcoin BTC coin",
        "ethereum": "Ethereum ETH coin",
        "eth": "Ethereum ETH coin",
        "solana": "Solana SOL coin",
        "sol": "Solana SOL coin",
        "cardano": "Cardano ADA coin",
        "ada": "Cardano ADA coin",
        "xrp": "XRP Ripple coin",
        "ripple": "XRP Ripple coin",
        "polkadot": "Polkadot DOT coin",
        "dot": "Polkadot DOT coin",
        "chainlink": "Chainlink LINK coin",
        "link": "Chainlink LINK coin",
        "polygon": "Polygon MATIC coin",
        "matic": "Polygon MATIC coin",
        "avalanche": "Avalanche AVAX coin",
        "avax": "Avalanche AVAX coin",
        "bnb": "Binance BNB coin",
        "binance": "Binance",
        "coinbase": "Coinbase",
        "dogecoin": "Dogecoin DOGE",
        "doge": "Dogecoin DOGE",
        "shib": "Shiba Inu SHIB",
        "shiba": "Shiba Inu SHIB",
        "pepe": "Pepe coin",
        "stablecoin": "stablecoin",
        "tether": "Tether USDT",
        "usdt": "Tether USDT",
        "usdc": "USDC stablecoin",
        "etf": "Bitcoin ETF",
        "defi": "DeFi protocol",
        "nft": "NFT digital art",
        "coldcard": "Coldcard hardware wallet",
        "ledger": "Ledger hardware wallet",
        "metamask": "MetaMask wallet",
    }
    lower = title.lower()
    hits = []
    for key, visual in known.items():
        if key in lower and visual not in hits:
            hits.append(visual)
    return ", ".join(hits)


def _cycle_suffix(suffixes: list[str]) -> str:
    """Return the next suffix in a rotating cycle."""
    import itertools

    if not hasattr(_cycle_suffix, "_cycle"):
        _cycle_suffix._cycle = itertools.cycle(suffixes)
    return next(_cycle_suffix._cycle)


def extract_json_from_text(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from a markdown or raw text block."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        import json
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None
