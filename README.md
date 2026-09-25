# BeauQuot

**AI Content Automation Platform** — автоматизированный pipeline для отбора, смыслового анализа, визуализации, валидации и публикации контента.

## Что делает проект

BeauQuot превращает исходную цитату в готовый визуальный контент и автоматически проходит production-процесс: от выбора и анализа цитаты до генерации изображения, quality checks и публикации.

Основной контур:

    quote
    → quality / duplicate checks
    → topic / mood analysis
    → semantic art direction
    → AI image generation
    → local normalization
    → OCR / semantic validation
    → visual history / deduplication
    → publication

## Основные возможности

- корпус цитат с quality scoring и защитой от повторного использования;
- тематический и эмоциональный анализ;
- semantic art direction перед генерацией изображения;
- temporal semantic composition;
- управление визуальными архетипами и разнообразием контента;
- генерация изображений через AI Horde / Flux.1-Schnell;
- несколько попыток генерации с обработкой ошибок;
- локальная нормализация изображений;
- OCR-проверка на наличие нежелательного текста;
- semantic validation визуального результата;
- SQLite для хранения состояния, истории публикаций и визуального разнообразия;
- Telegram-управление и автоматический scheduler;
- retry/fallback и runtime diagnostics.

## Production image pipeline

Текущая production-версия репозитория — **Visual Engine 3.1.6**.

Для генерации изображений используется **AI Horde + Flux.1-Schnell fp8 (Compact)**. В anonymous/free режиме изображение запрашивается в 1024×1024 и затем локально нормализуется перед последующими проверками и публикацией.

**Hugging Face не является image provider.** Он может использоваться отдельными компонентами semantic analysis / visual judging.

## Архитектура

Проект построен вокруг последовательного AI workflow с сохранением состояния:

- content selection;
- semantic analysis;
- visual concept generation;
- image generation;
- image validation;
- duplicate / diversity checks;
- publication.

SQLite используется как persistent state layer для истории контента, публикаций и визуальной памяти.

## Стек

- Python 3.10+
- SQLite
- AI Horde
- Flux.1-Schnell
- Hugging Face
- Telegram Bot API
- Pillow
- pytesseract / Tesseract OCR
- REST API
- systemd
- Linux / VPS
- environment-based configuration
- logging / runtime diagnostics

## Production

Production snapshot:

quote-bot-v3.1.6-free-image-square.tar.gz

SHA-256:

df1f493cbf8c37825d2bc18eb58036a3e0280b266dfeffb8c93a51a466f17d2d

## Configuration

Secrets and credentials are read from environment variables.

Example:

    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_CHANNEL_ID=@BeauQuot
    ADMIN_CHAT_ID=...

    AIHORDE_API_KEY=0000000000
    AIHORDE_IMAGE_MODEL=Flux.1-Schnell fp8 (Compact)
    AIHORDE_IMAGE_WIDTH=1024
    AIHORDE_IMAGE_HEIGHT=1024
    AIHORDE_IMAGE_STEPS=4
    AIHORDE_IMAGE_CFG=1
    AIHORDE_IMAGE_SAMPLER=k_euler
    AIHORDE_IMAGE_TIMEOUT=360
    AIHORDE_POLL_INTERVAL=5

Не коммитьте .env, токены, API-ключи, SQLite-файлы и runtime logs.

## Deployment

Проект рассчитан на работу как долгоживущий сервис под Linux/systemd.

Пример базового цикла обновления:

    systemctl stop quote-bot.service
    cd /opt/quote-bot
    tar -czf /root/quote-bot-backup-$(date +%Y%m%d-%H%M%S).tar.gz --exclude='venv' .
    /opt/quote-bot/venv/bin/python3 -m py_compile /opt/quote-bot/main.py
    systemctl start quote-bot.service
    systemctl status quote-bot.service --no-pager -l

Logs:

    journalctl -u quote-bot.service -f

## Repository hygiene

The repository excludes secrets, credentials, SQLite runtime state, local virtual environments, backups, logs and generated media. Use `.env.example` for configuration templates.

## Source layout

- `main.py` — orchestration and Telegram admin flow;
- `youtube/` — independent YouTube Shorts pipeline;
- `media/` — validated static-image preparation;
- `publishers/` — platform formatting;
- `max/` — MAX publishing adapter;
- `validators/` — publication quality gates;
- `core/` — pipeline contracts;
- `quotes_corpus.json` — source quote corpus.

## Project

BeauQuot is a practical example of an AI-assisted content automation system combining semantic processing, image generation, validation, persistent state and automated publishing.

## License

The repository currently does not declare a separate project license.
