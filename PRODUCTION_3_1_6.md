# BeauQuot 3.1.6 — Production snapshot

Дата snapshot: 2026-08-27.

## Production

Production runs `/opt/quote-bot/main.py` from `quote-bot-v3.1.6-free-image-square.tar.gz`.

- Image generation: free AI Horde volunteer network.
- Default image request: 1024×1024.
- Local centered square normalization: 1024×1024 before OCR/semantic validation/publication.
- Pillow is required for local image normalization.
- HF is not used for image generation.
- The current 3.1.6 production code still contains Hugging Face integration for semantic analysis / visual judging; this is separate from image generation.
- Telegram publishing, SQLite history, uniqueness checks and scheduler remain unchanged from the production pipeline.

## Production archive

Exact production archive:

`quote-bot-v3.1.6-free-image-square.tar.gz`

SHA-256:

`df1f493cbf8c37825d2bc18eb58036a3e0280b266dfeffb8c93a51a466f17d2d`

## Environment

Image generation works without an HF image token. Existing semantic/vision HF settings may remain in `.env` until that part of the pipeline is intentionally migrated.

Do not commit `.env`, Telegram tokens, HF tokens, SQLite databases or logs.

## Validation

```bash
/opt/quote-bot/venv/bin/python3 -m py_compile /opt/quote-bot/main.py
systemctl status quote-bot.service --no-pager -l
journalctl -u quote-bot.service -n 100 --no-pager
```
