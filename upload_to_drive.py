import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def main():
    creds = None
    token_path = 'token_drive.json'
    client_secret_path = r'C:\Users\dell\Downloads\client_secret_412365166879-o0g02bjcp9l817a9mus8lgdqobel4mbg.apps.googleusercontent.com.json'

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())

    service = build('drive', 'v3', credentials=creds)

    # Find or create 'profile' folder
    folder_name = 'profile'
    page_token = None
    folder_id = None
    while True:
        response = service.files().list(
            q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            spaces='drive',
            fields='nextPageToken, files(id, name)',
            pageToken=page_token
        ).execute()
        for folder in response.get('files', []):
            folder_id = folder.get('id')
            break
        page_token = response.get('nextPageToken', None)
        if folder_id or not page_token:
            break

    if not folder_id:
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = service.files().create(body=file_metadata, fields='id').execute()
        folder_id = folder.get('id')
        print(f"Created folder '{folder_name}' with ID: {folder_id}")
    else:
        print(f"Found folder '{folder_name}' with ID: {folder_id}")

    file_path = r'C:\Users\dell\Downloads\Cinematic Starfield and Planet Rim.png'
    file_name = os.path.basename(file_path)

    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    print(f"File ID: {file.get('id')}")
    print(f"Web View Link: {file.get('webViewLink')}")

if __name__ == '__main__':
    main()
