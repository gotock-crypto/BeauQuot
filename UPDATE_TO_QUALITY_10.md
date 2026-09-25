# Обновление BeauQuot — Quality 10 (итерация 2)

## Что усилено

1. **OCR-фильтр стал строже**: проверяются несколько вариантов изображения и несколько OCR-режимов. Случайный текст, буквы и короткие фрагменты ловятся лучше.
2. **Fail-closed для OCR**: если `pytesseract` или движок Tesseract не работает, изображение не публикуется.
3. **Fail-closed для семантики**: если включён quality-first режим и визуальная проверка недоступна, пост не выходит с непроверенным изображением.
4. **До 5 разных визуальных попыток** для одной цитаты.
5. **Перевод усилен**: GigaChat получает роль литературного переводчика; удаляются типичные служебные префиксы и лишние кавычки.
6. **Пост**: цитата, автор, ровно 3 коротких хештега и скрытая ссылка на канал сохранены.
7. Архив не содержит `.env`, БД и `venv`: секреты и история публикаций не затираются.

## 1. Загрузить архив

С локального компьютера:

```bash
scp quote-bot-quality-10-iteration2.tar.gz root@YOUR_SERVER:/root/
```

## 2. Сделать backup на сервере

Подключитесь:

```bash
ssh root@YOUR_SERVER
```

Найдите текущую папку проекта и создайте backup:

```bash
cd /path/to/quote-bot
cp main.py main.py.before-quality10-iteration2
cp requirements.txt requirements.txt.before-quality10-iteration2
cp .env .env.before-quality10-iteration2
```

**Не копируйте поверх проекта БД `quotes.db`, `.env` и `venv`.**

## 3. Распаковать обновление во временную папку

```bash
mkdir -p /tmp/quote-quality10
rm -rf /tmp/quote-quality10/*
tar -xzf /root/quote-bot-quality-10-iteration2.tar.gz -C /tmp/quote-quality10
```

## 4. Скопировать код

```bash
cd /path/to/quote-bot
cp /tmp/quote-quality10/quote-bot-quality-10-update/main.py ./main.py
cp /tmp/quote-quality10/quote-bot-quality-10-update/requirements.txt ./requirements.txt
```

Если хотите использовать новые значения по умолчанию, **вручную** добавьте в существующий `.env`:

```env
OCR_REQUIRED=1
OCR_MIN_CONFIDENCE=35
OCR_MIN_TOKEN_LENGTH=3
OCR_MAX_ATTEMPTS=5
VISUAL_GENERATION_ATTEMPTS=5
VISUAL_SEMANTIC_GATE=1
VISUAL_SEMANTIC_FAIL_CLOSED=1
```

## 5. Установить Python-зависимости

Активируйте существующее виртуальное окружение:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

## 6. Обязательно установить системный OCR-движок

На Ubuntu/Debian:

```bash
apt update
apt install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus
```

Проверка:

```bash
tesseract --version
```

## 7. Техническая проверка до restart

```bash
python -m py_compile main.py
python -c "import main; print('IMPORT OK')"
```

Если вторая команда показывает `IMPORT OK`, импорт прошёл успешно.

## 8. Restart

Если используется systemd:

```bash
systemctl restart quote-bot
systemctl status quote-bot --no-pager -n 30
journalctl -u quote-bot -n 80 --no-pager
```

Если имя сервиса другое, используйте своё имя.

## 9. Обязательный тест качества

Сделайте один тестовый пост через существующую команду бота. Проверьте:

- на изображении нет букв, цифр и водяных знаков;
- изображение передаёт **смысл**, а не просто настроение цитаты;
- перевод звучит естественно по-русски;
- автор указан корректно;
- есть ровно 3 простых хештега;
- ссылка на канал остаётся скрытой;
- в логах нет traceback после нового изменения.

## Rollback

Если результат хуже:

```bash
cd /path/to/quote-bot
cp main.py.before-quality10-iteration2 main.py
cp requirements.txt.before-quality10-iteration2 requirements.txt
systemctl restart quote-bot
```

Для `.env`:

```bash
cp .env.before-quality10-iteration2 .env
```

## Важное замечание

Это quality-first конфигурация: лучше пропустить один пост, чем опубликовать изображение с текстом или семантически неподходящую картинку. После нескольких реальных генераций стоит провести следующую итерацию по конкретным примерам: перевод → промпт → изображение → OCR → публикация.
