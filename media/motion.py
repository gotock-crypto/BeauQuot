"""Legacy compatibility module. Motion generation is intentionally disabled.

The publication pipeline now uses the validated static image directly.
"""

def create_framed_image(image_bytes: bytes, width: int = 540, height: int = 676) -> str:
    raise RuntimeError("Animated/framed media is disabled; use the validated static image directly")