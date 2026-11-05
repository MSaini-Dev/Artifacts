import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/drive"]

def get_editable_sheets() -> str:
    """List all Google Spreadsheets that are available/accessible to edit using the authenticated Google account and client secret."""
    creds = None
    token_path = os.path.join(os.path.dirname(__file__), "sheets_token.json")
    client_secret_path = os.path.join(os.path.dirname(__file__), "client_secret.json")

    if not os.path.exists(client_secret_path):
        # Fallback to root or other paths
        for p in [os.path.join(os.getcwd(), "client_secret.json"), "client_secret_412365166879-o0g02bjcp9l817a9mus8lgdqobel4mbg.apps.googleusercontent.com.json"]:
            if os.path.exists(p):
                client_secret_path = p
                break
        else:
            return "Error: client_secret JSON file not found."

    try:
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            
            if not creds:
                flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
                creds = flow.run_local_server(port=0)

            with open(token_path, "w") as token:
                token.write(creds.to_json())

        # Use Google Drive API to list Google Sheets files that the user can edit
        drive_service = build("drive", "v3", credentials=creds)
        
        # Query for Google Spreadsheets
        query = "mimeType = 'application/vnd.google-apps.spreadsheet'"
        results = drive_service.files().list(
            q=query,
            pageSize=100,
            fields="files(id, name, capabilities)"
        ).execute()
        
        items = results.get("files", [])
        if not items:
            return "No Google Spreadsheets found in your Google Drive."

        editable_sheets = []
        for item in items:
            caps = item.get("capabilities", {})
            # Check if user can edit this file
            if caps.get("canEdit", True):
                editable_sheets.append(f"- Name: {item['name']} (ID: {item['id']})")

        if not editable_sheets:
            return "Found Google Spreadsheets, but none are editable with the current permissions."

        return "Editable Google Spreadsheets:\n" + "\n".join(editable_sheets)

    except HttpError as error:
        return f"Google API error: {error}"
    except Exception as e:
        return f"Failed to list sheets: {str(e)}"
