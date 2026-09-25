import os
from urllib.parse import urlparse, parse_qs
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload"
]

SECRET = "youtube_client_secret.json"
TOKEN = "youtube_upload_test_token.json"

flow = InstalledAppFlow.from_client_secrets_file(
    SECRET,
    SCOPES
)

flow.redirect_uri = "http://localhost"

auth_url, _ = flow.authorization_url(
    access_type="offline",
    prompt="consent"
)

print("\nОткрой URL на компьютере:\n")
print(auth_url)

callback_url = input(
    "\nПосле авторизации вставь ПОЛНЫЙ URL из браузера:\n"
).strip()

parsed = urlparse(callback_url)
params = parse_qs(parsed.query)

auth_code = params.get("code", [None])[0]

if not auth_code:
    raise RuntimeError("Authorization code не найден")

print("\nAUTH CODE FOUND")

flow.fetch_token(code=auth_code)

creds = flow.credentials

Path(TOKEN).write_text(
    creds.to_json(),
    encoding="utf-8"
)

print("\nTOKEN SAVED:", TOKEN)

youtube = build(
    "youtube",
    "v3",
    credentials=creds
)

print("\nTESTING UPLOAD SCOPE...\n")

try:

    response = youtube.channels().list(
        part="snippet",
        mine=True
    ).execute()

    print("CHANNEL TEST OK")

    for item in response.get("items", []):
        print("CHANNEL:", item["snippet"]["title"])

except Exception as e:

    print("CHANNEL TEST ERROR:")
    print(type(e).__name__)
    print(str(e))

print("\nDONE")
