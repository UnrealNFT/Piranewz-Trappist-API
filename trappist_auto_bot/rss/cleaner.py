"""Clean RSS content from parasitic HTML/images/links."""

import re
import html


def clean_content(text: str) -> str:
    """Clean RSS content: strip HTML, images, links, boilerplate, entities."""
    if not text:
        return ""

    # Remove images and links (including their anchor text).
    text = re.sub(r"<img[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<a[^>]*>.*?</a>", "", text, flags=re.IGNORECASE)

    # Strip remaining HTML tags.
    text = re.sub(r"<[^>]*>", "", text)

    # Remove direct image URLs.
    text = re.sub(
        r"https?://[^\s]*\.(jpg|jpeg|png|gif|webp|svg)[^\s]*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove image captions/boilerplate.
    text = re.sub(r"\[Image:.*?\]", "", text)
    text = re.sub(r"\(Image:.*?\)", "", text)
    text = re.sub(r"Image\s*:\s*[^\n]*", "", text, flags=re.IGNORECASE)

    # Remove "read more" / source trailers.
    text = re.sub(r"Read more.*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"Continue reading.*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"Source\s*:\s*.*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"Read full story.*", "", text, flags=re.IGNORECASE)

    # Remove syndication boilerplate.
    text = re.sub(r"The post .* appeared first on.*", "", text)
    text = re.sub(r"Originally appeared on.*", "", text)

    # Decode HTML entities and normalize whitespace.
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\n+", " ", text)

    text = text.replace("\r", "").replace("\t", " ")

    # Drop empty brackets left by removals.
    text = re.sub(r"\[\s*\]", "", text)
    text = re.sub(r"\(\s*\)", "", text)

    return text.strip()
