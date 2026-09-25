# BeauQuot 4.1 — separate publication streams

## New admin controls
- 🚀 Опубликовать MAX + TG — only Telegram and MAX.
- 📺 Создать YouTube Shorts — only YouTube.
- ⚙️ Автопостинг MAX + TG — independent toggle.
- ⚙️ Автопостинг YouTube — independent toggle.
- ⏰ Интервал MAX + TG — independent interval.
- ⏰ Интервал YouTube — independent interval.

## Important
The old combined pipeline no longer uploads to YouTube. Telegram/MAX and YouTube have separate locks, schedules and last-publication timestamps.

YouTube has its own quote history based on `youtube_publications`, so repeated manual or automatic Shorts creation does not simply return the previous video as a successful new publication.
