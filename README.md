# BeauQuot

Telegram quote bot focused on high-quality inspirational posts and cinematic, text-free image generation.

## Features

- Curated quote selection with quality scoring and duplicate protection.
- Topic and mood analysis to route quotes into different visual concepts.
- Diverse visual archetypes to avoid repetitive `woman + flowers + golden light` imagery.
- Cinematic editorial image prompts with an explicit text ban.
- Multiple image-generation attempts with optional OCR rejection of obvious text artifacts.
- Free-first Pollinations image generation; an API key can be supplied through the environment when available.
- Russian translation fallback via Google Translate web endpoint and MyMemory.
- SQLite publication history and visual diversity history.
- Telegram admin controls and configurable auto-posting interval.

## Requirements

Python 3.10+ is recommended.

Install dependencies:

```bash
pip install -r requirements.txt
```

`pytesseract` additionally needs the Tesseract OCR executable installed on the host if you want the optional OCR quality gate to run. If Tesseract is unavailable, the bot continues without OCR rejection.

## Configuration

Create a `.env` file locally or provide environment variables through your deployment platform:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHANNEL_ID=@BeauQuot
ADMIN_CHAT_ID=0
POLLINATIONS_API_KEY=
```

Do **not** commit `.env`, tokens, API keys, databases, generated configuration, or admin ID files.

Optional variables include:

- `DB_FILE`
- `CONFIG_FILE`
- `ADMIN_ID_FILE`
- `QUOTE_CORPUS_FILE`
- `QUOTE_CORPUS_URL`
- `IMAGE_TIMEOUT`
- `LEXICAL_DUP_THRESHOLD`
- `SEMANTIC_DUP_THRESHOLD`
- `RECENT_DIVERSITY_WINDOW`
- `EMBEDDING_MODEL`

## Run

```bash
python main.py
```

The first `/start` initializes the first Telegram admin when no admin ID has been configured yet.

## Repair an already published quote

```bash
python main.py repair-published "QUOTE TEXT" "AUTHOR"
```

## Image pipeline

The image prompt deliberately does not include the quote itself. The generator is instructed to communicate the emotional thesis visually and to avoid text-bearing objects, typography, logos, signs, screens, posters, and other common sources of unwanted text. The pipeline then validates the returned image and, when OCR is available, rejects obvious text artifacts and retries.

## Security

Secrets are read from environment variables only. Keep production credentials in the deployment platform's secret manager rather than in Git.
