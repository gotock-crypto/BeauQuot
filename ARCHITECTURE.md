# BeauQuot 4.0 — production architecture
Pipeline: fetch → validate → translate → semantic concept → image generation → OCR/semantic gates → non-destructive social preparation → platform formatting → independent Telegram/MAX publishing → SQLite state/history.

## Publication standard
- Telegram: HTML formatting, quote hierarchy, italic author, exactly 3 hashtags, hidden channel anchor.
- MAX: clean platform-safe text, exactly 3 hashtags, independent delivery/retry.
- Image: validated original is never destructively cropped; publication uses a 1080×1350 soft-edge canvas with the original composition preserved.

## Reliability
Each platform is independent. Partial success is persisted. Retries never erase prior success. Generated content is consumed only after at least one platform succeeds.
