"""Test every TrappistAI x402 media type on one article.

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

import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from main import build_signer  # noqa: E402
from trappist_auto_bot.config import Config  # noqa: E402
from trappist_auto_bot.image.generator import TrappistImageGenerator  # noqa: E402
from trappist_auto_bot.media import TrappistMediaGenerator, build_media_prompts  # noqa: E402
from trappist_auto_bot.telegram.poster import NoOpPoster, TelegramPoster  # noqa: E402
from trappist_auto_bot.x402.signer import MockSigner  # noqa: E402

DEFAULT_TITLE = "Mesh & Visa Unite: Spend Crypto Directly From Your Wallet"
DEFAULT_SUMMARY = (
    "Mesh partners with Visa to enable instant crypto and stablecoin spending directly "
    "from wallet apps, eliminating the need to sell or transfer funds first. The "
    "integration brings seamless payment capabilities to everyday users."
)
DEFAULT_HASHTAGS = "#MeshWallet #VisaCrypto #StablecoinPayments #CryptoSpending #WalletIntegration"
DEFAULT_SOURCE = (
    "[📰 The Block](https://www.theblock.co/news/business/"
    "2026-10-19-mesh-visa-partner-spend-crypto-stablecoins-421058)"
)
STEPS = ["image", "speech", "music", "video", "3d"]
LABELS = {
    "image": "🖼 Image FLUX Schnell",
    "speech": "🎙 Speech",
    "music": "🎵 Music",
    "video": "🎬 Video",
    "3d": "🧊 3D Tripo (texture)",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--title", default=DEFAULT_TITLE)
    parser.add_argument("--summary", default=DEFAULT_SUMMARY)
    parser.add_argument("--hashtags", default=DEFAULT_HASHTAGS)
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


def download(url: str) -> bytes:
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    return response.content


def build_poster(config: Config, enabled: bool):
    if enabled and config.telegram_bot_token and config.telegram_chat_id:
        return TelegramPoster(config.telegram_bot_token, config.telegram_chat_id, config.telegram_chat_id_fr)
    return NoOpPoster()


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
    prompts = build_media_prompts(args.title, args.summary)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    quote_bodies = {
        "image": {"prompt": prompts["image"]},
        "speech": {"text": prompts["speech"], "voice": args.voice},
        "music": prompts["music"],
        "video": {"prompt": prompts["video"], "duration": 5, "aspectRatio": "16:9", "audio": True},
        "3d": {"imageUrl": "https://example.com/placeholder.png", "withTexture": True},
    }

    if not args.pay:
        total = 0.0
        print("💰 Current x402 prices (no payment made):")
        for step in args.only:
            details = media.quote(step, quote_bodies[step])
            total += float(details.cost_cspr or 0)
            print(f"  {LABELS[step]:<24} {details.cost_cspr:>14} CSPR  (${details.cost_usd})")
        if "3d" in args.only:
            details = media.quote("image", {"prompt": prompts["3d_image"]})
            total += float(details.cost_cspr or 0)
            print(f"  {'  + black-bg image for 3D':<24} {details.cost_cspr:>14} CSPR  (${details.cost_usd})")
        print(f"  {'TOTAL':<24} {total:>14.6f} CSPR")
        print("Re-run with --pay to generate (and --post to publish on Telegram).")
        return 0

    caption_tail = f"{args.hashtags}\n\n{DEFAULT_SOURCE}"
    image_url = ""
    failures = []

    async def publish(kind: str, data: bytes, filename: str, step: str) -> None:
        caption = f"{LABELS[step]}\n\n**{args.title}**\n\n{caption_tail}"
        # Fresh Bot per asyncio.run: its HTTP client is bound to one event loop.
        poster = build_poster(config, True)
        if kind == "photo":
            await poster.post_image_bytes(data, caption_en=caption)
        else:
            await poster.post_media(kind, data, filename, caption_en=caption)

    for step in args.only:
        print(f"\n=== {LABELS[step]} ===")
        try:
            if step == "image":
                result = media.image(prompts["image"])
                image_url = result.url
                data, filename, kind = download(result.url), "article.png", "photo"
            elif step == "speech":
                result = media.speech(prompts["speech"], voice=args.voice)
                data, filename, kind = result.data, "article_speech.mp3", "audio"
            elif step == "music":
                result = media.music(prompts["music"]["lyrics"], prompts["music"]["tags"])
                data, filename, kind = download(result.url), "article_music.mp3", "audio"
            elif step == "video":
                # Animate the article image when we have one, else text-to-video.
                result = media.video(prompts["video"], image_url=image_url or None)
                data, filename, kind = download(result.url), "article_video.mp4", "video"
            else:
                black_bg = media.image(prompts["3d_image"])
                print(f"  black-bg image: {black_bg.url} ({black_bg.payment.cost_cspr} CSPR)")
                (out_dir / "article_3d_source.png").write_bytes(download(black_bg.url))
                result = media.model_3d(black_bg.url, with_texture=True)
                data, filename, kind = download(result.url), "article_model.glb", "document"

            (out_dir / filename).write_bytes(data)
            print(f"  ✅ {result.url or filename} | {result.payment.cost_cspr} CSPR | tx {result.transaction}")
            if args.post:
                asyncio.run(publish(kind, data, filename, step))
        except Exception as exc:  # noqa: BLE001
            failures.append(step)
            print(f"  ❌ {step} failed: {exc}")

    print(f"\nFiles saved in {out_dir}")
    if failures:
        print(f"Failed steps: {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
