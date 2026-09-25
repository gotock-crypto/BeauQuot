import logging
from pathlib import Path
from pymax import Client, Photo

try:
    from pymax import Video
except ImportError:
    Video = None
log=logging.getLogger('quote_bot.max')
class MaxPublisher:
    def __init__(self, phone, session_name, work_dir, channel_id):
        self.work_dir=Path(work_dir); self.work_dir.mkdir(parents=True,exist_ok=True)
        self.client=Client(phone=phone, session_name=session_name, work_dir=str(self.work_dir))
        try:self.channel_id=int(str(channel_id).strip()) if channel_id else None
        except (TypeError,ValueError):self.channel_id=None
    def connected(self):
        v=getattr(self.client,'is_connected',False); return bool(v() if callable(v) else v)
    async def start(self):
        if not self.connected(): await self.client.connect()
    async def publish(self,text,media_path=''):
        await self.start()
        if not self.channel_id: raise RuntimeError('MAX_CHANNEL_ID not configured')
        kw = {'chat_id': self.channel_id,'text': text.strip()}
        if media_path and Path(media_path).is_file():
            suffix = Path(media_path).suffix.lower()
            if suffix == '.mp4':
                if Video is None: raise RuntimeError('pymax.Video is unavailable; cannot publish animated video')
                attachment = Video(path=str(media_path))
            else: attachment = Photo(path=str(media_path))
            kw['attachments'] = [attachment]
        msg = await self.client.send_message(**kw)
        return getattr(msg,'id',msg)
    async def close(self):
        try: await self.client.close()
        except Exception as exc: log.warning('MAX close error: %s',exc)