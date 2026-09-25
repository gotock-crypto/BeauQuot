# BeauQuot

**AI Content Automation Platform**

BeauQuot — практический AI-pipeline для автоматизированного создания и публикации визуального контента из корпуса цитат.

Проект объединяет отбор контента, смысловой анализ, визуальную режиссуру, генерацию изображений, OCR/semantic validation, контроль повторов и автоматическую публикацию.

---

## Pipeline

```text
Quote corpus
    ↓
Quality scoring
    ↓
Duplicate / publication history checks
    ↓
Topic + mood analysis
    ↓
Semantic art direction
    ↓
AI image generation
    ↓
Local image normalization
    ↓
OCR validation
    ↓
Semantic validation
    ↓
Visual history / deduplication
    ↓
Text generation + hashtags
    ↓
Telegram / MAX / YouTube
```

Каждый этап работает как часть общего stateful workflow: состояние, история публикаций и визуальная память сохраняются в SQLite.

---

## Что делает система

### 1. Отбор цитат

- корпус из **1655 цитат**;
- quality scoring;
- тематическая классификация;
- защита от повторного использования;
- учёт истории публикаций;
- контроль тематического разнообразия.

### 2. Semantic analysis

Перед генерацией изображения система анализирует содержание цитаты и формирует визуальное направление:

- смысл;
- тема;
- настроение;
- визуальный archetype;
- motif;
- visual profile;
- image caption.

Это позволяет отделить **смысл цитаты** от непосредственного запроса к image generator.

### 3. AI image generation

Production image pipeline использует:

- **AI Horde**;
- **Flux.1-Schnell fp8 (Compact)**;
- anonymous/free generation;
- исходный размер **1024×1024**;
- локальную нормализацию изображения перед дальнейшими проверками.

Production-версия visual engine: **3.1.6**.

> Hugging Face не является image provider проекта. Он может использоваться отдельными компонентами semantic analysis / visual judging.

### 4. Image quality gates

Сгенерированное изображение не публикуется автоматически без проверок.

Pipeline включает:

- MIME validation;
- Pillow validation;
- OCR;
- semantic validation;
- visual duplicate detection;
- perceptual hash;
- контроль visual history;
- контроль visual diversity.

Если результат не проходит проверку, pipeline может перейти к следующей попытке генерации.

### 5. Контроль визуального разнообразия

Система хранит визуальную историю и учитывает:

- archetype;
- motif;
- visual profile;
- image caption;
- perceptual hash.

Цель — не только избегать технических дублей, но и снижать повторяемость визуального паттерна между публикациями.

---

## Automated publishing

### Telegram

Telegram используется как один из основных каналов публикации.

Pipeline поддерживает:

- автоматический scheduler;
- подготовку изображения;
- форматирование текста;
- hashtags;
- retry;
- сохранение состояния;
- обработку ошибок.

### MAX

Для MAX используется отдельный publisher.

Публикация выполняется независимо от Telegram, поэтому ошибка одной платформы не должна автоматически ломать весь pipeline.

### YouTube Shorts

Отдельный contour формирует вертикальные Shorts:

```text
AI script
    ↓
Edge TTS
    ↓
Audio processing
    ↓
FFmpeg
    ↓
1080×1920 video
    ↓
H.264 / AAC
    ↓
YouTube API / OAuth
```

В pipeline предусмотрены аудиомикс, background music, loudness processing и проверка итогового MP4.

---

## Stateful architecture

SQLite используется как persistent state layer.

Система хранит:

- историю цитат;
- историю публикаций;
- состояние pipeline;
- visual history;
- данные, необходимые для контроля повторов.

Основной принцип — pipeline не должен зависеть только от текущего процесса. Состояние сохраняется и может использоваться после перезапуска.

---

## Reliability

В проекте используются:

- retry;
- timeout handling;
- fallback logic;
- state management;
- runtime diagnostics;
- logging;
- независимая публикация по платформам;
- cleanup временных media-файлов.

Pipeline рассчитан на длительную автоматическую работу под Linux/systemd.

---

## Repository structure

```text
BeauQuot/
├── main.py
├── core/
│   └── pipeline_contract.py
├── media/
│   ├── motion.py
│   └── prepare.py
├── publishers/
│   └── formatters.py
├── validators/
│   └── platform.py
├── max/
│   └── publisher.py
├── youtube/
│   └── pipeline.py
├── quotes_corpus.json
├── requirements.txt
└── documentation / update notes
```

### Key modules

- `main.py` — orchestration, scheduling and Telegram/admin flow;
- `core/` — pipeline contracts and stage definitions;
- `media/` — image preparation;
- `validators/` — publication validation;
- `publishers/` — platform-specific formatting;
- `max/` — MAX publishing adapter;
- `youtube/` — YouTube Shorts pipeline;
- `quotes_corpus.json` — source quote corpus.

---

## Tech stack

**Core**

- Python
- asyncio
- SQLite
- REST API
- logging
- systemd
- Linux / VPS

**AI**

- GigaChat
- AI Horde
- Flux.1-Schnell
- Hugging Face components

**Media**

- Pillow
- pytesseract / Tesseract OCR
- FFmpeg
- Edge TTS

**Platforms**

- Telegram Bot API
- MAX API
- YouTube API
- OAuth

---

## Configuration

Secrets are supplied through environment variables.

Example:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHANNEL_ID=@BeauQuot
ADMIN_CHAT_ID=...

AIHORDE_API_KEY=...
AIHORDE_IMAGE_MODEL=Flux.1-Schnell fp8 (Compact)
```

**Do not commit:**

- `.env`;
- API keys;
- bot tokens;
- OAuth credentials;
- YouTube tokens;
- SQLite runtime databases;
- runtime state;
- local virtual environments;
- backups.

The repository contains a `.gitignore` for these categories.

---

## Deployment

Project is designed as a long-running Linux/systemd service.

Typical operational flow:

```bash
systemctl stop quote-bot.service
# update source
# validate configuration
# run syntax / smoke checks
systemctl start quote-bot.service
systemctl status quote-bot.service --no-pager -l
```

Runtime logs can be inspected with:

```bash
journalctl -u quote-bot.service -f
```

---

## Production snapshot

Visual Engine production version:

**3.1.6**

Production snapshot:

```text
quote-bot-v3.1.6-free-image-square.tar.gz
```

SHA-256:

```text
df1f493cbf8c37825d2bc18eb58036a3e0280b266dfeffb8c93a51a466f17d2d
```

---

## Project status

BeauQuot is a practical AI-assisted automation project combining:

- LLM-based semantic processing;
- AI image generation;
- automated quality gates;
- visual deduplication;
- persistent state;
- multi-platform publishing;
- scheduled execution;
- production-oriented retry and recovery logic.

The repository intentionally contains source code and documentation, while credentials, runtime state, local environments and backups are excluded.

## License

The repository currently does not declare a separate project license.
