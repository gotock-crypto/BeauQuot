import os
import json

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

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
    part="contentDetails,snippet,statistics",
    mine=True
).execute()

item = channel["items"][0]

print("\n========== CHANNEL ==========\n")

print("TITLE:", item["snippet"]["title"])
print("CHANNEL ID:", item["id"])
print("VIDEOS:", item["statistics"].get("videoCount"))

uploads_playlist = item["contentDetails"]["relatedPlaylists"]["uploads"]

print("UPLOADS PLAYLIST:", uploads_playlist)

print("\n========== RECENT VIDEOS ==========\n")

response = youtube.playlistItems().list(
    part="snippet,contentDetails",
    playlistId=uploads_playlist,
    maxResults=20
).execute()

items = response.get("items", [])

print("FOUND:", len(items))

for i, video in enumerate(items, 1):

    snippet = video["snippet"]
    content = video["contentDetails"]

    print("\n----------------------------")

    print("", i)
    print("TITLE:", snippet.get("title"))
    print("VIDEO ID:", content.get("videoId"))
    print("PUBLISHED:", content.get("videoPublishedAt"))
    print("PLAYLIST ADDED:", content.get("videoPublishedAt"))

print("\n==============================")
