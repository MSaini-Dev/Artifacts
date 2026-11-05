import os
from typing import List

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Scopes required for Google Tasks API
SCOPES = ["https://www.googleapis.com/auth/tasks"]

def _get_credentials() -> Credentials:
    """Load or obtain OAuth credentials for Google Tasks.
    Looks for client_secret.json in several common locations and stores
    the token in a file named `token_tasks.json` next to this tool.
    """
    possible_paths = [
        r"C:\\Users\\dell\\Desktop\\client_secret_412365166879-o0g02bjcp9l817a9mus8lgdqobel4mbg.apps.googleusercontent.com.json",
        r"C:\\Users\\dell\\Downloads\\client_secret_412365166879-o0g02bjcp9l817a9mus8lgdqobel4mbg.apps.googleusercontent.com.json",
        "client_secret.json",
        os.path.join(os.path.dirname(__file__), "client_secret.json"),
    ]
    client_secret_path = None
    for path in possible_paths:
        if os.path.exists(path):
            client_secret_path = path
            break
    if not client_secret_path:
        raise FileNotFoundError("client_secret.json not found in expected locations.")

    token_path = os.path.join(os.path.dirname(__file__), "token_tasks.json")
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    # Refresh or obtain new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())
    return creds

def google_task_manager(tasklist_name: str = "artifect", tasks: List[str] = None) -> str:
    """Create a Google Tasks tasklist (if it does not exist) and populate it uniquely.

    Args:
        tasklist_name: Name of the task list to create.
        tasks: List of task titles to add. If None a default set is used.

    Returns:
        Human‑readable summary of actions performed or error message.
    """
    if tasks is None:
        tasks = [
            "Brain",
            "Agent",
            "Memory",
            "Backend Server",
            "Frontend Server",
            "Mesh",
            "Dynamic Tools",
        ]
    try:
        creds = _get_credentials()
        service = build("tasks", "v1", credentials=creds)
        # Check if the tasklist already exists
        existing = service.tasklists().list(maxResults=100).execute()
        tasklist_id = None
        for tl in existing.get("items", []):
            if tl.get("title") == tasklist_name:
                tasklist_id = tl.get("id")
                break
        if not tasklist_id:
            created = service.tasklists().insert(body={"title": tasklist_name}).execute()
            tasklist_id = created.get("id")
            created_msg = f"Created tasklist '{tasklist_name}'."
        else:
            created_msg = f"Tasklist '{tasklist_name}' already exists."

        # Fetch existing tasks to prevent duplicates
        existing_tasks = service.tasks().list(tasklist=tasklist_id, maxResults=100).execute()
        existing_titles = {t.get("title") for t in existing_tasks.get("items", [])}

        # Insert missing tasks
        added = []
        for title in tasks:
            if title not in existing_titles:
                task_body = {"title": title}
                service.tasks().insert(tasklist=tasklist_id, body=task_body).execute()
                added.append(title)
                existing_titles.add(title)

        return (
            f"{created_msg}\nAdded tasks to '{tasklist_name}':\n- "
            + ("\n- ".join(added) if added else "(No new tasks added, all already existed)")
        )
    except Exception as e:
        return f"Error in google_task_manager: {e}"
