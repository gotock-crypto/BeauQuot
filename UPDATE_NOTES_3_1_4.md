# Обновление BeauQuot 3.1.4

Архив распаковывается поверх `/opt/quote-bot`.

Заменяется `main.py` и добавляются документационные файлы. `.env`, SQLite-база и рабочее состояние не заменяются архивом.

## Обновление production

```bash
cd /opt/quote-bot
systemctl stop quote-bot.service

BACKUP="/root/quote-bot-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
tar -czf "$BACKUP" --exclude='venv' .

tar -xzf /root/quote-bot-v3.1.4.tar.gz -C /

/opt/quote-bot/venv/bin/python3 -m py_compile /opt/quote-bot/main.py
echo "compile=$?"

systemctl start quote-bot.service
systemctl status quote-bot.service --no-pager -l
```

## Проверка версии

```bash
journalctl -u quote-bot.service -n 30 --no-pager | grep -Ei '3\.1\.4|temporal semantic|Image provider|ERROR|WARNING'
```

Ожидается:

`BeauQuot 3.1.4 Visual Engine started — temporal semantic composition enabled`

## Тест

В Telegram нажать `🧪 Тест картинки`.

Для 3.1.4 лучше использовать цитату с явной временной или многочастной логикой. В логах должны появиться semantic/concept данные, а изображение должно оставаться одной непрерывной сценой, а не коллажем.

## Откат

```bash
systemctl stop quote-bot.service
cd /opt/quote-bot
rm -f main.py
# распаковать сохранённый backup обратно в /opt/quote-bot
/opt/quote-bot/venv/bin/python3 -m py_compile /opt/quote-bot/main.py
systemctl start quote-bot.service
```

Токены и `.env` в архив не входят.
