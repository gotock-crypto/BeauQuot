# BeauQuot

Telegram-бот для публикации качественных вдохновляющих цитат с кинематографичными изображениями без текста.

## Текущая production-версия

**Visual Engine 3.1.6**.

Production 3.1.6 использует **AI Horde + Flux.1-Schnell fp8 (Compact)** для бесплатной генерации изображений. В anonymous/free режиме изображение запрашивается в **1024×1024**, затем локально нормализуется до квадрата перед OCR/semantic validation и публикацией.

### Pipeline

```text
quote
→ topic / mood
→ semantic art direction
→ AI Horde / Flux Schnell 1024×1024
→ local square normalization
→ OCR / semantic validation
→ Telegram publication
```

## Возможности

- отбор цитат с оценкой качества и защитой от дублей;
- анализ темы и настроения;
- semantic art direction;
- temporal semantic composition;
- разнообразные визуальные архетипы;
- кинематографичные промпты с запретом текста;
- несколько попыток генерации изображения;
- OCR-проверка при наличии Tesseract;
- бесплатная генерация через volunteer-сеть AI Horde;
- локальная нормализация изображения 1024×1024;
- SQLite-история публикаций и визуального разнообразия;
- Telegram-управление и автопостинг.

## Hugging Face

**Hugging Face не используется как image provider.**

В production 3.1.6 Hugging Face всё ещё может использоваться отдельными компонентами semantic analysis / visual judging. Это не относится к генерации изображений.

## Настройка

```env
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

TEMPORAL_COMPOSITION_ENABLED=1
TEMPORAL_COMPOSITION_MIN_CLAUSES=2
```

`AIHORDE_API_KEY=0000000000` — anonymous/free режим с низшим приоритетом очереди. Личный AI Horde key не обязателен.

Не коммитьте `.env`, Telegram-токены, API-ключи, SQLite и логи.

## Требования

- Python 3.10+;
- зависимости из `requirements.txt`;
- Tesseract OCR — необязательно, если нужна OCR-проверка.

## Production snapshot

Точный архив, использованный для production 3.1.6:

`quote-bot-v3.1.6-free-image-square.tar.gz`

SHA-256:

`df1f493cbf8c37825d2bc18eb58036a3e0280b266dfeffb8c93a51a466f17d2d`

Подробности: `PRODUCTION_3_1_6.md`.

## Обновление production

```bash
systemctl stop quote-bot.service
cd /opt/quote-bot
tar -czf /root/quote-bot-backup-$(date +%Y%m%d-%H%M%S).tar.gz --exclude='venv' .
tar -xzf /root/quote-bot-v3.1.6-free-image-square.tar.gz -C /
/opt/quote-bot/venv/bin/python3 -m py_compile /opt/quote-bot/main.py
systemctl start quote-bot.service
systemctl status quote-bot.service --no-pager -l
```

Логи:

```bash
journalctl -u quote-bot.service -f
```

## Безопасность

Секреты считываются только из environment. Если токен или API-ключ был раскрыт, его необходимо отозвать и перевыпустить.

## Лицензия

В репозитории пока не задана отдельная лицензия.
