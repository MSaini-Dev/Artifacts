import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Scopes needed for listing and editing spreadsheets
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive",
]

# Absolute path to the client secret JSON on the Desktop
CLIENT_SECRET_PATH = r"C:\Users\dell\Downloads\client_secret_412365166879-o0g02bjcp9l817a9mus8lgdqobel4mbg.apps.googleusercontent.com.json"

def list_editable_sheets() -> str:
    """Return a newline‑separated list of Google Spreadsheet names that the authenticated user can edit.
    The function will create/refresh a token file (sheets_token.json) in the same directory as this tool.
    """
    creds = None
    token_path = os.path.join(os.path.dirname(__file__), "sheets_token.json")

    if not os.path.exists(CLIENT_SECRET_PATH):
        return f"Error: client secret file not found at {CLIENT_SECRET_PATH}"

    try:
        # Load existing credentials if present
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        # If no valid credentials, run the OAuth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            if not creds:
                flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(token_path, "w") as token_file:
                token_file.write(creds.to_json())

        # Use Drive API to list spreadsheets the user can edit
        drive_service = build("drive", "v3", credentials=creds)
        query = "mimeType = 'application/vnd.google-apps.spreadsheet'"
        results = (
            drive_service.files()
            .list(q=query, pageSize=200, fields="files(id, name, capabilities)")
            .execute()
        )
        files = results.get("files", [])
        if not files:
            return "No Google Spreadsheets found in Drive."

        editable = []
        for f in files:
            caps = f.get("capabilities", {})
            if caps.get("canEdit", True):
                editable.append(f["name"])  # only name as requested

        if not editable:
            return "No editable spreadsheets found."
        return "\n".join(editable)
    except HttpError as err:
        return f"Google API error: {err}"
    except Exception as exc:
        return f"Unexpected error: {exc}"