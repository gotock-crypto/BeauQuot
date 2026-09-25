"""Prepare a clean static image for Telegram, MAX and other social feeds.

No text, branding, borders, overlays, animation frames or decorative cards are added.
"""
from io import BytesIO
from PIL import Image, ImageOps, ImageEnhance

TARGET = (1080, 1350)


def prepare_social_image(data, width=1080, height=1350, brand=None):
    """Return a polished, full-bleed static artwork without any added text."""
    src = ImageOps.exif_transpose(Image.open(BytesIO(data))).convert("RGB")
    image = ImageOps.fit(src, (width, height), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    image = ImageEnhance.Contrast(image).enhance(1.025)
    image = ImageEnhance.Color(image).enhance(1.035)
    image = ImageEnhance.Sharpness(image).enhance(1.06)
    out = BytesIO()
    image.save(out, "JPEG", quality=96, optimize=True, progressive=True, subsampling=0)
    return out.getvalue()


def create_emergency_image(*args, **kwargs):
    """Emergency text cards are forbidden; publication must retry image generation."""
    raise RuntimeError("Text-card fallback is disabled by static clean-image policy")
