"""Shared visual theme for all Piranewz generated images."""

from typing import Any

from PIL import Image, ImageDraw

# Piranewz dark piranha palette.
INK_BLACK = (8, 8, 12)
DEEP_CHARCOAL = (18, 18, 26)
PALE_GRAY = (210, 210, 220)
MUTED_GRAY = (130, 130, 145)
BLOOD_RED = (200, 40, 60)
ROSE_TINT = (235, 80, 100)
AQUA_TEAL = (0, 180, 170)


def _interpolate(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def draw_dark_gradient(draw: ImageDraw.Draw, size: tuple[int, int]) -> None:
    """Draw a subtle dark vertical gradient background."""
    width, height = size
    for y in range(height):
        t = y / height
        color = _interpolate(INK_BLACK, DEEP_CHARCOAL, t)
        draw.line([(0, y), (width, y)], fill=color)


def draw_subtle_noise(draw: ImageDraw.Draw, size: tuple[int, int], density: int = 60) -> None:
    """Draw sparse tiny specks for texture (like deep water dust)."""
    import random

    width, height = size
    random.seed(7)
    for _ in range(density):
        x = random.randint(0, width)
        y = random.randint(0, height)
        r = random.randint(1, 2)
        alpha = random.randint(40, 90)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(*PALE_GRAY, alpha))


def create_theme_background(size: tuple[int, int]) -> Image.Image:
    """Create the standard Piranewz dark background for generated cards."""
    img = Image.new("RGBA", size, INK_BLACK)
    draw = ImageDraw.Draw(img)
    draw_dark_gradient(draw, size)
    draw_subtle_noise(draw, size)
    return img
