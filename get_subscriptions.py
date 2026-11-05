import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CLIENT_SECRET_FILE = r"C:\Users\dell\Downloads\client_secret_412365166879-o0g02bjcp9l817a9mus8lgdqobel4mbg.apps.googleusercontent.com.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

def main():
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    
    youtube = build("youtube", "v3", credentials=creds)
    
    print("\nFetching your YouTube subscriptions:")
    request = youtube.subscriptions().list(
        part="snippet,contentDetails",
        mine=True,
        maxResults=50
    )
    
    channels = []
    while request is not None:
        response = request.execute()
        for item in response.get("items", []):
            title = item["snippet"]["title"]
            channel_id = item["snippet"]["resourceId"]["channelId"]
            channels.append((title, channel_id))
        request = youtube.subscriptions().list_next(request, response)
        
    print(f"\nTotal Subscriptions: {len(channels)}\n")
    for idx, (title, cid) in enumerate(channels, 1):
        print(f"{idx}. {title} (ID: {cid})")

if __name__ == "__main__":
    main()
