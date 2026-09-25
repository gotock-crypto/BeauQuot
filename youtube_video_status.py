import os
import json

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

TOKEN = "youtube_diagnose_token.json"

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
    creds.refresh(Request())

youtube = build(
    "youtube",
    "v3",
    credentials=creds
)

channel = youtube.channels().list(
    part="contentDetails",
    mine=True
).execute()

uploads = channel["items"][0][
    "contentDetails"
]["relatedPlaylists"]["uploads"]

playlist = youtube.playlistItems().list(
    part="contentDetails",
    playlistId=uploads,
    maxResults=10
).execute()

video_ids = []

for item in playlist.get("items", []):
    video_ids.append(
        item["contentDetails"]["videoId"]
    )

print("\nVIDEO IDS:")

for v in video_ids:
    print(v)

print("\n========== DETAILS ==========\n")

videos = youtube.videos().list(
    part="snippet,status,contentDetails,statistics",
    id=",".join(video_ids)
).execute()

for video in videos.get("items", []):

    print("\n==============================")

    print("TITLE:")
    print(video["snippet"].get("title"))

    print("\nVIDEO ID:")
    print(video["id"])

    print("\nPUBLISHED:")
    print(video["snippet"].get("publishedAt"))

    print("\nSTATUS:")
    print(json.dumps(
        video.get("status"),
        indent=2,
        ensure_ascii=False
    ))

    print("\nCONTENT:")
    print(json.dumps(
        video.get("contentDetails"),
        indent=2,
        ensure_ascii=False
    ))

    print("\nSTATISTICS:")
    print(json.dumps(
        video.get("statistics"),
        indent=2,
        ensure_ascii=False
    ))

print("\n==============================")
