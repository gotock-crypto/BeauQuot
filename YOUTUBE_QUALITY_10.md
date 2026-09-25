# YouTube Shorts Quality Upgrade

This version upgrades the Shorts pipeline with a quality-first profile:

- Natural voice pacing: slower speech, subtle pitch adjustment and sentence segmentation.
- Voice-first script: 45-70 spoken words, quote first, then one human interpretation.
- Audible ambient music: layered warm tones and soft texture instead of near-silent sine waves.
- Clean audio mix: voice normalized for intelligibility; music kept clearly audible but below speech.
- Better image presentation: 1080x1920 render, CRF 19, medium preset, mild contrast/saturation correction.
- Optional ultra-subtle cinematic push on the same image. Disable with `YOUTUBE_KEN_BURNS=0`.
- Production validation of the final MP4.

Recommended production settings are documented in `.env.example`.
