import os
from urllib.parse import urlparse, parse_qs
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Разрешаем localhost для ручного OAuth callback
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly"
]

SECRET = "youtube_client_secret.json"
TOKEN = "youtube_diagnose_token.json"

flow = InstalledAppFlow.from_client_secrets_file(
    SECRET,
    SCOPES
)

flow.redirect_uri = "http://localhost"

auth_url, _ = flow.authorization_url(
    access_type="offline",
    prompt="consent"
)

print("\nОткрой URL на своём Windows-компьютере:\n")
print(auth_url)

callback_url = input(
    "\nПосле авторизации скопируй ПОЛНЫЙ URL из адресной строки и вставь сюда:\n"
).strip()

# Получаем только authorization code из URL
parsed = urlparse(callback_url)
params = parse_qs(parsed.query)

auth_code = params.get("code", [None])[0]

if not auth_code:
    raise RuntimeError("Не найден параметр code в URL")

print("\nAUTH CODE FOUND")

flow.fetch_token(code=auth_code)

creds = flow.credentials

Path(TOKEN).write_text(
    creds.to_json(),
    encoding="utf-8"
)

youtube = build(
    "youtube",
    "v3",
    credentials=creds
)

response = youtube.channels().list(
    part="snippet,statistics,status,contentDetails",
    mine=True
).execute()

print("\n========== RESULT ==========\n")

items = response.get("items", [])

print("CHANNELS FOUND:", len(items))

for item in items:

    print("\nTITLE:", item["snippet"].get("title"))
    print("CHANNEL ID:", item.get("id"))
    print("CREATED:", item["snippet"].get("publishedAt"))

    print("\nSTATISTICS:")
    print(item.get("statistics"))

    print("\nSTATUS:")
    print(item.get("status"))

print("\n============================")
