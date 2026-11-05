import os
import requests
from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_SECRET_FILE = r"C:\Users\dell\Downloads\client_secret_412365166879-o0g02bjcp9l817a9mus8lgdqobel4mbg.apps.googleusercontent.com.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

def main():
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    
    token = creds.token
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    url = "https://www.googleapis.com/youtube/v3/subscriptions?part=snippet,contentDetails&mine=true&maxResults=50"
    print("Making GET request to:", url)
    resp = requests.get(url, headers=headers)
    print("Status Code:", resp.status_code)
    print("Response Body:")
    print(resp.text)

if __name__ == "__main__":
    main()
