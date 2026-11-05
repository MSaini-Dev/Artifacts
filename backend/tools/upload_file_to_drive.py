import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def get_drive_service():
    SCOPES = [
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/spreadsheets'
    ]
    # Look for client_secret_*.json either on desktop or in current directory
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
    client_secret_file = None
    
    search_dirs = [desktop_path, os.getcwd()]
    for d in search_dirs:
        if os.path.exists(d):
            for f in os.listdir(d):
                if f.startswith("client_secret_") and f.endswith(".json"):
                    client_secret_file = os.path.join(d, f)
                    break
        if client_secret_file:
            break
    
    if not client_secret_file:
        raise Exception("Client secret JSON file not found on desktop or current directory.")

    token_path = os.path.join(os.path.dirname(__file__), "sheets_token.json")
    creds = None
    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "wb") as token:
            pickle.dump(creds, token)

    return build('drive', 'v3', credentials=creds)

def upload_file_to_drive(file_path: str, folder_name: str = "profile") -> str:
    """
    Uploads a file to Google Drive. If folder_name is provided, it creates the folder
    (or finds it if it already exists) and uploads the file into that folder.
    """
    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"

    service = get_drive_service()

    parent_id = None
    if folder_name:
        # Check if folder exists
        query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
        results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        folders = results.get('files', [])

        if folders:
            parent_id = folders[0]['id']
        else:
            # Create folder
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = service.files().create(body=folder_metadata, fields='id').execute()
            parent_id = folder.get('id')

    file_metadata = {'name': os.path.basename(file_path)}
    if parent_id:
        file_metadata['parents'] = [parent_id]

    media = MediaFileUpload(file_path, resumable=True)
    uploaded_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, name, webViewLink'
    ).execute()

    return f"Successfully uploaded '{uploaded_file.get('name')}' to Google Drive (Folder: {folder_name or 'Root'}). File ID: {uploaded_file.get('id')}, Link: {uploaded_file.get('webViewLink')}"
