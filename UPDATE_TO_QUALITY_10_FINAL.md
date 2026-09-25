# BeauQuot — Final Quality Update

## Что изменено
- Строгий финальный OCR gate: текст на изображении блокирует публикацию.
- OCR работает fail-closed: при проблеме с OCR непроверенное изображение не публикуется.
- Многошаговая проверка OCR и до 5 попыток генерации.
- Семантическая проверка изображения и защита от визуальных повторов.
- Литературный перевод через GigaChat с дополнительным quality gate.
- Очистка LLM-меток и защита от публикации явно плохого перевода.
- Ровно 3 простых хештега.
- Более чистое премиальное оформление поста.
- Скрытая zero-width ссылка на канал сохранена.

## Обновление на сервере
Ниже предполагается, что текущий проект находится в `/opt/quote-bot`. При другом пути замените его во всех командах.

### 1. Backup
```bash
cd /opt
sudo tar -czf quote-bot-backup-$(date +%F-%H%M).tar.gz quote-bot
```

### 2. Загрузите архив
Загрузите `quote-bot-quality-10-final.tar.gz` на сервер, например в `/tmp`.

### 3. Распакуйте во временную папку
```bash
rm -rf /tmp/quote-bot-update
mkdir -p /tmp/quote-bot-update
tar -xzf /tmp/quote-bot-quality-10-final.tar.gz -C /tmp/quote-bot-update
```

### 4. Остановите сервис
Сначала узнайте точное имя сервиса, если оно неизвестно:
```bash
systemctl list-units --type=service | grep -i quote
```
Затем остановите его, например:
```bash
sudo systemctl stop quote-bot
```

### 5. Обновите код БЕЗ перезаписи .env и базы
```bash
sudo rsync -av --delete \
  --exclude '.env' \
  --exclude 'quotes.db' \
  --exclude 'admin_id.txt' \
  --exclude 'venv' \
  /tmp/quote-bot-update/quote-bot-quality-10-final/ /opt/quote-bot/
```

### 6. Установите системный OCR
```bash
sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng
```

### 7. Обновите Python-зависимости
```bash
cd /opt/quote-bot
source venv/bin/activate
pip install -r requirements.txt
python -m py_compile main.py
python - <<'PY'
import pytesseract
print('Tesseract:', pytesseract.get_tesseract_version())
PY
```

### 8. Перезапустите
```bash
sudo systemctl start quote-bot
sudo systemctl status quote-bot --no-pager
journalctl -u quote-bot -n 80 --no-pager
```

## Что проверить после обновления
1. Нет traceback после старта.
2. Tesseract доступен и имеет `rus` и `eng`.
3. Сделайте один тестовый пост.
4. Убедитесь: изображение без текста, смысл соответствует цитате, перевод естественный, ровно 3 хештега, ссылка скрыта.

## Rollback
```bash
sudo systemctl stop quote-bot
sudo rm -rf /opt/quote-bot
sudo tar -xzf /opt/quote-bot-backup-YYYY-MM-DD-HHMM.tar.gz -C /opt
sudo systemctl start quote-bot
```
