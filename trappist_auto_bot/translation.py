"""Translate and summarize RSS articles for Telegram posts."""

import json
import re
import time
from typing import Any

import requests
from deep_translator import GoogleTranslator

from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"


def summarize_article(
    article: dict[str, Any],
    groq_api_key: str | None = None,
    groq_model: str = DEFAULT_GROQ_MODEL,
    max_retries: int = 2,
) -> dict[str, Any]:
    """Summarize an article in English with Groq API and translate to French.

    If groq_api_key is empty or Groq is unavailable, falls back to Ollama local,
    then to Google Translate.
    """
    # 1. Try Groq API
    if groq_api_key:
        for attempt in range(max_retries):
            try:
                data = _summarize_with_groq(article, groq_api_key, groq_model)
                return _translate_result(data)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                logger.warning("Groq attempt %s/%s failed: HTTP %s", attempt + 1, max_retries, status)
                # Back off longer on rate limits.
                if attempt < max_retries - 1:
                    time.sleep(5 if status == 429 else 2)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Groq attempt %s/%s failed: %s", attempt + 1, max_retries, exc)
                if attempt < max_retries - 1:
                    time.sleep(2)

    # 2. Try Ollama local as fallback
    logger.info("Groq unavailable or not configured, falling back to Ollama local")
    for attempt in range(max_retries):
        try:
            data = _summarize_with_ollama(article)
            return _translate_result(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama attempt %s/%s failed: %s", attempt + 1, max_retries, exc)
            if attempt < max_retries - 1:
                time.sleep(2)

    # 3. Fallback: translate the original title/description with Google Translate.
    logger.error("LLM summarization failed, using Google Translate fallback")
    try:
        translator = GoogleTranslator(source="auto", target="fr")
        return {
            "title_en": article["title"],
            "title_fr": translator.translate(article["title"]),
            "description_en": article.get("summary", "")[:200],
            "description_fr": translator.translate(article.get("summary", "")[:200]),
            "summary_en": article.get("summary", "")[:150],
            "summary_fr": translator.translate(article.get("summary", "")[:150]),
            "hashtags": ["#Crypto", "#News"],
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Google Translate fallback failed: %s", exc)
        return {
            "title_en": article["title"],
            "title_fr": article["title"],
            "description_en": article.get("summary", "")[:200],
            "description_fr": article.get("summary", "")[:200],
            "summary_en": article.get("summary", "")[:150],
            "summary_fr": article.get("summary", "")[:150],
            "hashtags": ["#Crypto", "#Blockchain"],
        }


def _build_prompt(article: dict[str, Any]) -> str:
    return f"""You are a professional crypto journalist. Analyze this article and create a quality Telegram post in ENGLISH.

ARTICLE:
Title: {article["title"]}
Description: {article.get("summary", "")[:500]}
Source: {article.get("source", "")}

STRICT RULES:
1. Write a catchy English title (clear, concise, engaging)
2. Write a SHORT and UNIQUE summary (2 sentences max, different from description)
3. Add a COMPLEMENTARY description (1 sentence that ADDS info, no repetition)
4. Generate 3-4 relevant crypto hashtags
5. Write as ORIGINAL content (never mention source name like "CoinTelegraph reports...")

JSON RESPONSE FORMAT (valid JSON only):
{{
    "title_en": "catchy English title",
    "description_en": "complementary info different from summary",
    "summary": "short summary in 2 sentences maximum",
    "hashtags": ["#Tag1", "#Tag2", "#Tag3"]
}}

Respond ONLY with JSON:"""


def _summarize_with_groq(
    article: dict[str, Any],
    api_key: str,
    model: str,
    url: str = "https://api.groq.com/openai/v1/chat/completions",
) -> dict[str, Any]:
    """Call Groq API and return parsed JSON fields."""
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": _build_prompt(article),
                }
            ],
            "temperature": 0.7,
            "max_tokens": 512,
        },
        timeout=60,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"].strip()

    data = _extract_json(content)
    if data is None:
        raise ValueError("No valid JSON in Groq response")

    required = ["title_en", "description_en", "summary"]
    if not all(key in data for key in required):
        raise ValueError("Missing fields in Groq response")

    if "hashtags" not in data or not data["hashtags"]:
        data["hashtags"] = ["#Crypto", "#Blockchain", "#Bitcoin"]

    return data


def _summarize_with_ollama(
    article: dict[str, Any],
    ollama_url: str = "http://localhost:11434/api/generate",
    ollama_model: str = "llama3.2:latest",
) -> dict[str, Any]:
    """Call Ollama local and return parsed JSON fields."""
    response = requests.post(
        ollama_url,
        json={
            "model": ollama_model,
            "prompt": _build_prompt(article),
            "stream": False,
            "options": {"temperature": 0.7},
        },
        timeout=120,
    )
    response.raise_for_status()
    content = response.json().get("response", "").strip()

    data = _extract_json(content)
    if data is None:
        raise ValueError("No valid JSON in Ollama response")

    required = ["title_en", "description_en", "summary"]
    if not all(key in data for key in required):
        raise ValueError("Missing fields in Ollama response")

    if "hashtags" not in data or not data["hashtags"]:
        data["hashtags"] = ["#Crypto", "#Blockchain", "#Bitcoin"]

    return data


def _translate_result(data: dict[str, Any]) -> dict[str, Any]:
    """Translate English fields to French and normalize output."""
    translator = GoogleTranslator(source="en", target="fr")
    return {
        "title_en": data["title_en"],
        "title_fr": translator.translate(data["title_en"]),
        "description_en": data["description_en"],
        "description_fr": translator.translate(data["description_en"]),
        "summary_en": data["summary"],
        "summary_fr": translator.translate(data["summary"]),
        "hashtags": data["hashtags"],
    }


def _extract_json(text: str) -> dict[str, Any] | None:
    """Try to parse the text directly, otherwise extract the first JSON object."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


DEFAULT_PRICE_HASHTAGS = [
    "#Crypto",
    "#Bitcoin",
    "#Ethereum",
    "#Casper",
    "#Algorand",
    "#Dogecoin",
    "#Solana",
    "#Altcoins",
]


def _build_hashtag_prompt(symbols: list[str], pool: list[str]) -> str:
    return f"""You are a crypto social media expert. Pick 4 to 6 relevant hashtags for a Telegram price update about {', '.join(symbols)}.

Choose from this pool (you may drop some, repeat is allowed only if really relevant):
{', '.join(pool)}

You may ADD 0 to 2 extra hashtags if they fit the current market vibe, but keep them crypto-related.

Respond ONLY with valid JSON:
{{"hashtags": ["#Tag1", "#Tag2", "#Tag3", "#Tag4"]}}
"""


def generate_price_hashtags(
    symbols: list[str],
    groq_api_key: str | None = None,
    groq_model: str = DEFAULT_GROQ_MODEL,
    ollama_url: str = "http://localhost:11434/api/generate",
    ollama_model: str = "llama3.2:latest",
) -> list[str]:
    """Generate a curated list of hashtags for a price update.

    Tries Groq first, then Ollama local, then falls back to the full fixed pool.
    """
    prompt = _build_hashtag_prompt(symbols, DEFAULT_PRICE_HASHTAGS)

    # 1. Groq
    if groq_api_key:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": groq_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 128,
                },
                timeout=30,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            data = _extract_json(content)
            if data and "hashtags" in data:
                return _normalize_hashtags(data["hashtags"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Groq hashtag generation failed: %s", exc)

    # 2. Ollama local
    try:
        response = requests.post(
            ollama_url,
            json={"model": ollama_model, "prompt": prompt, "stream": False, "options": {"temperature": 0.7}},
            timeout=60,
        )
        response.raise_for_status()
        content = response.json().get("response", "").strip()
        data = _extract_json(content)
        if data and "hashtags" in data:
            return _normalize_hashtags(data["hashtags"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ollama hashtag generation failed: %s", exc)

    # 3. Fallback
    return DEFAULT_PRICE_HASHTAGS


def _normalize_hashtags(tags: list[Any]) -> list[str]:
    """Clean and validate hashtag list."""
    cleaned: list[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            continue
        tag = tag.strip()
        if not tag.startswith("#"):
            tag = "#" + tag
        tag = re.sub(r"\s+", "", tag)
        if len(tag) > 1 and tag not in cleaned:
            cleaned.append(tag)
    return cleaned if cleaned else DEFAULT_PRICE_HASHTAGS
