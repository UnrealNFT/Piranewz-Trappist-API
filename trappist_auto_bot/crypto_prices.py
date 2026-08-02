"""Fetch crypto prices from multiple providers with fallback."""

import time
from typing import Any

import requests

from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)

# Mapping from display symbol to provider-specific ids.
COIN_IDS = {
    "BTC": {"coingecko": "bitcoin", "cmc": "1", "cryptocompare": "BTC", "kraken": "XXBTZUSD"},
    "ETH": {"coingecko": "ethereum", "cmc": "1027", "cryptocompare": "ETH", "kraken": "XETHZUSD"},
    "SOL": {"coingecko": "solana", "cmc": "5426", "cryptocompare": "SOL", "kraken": "SOLUSD"},
    "ADA": {"coingecko": "cardano", "cmc": "2010", "cryptocompare": "ADA", "kraken": "ADAUSD"},
    "DOGE": {"coingecko": "dogecoin", "cmc": "74", "cryptocompare": "DOGE", "kraken": "XDGUSD"},
    "ALGO": {"coingecko": "algorand", "cmc": "4030", "cryptocompare": "ALGO", "kraken": "ALGOUSD"},
    "CSPR": {"coingecko": "casper-network", "cmc": "5899", "cryptocompare": "CSPR", "kraken": "CSPRUSD"},
}


class PriceProviderError(Exception):
    """Raised when a price provider fails."""


def fetch_prices(
    symbols: list[str], cmc_api_key: str = ""
) -> dict[str, dict[str, Any]]:
    """Fetch USD price and 24h change for *symbols*, trying providers in order.

    Order:
        1. CoinGecko (free, no key)
        2. CoinMarketCap (requires CMC_API_KEY)
        3. CryptoCompare (free)
    """
    providers = [
        ("coingecko", lambda s: _fetch_coingecko(s)),
        ("kraken", lambda s: _fetch_kraken(s)),
    ]
    if cmc_api_key:
        providers.append(("coinmarketcap", lambda s: _fetch_cmc(s, cmc_api_key)))
    providers.append(("cryptocompare", lambda s: _fetch_cryptocompare(s)))

    last_error: Exception | None = None
    for name, provider in providers:
        try:
            logger.info("Fetching prices from %s", name)
            result = provider(symbols)
            if result:
                logger.info("Prices fetched from %s", name)
                return result
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("Price provider %s failed: %s", name, exc)

    raise PriceProviderError(f"All price providers failed: {last_error}")


def _fetch_coingecko(symbols: list[str]) -> dict[str, dict[str, Any]]:
    ids = ",".join(COIN_IDS[s]["coingecko"] for s in symbols if s in COIN_IDS)
    if not ids:
        return {}
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        f"?ids={ids}&vs_currencies=usd&include_24hr_change=true"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    result: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        cid = COIN_IDS.get(symbol, {}).get("coingecko")
        entry = data.get(cid)
        if entry:
            result[symbol] = {
                "usd": float(entry.get("usd", 0)),
                "change_24h": float(entry.get("usd_24h_change", 0)),
            }
    return result


def _fetch_cmc(symbols: list[str], api_key: str) -> dict[str, dict[str, Any]]:
    ids = ",".join(COIN_IDS[s]["cmc"] for s in symbols if s in COIN_IDS)
    if not ids:
        return {}
    url = "https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest"
    headers = {"X-CMC_PRO_API_KEY": api_key, "Accept": "application/json"}
    params = {"id": ids, "convert": "USD"}
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    result: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        cmc_id = COIN_IDS.get(symbol, {}).get("cmc")
        quote = data.get("data", {}).get(cmc_id, {}).get("quote", {}).get("USD", {})
        if quote:
            result[symbol] = {
                "usd": float(quote.get("price", 0)),
                "change_24h": float(quote.get("percent_change_24h", 0)),
            }
    return result


def _fetch_kraken(symbols: list[str]) -> dict[str, dict[str, Any]]:
    pairs = ",".join(COIN_IDS[s]["kraken"] for s in symbols if s in COIN_IDS)
    if not pairs:
        return {}
    url = f"https://api.kraken.com/0/public/Ticker?pair={pairs}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise PriceProviderError(f"Kraken error: {data['error']}")

    result: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        pair = COIN_IDS.get(symbol, {}).get("kraken")
        ticker = data.get("result", {}).get(pair, {})
        if ticker:
            last_trade = ticker.get("c", [0])[0]
            open_price = ticker.get("o", 0)
            last = float(last_trade) if last_trade else 0
            open_p = float(open_price) if open_price else 0
            change = ((last - open_p) / open_p * 100) if open_p else 0
            result[symbol] = {"usd": last, "change_24h": change}
    return result


def _fetch_cryptocompare(symbols: list[str]) -> dict[str, dict[str, Any]]:
    fsyms = ",".join(COIN_IDS[s]["cryptocompare"] for s in symbols if s in COIN_IDS)
    if not fsyms:
        return {}
    price_url = (
        "https://min-api.cryptocompare.com/data/pricemulti"
        f"?fsyms={fsyms}&tsyms=USD"
    )
    change_url = (
        "https://min-api.cryptocompare.com/data/pricemultifull"
        f"?fsyms={fsyms}&tsyms=USD"
    )

    prices = requests.get(price_url, timeout=15).json()
    time.sleep(0.2)  # be polite with free API rate limits
    full = requests.get(change_url, timeout=15).json()

    result: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        ccmp_id = COIN_IDS.get(symbol, {}).get("cryptocompare")
        raw_price = prices.get(ccmp_id, {}).get("USD", 0)
        raw_change = full.get("RAW", {}).get(ccmp_id, {}).get("USD", {}).get("CHANGEPCT24HOUR", 0)
        if raw_price:
            result[symbol] = {
                "usd": float(raw_price),
                "change_24h": float(raw_change),
            }
    return result
