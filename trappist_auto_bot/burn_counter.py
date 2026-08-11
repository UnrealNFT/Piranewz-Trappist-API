"""Track TrappistAI image generations and celebrate CSPR burned."""

from typing import Any

from trappist_auto_bot.image.generator import TrappistImageGenerator
from trappist_auto_bot.storage.db import Database
from trappist_auto_bot.telegram.poster import TelegramPoster
from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)

# Casper transaction fees are burned. Each TrappistAI generation triggers one
# deploy, costing approximately 0.1 CSPR in network fees.
CSPR_BURNED_PER_IMAGE = 0.1


class BurnCounter:
    """Count TrappistAI generations and post burn milestones."""

    def __init__(
        self,
        database: Database,
        poster: TelegramPoster,
        generator: TrappistImageGenerator | None = None,
        milestone_interval: int = 10,
        logo_path: str = "",
    ) -> None:
        self.db = database
        self.poster = poster
        self.generator = generator
        self.milestone_interval = max(1, milestone_interval)
        self.logo_path = logo_path

    def record_generation(self) -> tuple[int, float]:
        """Increment the burn counter and return the new totals."""
        images = self.db.increment_burn_counter()
        burned = round(images * CSPR_BURNED_PER_IMAGE, 1)
        logger.info("Burn counter updated: %s images, %s CSPR burned", images, burned)
        return images, burned

    def get_stats(self) -> tuple[int, float]:
        """Return current counter values without incrementing."""
        images = self.db.get_burn_counter()
        burned = round(images * CSPR_BURNED_PER_IMAGE, 1)
        return images, burned

    def build_prompt(self, images: int, burned: float) -> str:
        """Create a pro Piranewz burn-milestone prompt for TrappistAI."""
        return (
            "Square album cover artwork for Piranewz, a dark cyberpunk crypto "
            "news brand. A giant metallic Casper $CSPR coin in the center, "
            "engulfed in realistic red, orange and blue flames, burning "
            "deflationary money. Bold text logo at the top reading "
            f"'C coin burn', subtitle 'Casper deflationary', big centered "
            f"numbers '{int(burned)} $CSPR burned', below that '{images} images generated' "
            "and 'powered by trappist.land'. Piranewz piranha mascot silhouette "
            "in the corner, neon glow, cinematic lighting, ultra detailed, 8k, "
            "square format"
        )

    def build_caption(self, images: int, burned: float) -> tuple[str, str]:
        """Return clear English and French captions for a burn milestone post."""
        emoji = "🔥"
        caption_en = (
            f"{emoji} **Piranewz Burn Milestone**\n\n"
            f"**{images}** images generated so far\n"
            f"**{burned} $CSPR** burned in total\n\n"
            f"How it works: every time Piranewz creates an image on "
            f"[trappist.land](https://trappist.land), the Casper network "
            f"charges a ~0.1 $CSPR transaction fee — and Casper burns *all* "
            f"its fees. So every 10 images = 1 $CSPR removed from circulation "
            f"forever.\n\n"
            f"Piranewz is feeding the fire. 🔱"
        )
        caption_fr = (
            f"{emoji} **Jalon Burn Piranewz**\n\n"
            f"**{images}** images générées jusqu'à présent\n"
            f"**{burned} $CSPR** brûlés au total\n\n"
            f"Comment ça marche : chaque fois que Piranewz crée une image sur "
            f"[trappist.land](https://trappist.land), le réseau Casper "
            f"prélève environ 0.1 $CSPR de frais de transaction — et Casper "
            f"brûle *tous* ses frais. Donc toutes les 10 images = 1 $CSPR "
            f"retiré de la circulation pour toujours.\n\n"
            f"Piranewz alimente le feu. 🔱"
        )
        tags = "#Casper #CSPR #Burn #Deflationary #Crypto #Piranewz #TrappistAI #Blockchain"
        return f"{caption_en}\n\n{tags}", f"{caption_fr}\n\n{tags}"

    async def maybe_post_milestone(
        self,
        images: int,
        burned: float,
    ) -> dict[str, Any] | None:
        """Post a burn milestone when images hits the configured interval."""
        logger.info(
            "Checking burn milestone: images=%s, interval=%s, modulo=%s",
            images,
            self.milestone_interval,
            images % self.milestone_interval if images > 0 else "N/A",
        )
        if images <= 0 or images % self.milestone_interval != 0:
            logger.info("Burn milestone not at interval, skipping")
            return None

        return await self._post_burn_update(images, burned)

    async def post_burn_update(
        self,
        images: int,
        burned: float,
    ) -> dict[str, Any] | None:
        """Post a burn update immediately, regardless of milestone interval."""
        return await self._post_burn_update(images, burned)

    async def _post_burn_update(
        self,
        images: int,
        burned: float,
    ) -> dict[str, Any] | None:
        """Generate and post the burn update image + caption."""
        if self.generator is None:
            logger.warning("No TrappistAI generator configured; skipping burn update image")
            return None

        prompt = self.build_prompt(images, burned)
        logger.info("Generating burn update image with TrappistAI")
        try:
            generation_result = await self._generate_with_trappist(prompt)
            image_url = (
                generation_result.get("api_response", {}).get("imageUrl")
                or generation_result.get("api_response", {}).get("url", "")
            )
            logger.info("Burn update image URL: %s", image_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to generate burn update image: %s", exc)
            return None

        if not image_url:
            logger.warning("No image URL returned for burn update")
            return None

        caption_en, caption_fr = self.build_caption(images, burned)
        logger.info("Posting burn update to Telegram (logo=%s)", bool(self.logo_path))
        try:
            result = await self.poster.post_image(
                image_url=image_url,
                caption_en=caption_en,
                caption_fr=caption_fr,
                add_logo=bool(self.logo_path),
                logo_path=self.logo_path,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to post burn update: %s", exc)
            return None

        logger.info("Posted burn update: %s images, %s $CSPR burned", images, burned)
        return {
            "type": "burn_milestone",
            "images_generated": images,
            "cspr_burned": burned,
            **result,
        }

    async def _generate_with_trappist(self, prompt: str) -> dict[str, Any]:
        """Run the TrappistAI generator in the async executor."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.generator.generate, prompt)
