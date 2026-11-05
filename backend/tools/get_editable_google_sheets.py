import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive"
]

def get_editable_google_sheets() -> str:
    """
    Returns a newline-separated list of Google Spreadsheet names available to edit
    using the specified OAuth client secret and Google Sheets/Drive scopes.
    """
    possible_paths = [
        r"C:\Users\dell\Desktop\client_secret_412365166879-o0g02bjcp9l817a9mus8lgdqobel4mbg.apps.googleusercontent.com.json",
        r"C:\Users\dell\Downloads\client_secret_412365166879-o0g02bjcp9l817a9mus8lgdqobel4mbg.apps.googleusercontent.com.json",
        "client_secret.json",
        os.path.join(os.path.dirname(__file__), "client_secret.json")
    ]
    
    client_secret_path = None
    for path in possible_paths:
        if os.path.exists(path):
            client_secret_path = path
            break
            
    if not client_secret_path:
        return f"Error: client secret file not found in expected locations."
        
    token_path = os.path.join(os.path.dirname(__file__), "sheets_token_v3.json")
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token:
            token.write(creds.to_json())
            
    try:
        # First try Google Sheets API v4 spreadsheets.list if any, or Service usage API / Drive API
        # Wait, Google Drive API needs to be enabled in the Google Cloud Console for project 412365166879.
        # Let's try building sheets API or service usage API if available, or fallback to explaining the error clearly.
        service = build("drive", "v3", credentials=creds)
        query = "mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
        results = service.files().list(
            q=query,
            pageSize=100,
            fields="files(id, name, capabilities)"
        ).execute()
        files = results.get("files", [])
        
        editable_names = []
        for file in files:
            caps = file.get("capabilities", {})
            if caps.get("canEdit", False):
                editable_names.append(file.get("name"))
                
        if not editable_names:
            return "No editable Google Spreadsheets found."
            
        return "\n".join(editable_names)
    except Exception as e:
        err_str = str(e)
        if "accessNotConfigured" in err_str or "Google Drive API has not been used" in err_str:
            return (
                "Error: The Google Drive API is not yet enabled for your Google Cloud project (412365166879).\n"
                "Please visit the following URL to enable it:\n"
                "https://console.developers.google.com/apis/api/drive.googleapis.com/overview?project=412365166879\n"
                "After enabling it, wait 1-2 minutes and re-run the tool."
            )
        return f"Error accessing Google Drive API: {err_str}"
