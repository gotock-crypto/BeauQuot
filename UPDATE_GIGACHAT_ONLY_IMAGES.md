# GigaChat-only image generation

- Removed operational use of AI Horde and emergency PIL quote-card fallback.
- Image generation is strictly GigaChat-only.
- OCR-invalid, empty, unavailable, or semantically rejected results are retried indefinitely.
- The pipeline does not publish a text card or substitute image when generation fails.
- A new visual concept is generated after semantic rejection to avoid repeating irrelevant compositions.
