"""Manually run the TrappistAI x402 media suite (the bot also runs it once at startup
when MEDIA_SUITE_ON_START=true).

Default run only fetches the 402 challenges and prints prices (no payment).
Add --pay to really pay in CSPR, and --post to publish results on Telegram.

    python scripts/test_media_suite.py                      # quotes only
    python scripts/test_media_suite.py --pay --only speech  # cheapest real test
    python scripts/test_media_suite.py --pay --post         # full suite
"""

import argparse
import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from main import build_signer  # noqa: E402
from trappist_auto_bot.config import Config  # noqa: E402
from trappist_auto_bot.image.generator import TrappistImageGenerator  # noqa: E402
from trappist_auto_bot.media import TrappistMediaGenerator, build_media_prompts  # noqa: E402
from trappist_auto_bot.media.suite import DEFAULT_ARTICLE, LABELS, STEPS, SuiteArticle, run_media_suite  # noqa: E402
from trappist_auto_bot.telegram.poster import NoOpPoster, TelegramPoster  # noqa: E402
from trappist_auto_bot.x402.signer import MockSigner  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--title", default=DEFAULT_ARTICLE.title)
    parser.add_argument("--summary", default=DEFAULT_ARTICLE.summary)
    parser.add_argument("--hashtags", default=DEFAULT_ARTICLE.hashtags)
    parser.add_argument("--only", nargs="+", choices=STEPS, default=STEPS)
    parser.add_argument("--pay", action="store_true", help="Really pay in CSPR (otherwise quotes only)")
    parser.add_argument("--post", action="store_true", help="Publish each asset on Telegram")
    parser.add_argument("--voice", default="en-male", help="fr-female, fr-male, en-female, en-male, auto")
    parser.add_argument(
        "--max-cspr", type=float, default=None,
        help="Refuse any single payment above this (default: MAX_PAYMENT_MOTES)",
    )
    parser.add_argument("--out", default=str(_PROJECT_ROOT / "data" / "media_test"))
    return parser.parse_args()


def print_quotes(media: TrappistMediaGenerator, prompts: dict, steps: list[str], voice: str) -> None:
    bodies = {
        "image": {"prompt": prompts["image"]},
        "speech": {"text": prompts["speech"], "voice": voice},
        "music": prompts["music"],
        "video": {"prompt": prompts["video"], "duration": 5, "aspectRatio": "16:9", "audio": True},
        "3d": {"imageUrl": "https://example.com/placeholder.png", "withTexture": True},
    }
    total = 0.0
    print("💰 Current x402 prices (no payment made):")
    for step in steps:
        details = media.quote(step, bodies[step])
        total += float(details.cost_cspr or 0)
        print(f"  {LABELS[step]:<24} {details.cost_cspr:>14} CSPR  (${details.cost_usd})")
    if "3d" in steps:
        details = media.quote("image", {"prompt": prompts["3d_image"]})
        total += float(details.cost_cspr or 0)
        print(f"  {'  + black-bg image for 3D':<24} {details.cost_cspr:>14} CSPR  (${details.cost_usd})")
    print(f"  {'TOTAL':<24} {total:>14.6f} CSPR")
    print("Re-run with --pay to generate (and --post to publish on Telegram).")


def main() -> int:
    args = parse_args()
    config = Config.from_env()
    signer = build_signer(config)
    if args.pay and isinstance(signer, MockSigner):
        print("❌ No real Casper signer configured (CASPER_PRIVATE_KEY_*), cannot pay.")
        return 1

    paid = TrappistImageGenerator(config.trappist_api_url, config.wallet_public_key, signer)
    max_motes = config.max_payment_motes if args.max_cspr is None else int(args.max_cspr * 1_000_000_000)
    media = TrappistMediaGenerator(paid, max_payment_motes=max_motes)

    if not args.pay:
        print_quotes(media, build_media_prompts(args.title, args.summary), args.only, args.voice)
        return 0

    poster = (
        TelegramPoster(config.telegram_bot_token, config.telegram_chat_id, config.telegram_chat_id_fr)
        if args.post
        else NoOpPoster()
    )
    article = SuiteArticle(args.title, args.summary, args.hashtags, DEFAULT_ARTICLE.source)
    results = asyncio.run(
        run_media_suite(media, poster, article, steps=args.only, voice=args.voice, out_dir=Path(args.out))
    )
    for step, outcome in results.items():
        print(f"  {LABELS[step]:<24} {outcome}")
    print(f"Files saved in {args.out}")
    return 1 if any(o.startswith("failed:") for o in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
