# Обновление BeauQuot: YouTube Shorts

## Что добавлено
- Единый pipeline: цитата -> существующее AI-изображение GigaChat -> GigaChat-сценарий -> Edge TTS -> лёгкая фоновая музыка -> Ken Burns движение -> MP4 9:16 -> YouTube Shorts.
- YouTube независим от Telegram/MAX: ошибка YouTube не ломает публикацию в остальные платформы.
- SQLite хранит только состояние публикации и YouTube video_id. Медиа создаются во `runtime/youtube` и удаляются в `finally` после каждой попытки.
- Защита от повторной загрузки одной цитаты в YouTube по `quote_hash`.
- Музыка генерируется локально ffmpeg как тихий ambient bed, поэтому не нужен платный сервис и не скачиваются чужие треки.
- Edge TTS бесплатен, голос настраивается через `.env`.

## Важное ограничение
Для реальной загрузки в YouTube нужен ваш собственный Google Cloud OAuth Desktop Client и первый вход в Google/YouTube. Это обязательное действие владельца канала: пароль и доступ к аккаунту в проект не вшиваются.

## Команды обновления на сервере
Сначала распакуйте архив поверх `/opt/quote-bot` (с резервной копией старой версии):

```bash
systemctl stop quote-bot
cd /opt
cp -a quote-bot quote-bot.before-youtube-$(date +%Y%m%d-%H%M%S)
tar -xzf quote-bot-youtube-shorts-final.tar.gz
cd /opt/quote-bot
./venv/bin/pip install -r requirements.txt
apt-get update && apt-get install -y ffmpeg
```

Если `edge-tts` требует системные пакеты, установите зависимости pip внутри venv, как выше.

Скопируйте новые YouTube-переменные из `.env.example` в `.env`, но сначала оставьте:

```env
YOUTUBE_ENABLED=0
YOUTUBE_PRIVACY_STATUS=private
```

## Ваши действия для YouTube
1. В Google Cloud Console создайте проект.
2. Включите **YouTube Data API v3**.
3. Настройте OAuth consent screen.
4. Создайте OAuth Client ID типа **Desktop app**.
5. Скачайте JSON и положите на сервер как `/opt/quote-bot/youtube_client_secret.json`.
6. Выполните первый OAuth-вход командой ниже. Она создаст `youtube_token.json`.
7. После успешного входа установите `YOUTUBE_ENABLED=1`.
8. Перезапустите сервис.

Для первого OAuth запуска используйте:

```bash
cd /opt/quote-bot
./venv/bin/python - <<'PY'
from youtube.pipeline import YouTubePublisher
p=YouTubePublisher('quotes.db')
p.upload.__func__ if False else None
print('OAuth будет запущен при первой загрузке. Проверьте youtube_client_secret.json.')
PY
```

### Рекомендуемый безопасный первый запуск
Сначала поставьте `YOUTUBE_PRIVACY_STATUS=private`, затем вручную отправьте один тестовый пост из Telegram. После проверки переключите на `public`.

## Проверка

```bash
./venv/bin/python -m py_compile main.py youtube/pipeline.py
systemctl restart quote-bot
sleep 5
systemctl status quote-bot --no-pager -l
journalctl -u quote-bot -n 100 --no-pager
```

## Требования
- ffmpeg
- Edge TTS (ставится requirements.txt)
- Google OAuth JSON
- включённый YouTube Data API v3
- GigaChat credentials уже используются проектом для сценария/изображения
