import os
import csv
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CLIENT_SECRET_FILE = r"C:\Users\dell\Downloads\client_secret_412365166879-o0g02bjcp9l817a9mus8lgdqobel4mbg.apps.googleusercontent.com.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

def main():
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    
    youtube = build("youtube", "v3", credentials=creds)
    
    # 1. Find the playlist named "Song 2"
    print("Searching for playlist 'Song 2'...")
    playlists_request = youtube.playlists().list(
        part="snippet",
        mine=True,
        maxResults=50
    )
    
    playlist_id = None
    while playlists_request is not None:
        response = playlists_request.execute()
        for item in response.get("items", []):
            title = item["snippet"]["title"]
            print(f"Found playlist: {title} ({item['id']})")
            if title.strip().lower() == "song 2":
                playlist_id = item["id"]
                break
        if playlist_id:
            break
        playlists_request = youtube.playlists().list_next(playlists_request, response)
        
    if not playlist_id:
        print("Error: Could not find a playlist named 'Song 2'.")
        return
        
    print(f"Found playlist 'Song 2' with ID: {playlist_id}")
    
    # 2. Fetch all videos in this playlist
    videos = []
    playlist_items_request = youtube.playlistItems().list(
        part="snippet",
        playlistId=playlist_id,
        maxResults=50
    )
    
    while playlist_items_request is not None:
        response = playlist_items_request.execute()
        for item in response.get("items", []):
            snippet = item["snippet"]
            video_title = snippet["title"]
            resource_id = snippet.get("resourceId", {})
            video_id = resource_id.get("videoId")
            if video_id:
                video_link = f"https://www.youtube.com/watch?v={video_id}"
                videos.append((video_title, video_link))
        playlist_items_request = youtube.playlistItems().list_next(playlist_items_request, response)
        
    print(f"Found {len(videos)} videos in playlist 'Song 2'.")
    
    # 3. Write to CSV on Desktop
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
    csv_file_path = os.path.join(desktop_path, "Song_2_playlist.csv")
    
    with open(csv_file_path, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Video Name", "Video Link"])
        for title, link in videos:
            writer.writerow([title, link])
            
    print(f"Successfully created CSV file at: {csv_file_path}")

if __name__ == "__main__":
    main()
