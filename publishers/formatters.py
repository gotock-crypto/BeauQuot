import html
import re


def _clean_tag(x):
    return re.sub(
        r'[^0-9A-Za-zА-Яа-яЁё_]+',
        '',
        str(x)
    ).lower()[:28]


def _tags(tags):
    out = []
    for x in tags or []:
        x = _clean_tag(x)
        if x and x not in out:
            out.append(x)
    for x in ('цитаты', 'мысли', 'вдохновение'):
        if len(out) >= 3:
            break
        if x not in out:
            out.append(x)
    return out[:3]


def _link(url, label):
    if not url:
        return ""
    safe_url = html.escape(url, quote=True)
    safe_label = html.escape(label)
    return f'<a href="{safe_url}">{safe_label}</a>'


def telegram_caption(content, telegram_url='', max_url='', limit=1024):
    q = html.escape(str(content.get('translated_quote', '')).strip()) or 'Цитата дня'
    a = html.escape(str(content.get('translated_author', '')).strip()) or 'BEAUQUOT'
    tags = ' '.join('#' + html.escape(x) for x in _tags(content.get('hashtags')))
    prefix = ' <b>ЦИТАТА ДНЯ</b>\n\n'
    links = []
    if telegram_url:
        links.append(_link(telegram_url, 'Telegram'))
    if max_url:
        links.append(_link(max_url, 'MAX'))
    suffix = f'\n\n <b>{a}</b>\n\n{tags}'
    if links:
        suffix += '\n\n Мы также здесь:\n' + '  '.join(links)
    budget = max(40, limit - len(prefix) - len(suffix) - 8)
    if len(q) > budget:
        q = q[:budget].rsplit(' ', 1)[0].rstrip() + ''
    return prefix + f'<i>{q}</i>' + suffix


def max_caption(content, telegram_url='', max_url=''):
    q = str(content.get('translated_quote', '')).strip() or 'Цитата дня'
    a = str(content.get('translated_author', '')).strip() or 'BEAUQUOT'
    tags = ' '.join('#' + x for x in _tags(content.get('hashtags')))
    result = ' ЦИТАТА ДНЯ\n\n' + f'{q}\n\n' + f' {a}\n\n' + f'{tags}'
    links = []
    if telegram_url:
        links.append(f'[Мы в Telegram]({telegram_url})')
    if max_url:
        links.append(f'[Мы в MAX]({max_url})')
    if links:
        result += '\n\n Мы также здесь:\n' + '  '.join(links)
    return result[:3900]