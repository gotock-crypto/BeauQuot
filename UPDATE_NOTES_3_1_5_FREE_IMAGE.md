# Обновление BeauQuot 3.1.5 — бесплатная генерация изображений

В этой версии **Hugging Face полностью исключён из генерации изображений**.

Изображения генерируются через **AI Horde** — волонтёрскую распределённую сеть. Генерация бесплатна; по умолчанию используется анонимный ключ `0000000000`, поэтому `HF_TOKEN`, `HF_TOKEN_2`, `HF_TOKEN_3` больше не нужны именно для картинок. AI Horde подтверждает, что генерация бесплатна, а API поддерживает асинхронную постановку задания и получение результата.

Используемая модель по умолчанию:

`Flux.1-Schnell fp8 (Compact)`

Для Flux рекомендуются 4–8 шагов, `k_euler` и CFG 1; эти параметры соответствуют настройкам AI Horde.

## Что осталось от Hugging Face

HF **не удалён из проекта целиком**: он по-прежнему используется для semantic analyst и visual judge/captioning. Это отдельная задача и не относится к генерации изображений.

## Новые переменные `.env`

Можно вообще ничего не добавлять — работают значения по умолчанию:

```env
AIHORDE_API_KEY=0000000000
AIHORDE_IMAGE_MODEL=Flux.1-Schnell fp8 (Compact)
AIHORDE_IMAGE_WIDTH=1024
AIHORDE_IMAGE_HEIGHT=1280
AIHORDE_IMAGE_STEPS=4
AIHORDE_IMAGE_CFG=1
AIHORDE_IMAGE_SAMPLER=k_euler
AIHORDE_IMAGE_TIMEOUT=360
AIHORDE_POLL_INTERVAL=5
```

`AIHORDE_API_KEY=0000000000` — анонимный режим с низшим приоритетом очереди. Личный ключ AI Horde необязателен; его можно указать позже, если понадобится более высокий приоритет.

## Установка

```bash
systemctl stop quote-bot.service
cd /opt/quote-bot
BACKUP="/root/quote-bot-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
tar -czf "$BACKUP" --exclude='venv' .
tar -xzf /root/quote-bot-v3.1.5-free-image.tar.gz -C /
/opt/quote-bot/venv/bin/python3 -m py_compile /opt/quote-bot/main.py
systemctl start quote-bot.service
systemctl status quote-bot.service --no-pager -l
```

Проверка:

```bash
journalctl -u quote-bot.service -n 60 --no-pager | grep -Ei '3\.1\.5|AI Horde|Image provider|ERROR|WARNING'
```

Ожидается:

`Image provider: AI Horde free/anonymous; Hugging Face tokens are used only for semantic LLM/vision.`

и после запуска:

`BeauQuot 3.1.5 Visual Engine started — temporal semantic composition + free AI Horde image generation enabled`

## Важное ограничение

Анонимный AI Horde имеет самый низкий приоритет, поэтому картинка может генерироваться заметно дольше Hugging Face. Это цена за отсутствие платного аккаунта и постоянной ротации HF-токенов.

Откат выполняется обычным восстановлением backup. `.env` и SQLite в архив не входят.


### 3.1.6 patch: free-friendly square generation
- AI Horde image generation defaults to 1024x1024.
- Generated images are normalized locally to a centered 1024x1024 square before OCR/semantic validation/publication.
- Added Pillow dependency.
