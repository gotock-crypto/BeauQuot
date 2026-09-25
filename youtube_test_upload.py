import json
import traceback

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

TOKEN = "youtube_upload_test_token.json"
VIDEO = "test_api_upload.mp4"

with open(TOKEN) as f:
    data = json.load(f)

creds = Credentials(
    token=data.get("token"),
    refresh_token=data.get("refresh_token"),
    token_uri=data.get("token_uri"),
    client_id=data.get("client_id"),
    client_secret=data.get("client_secret"),
    scopes=data.get("scopes"),
)

if creds.expired and creds.refresh_token:
    print("REFRESH TOKEN...")
    creds.refresh(Request())

print("AUTH OK")

youtube = build(
    "youtube",
    "v3",
    credentials=creds
)

body = {
    "snippet": {
        "title": "API DIAGNOSTIC TEST",
        "description": "Temporary diagnostic upload"
    },
    "status": {
        "privacyStatus": "private",
        "selfDeclaredMadeForKids": False
    }
}

media = MediaFileUpload(
    VIDEO,
    mimetype="video/mp4",
    resumable=True
)

print("CREATING UPLOAD REQUEST...")

request = youtube.videos().insert(
    part="snippet,status",
    body=body,
    media_body=media
)

try:

    print("STARTING UPLOAD...")

    response = None

    while response is None:

        status, response = request.next_chunk()

        if status:

            print(
                "PROGRESS:",
                int(status.progress() * 100),
                "%"
            )

    print("\n========== SUCCESS ==========\n")

    print(
        json.dumps(
            response,
            indent=2,
            ensure_ascii=False
        )
    )

except HttpError as e:

    print("\n========== HTTP ERROR ==========\n")

    print("STATUS:", e.resp.status)

    print("\nCONTENT:")

    try:
        print(
            json.dumps(
                json.loads(e.content.decode()),
                indent=2,
                ensure_ascii=False
            )
        )
    except Exception:
        print(e.content)

except Exception as e:

    print("\n========== ERROR ==========\n")

    print(type(e).__name__)
    print(str(e))

    traceback.print_exc()

