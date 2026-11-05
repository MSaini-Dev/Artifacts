import os
import base64
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

def send_email(to: str, subject: str, body: str) -> str:
    """Send an email using the authenticated Gmail account. Use this tool when the user explicitly asks to send an email."""
    creds = None
    token_path = os.path.join(os.path.dirname(__file__), "token.json")
    credentials_path = os.path.join(os.path.dirname(__file__), "credentials.json")

    # If credentials.json is not found locally, try root credentials.json
    if not os.path.exists(credentials_path):
        root_creds = os.path.join(os.getcwd(), "credentials.json")
        if os.path.exists(root_creds):
            credentials_path = root_creds
        else:
            return "Error: missing credentials file (credentials.json). Please place it in backend/tools/ or the root directory."

    try:
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    # If refresh fails, re-authenticate
                    creds = None
            
            if not creds:
                if not os.path.exists(credentials_path):
                    return f"Error: credentials file not found at {credentials_path}"
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)

            with open(token_path, "w") as token:
                token.write(creds.to_json())

        service = build("gmail", "v1", credentials=creds)

        message = EmailMessage()
        message.set_content(body)
        message["To"] = to
        message["Subject"] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {"raw": encoded_message}

        sent_message = service.users().messages().send(userId="me", body=create_message).execute()
        return f"Email successfully sent to {to}. Message ID: {sent_message.get('id')}"

    except HttpError as error:
        return f"Gmail API error: {error}"
    except Exception as e:
        return f"Failed to send email: {str(e)}"
