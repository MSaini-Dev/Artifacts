"""Purpose-specific Google Drive, Gmail, Sheets, and Tasks tools."""

import base64
import os
import uuid
from email.message import EmailMessage
from pathlib import Path
from typing import Literal, Optional


_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/tasks",
]


def _client_secret_path():
    configured = os.getenv("GOOGLE_OAUTH_CLIENT_SECRETS")
    candidates = [
        Path(configured).expanduser() if configured else None,
        Path(__file__).with_name("credentials.json"),
        Path(__file__).with_name("client_secret.json"),
        Path(__file__).resolve().parents[2] / "credentials.json",
        Path(__file__).resolve().parents[2] / "client_secret.json",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Google OAuth client secrets not found. Set GOOGLE_OAUTH_CLIENT_SECRETS "
        "or place credentials.json/client_secret.json in the project root or backend/tools."
    )


def _credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_path = Path(
        os.getenv(
            "GOOGLE_WORKSPACE_TOKEN_PATH",
            str(Path(__file__).with_name("google_workspace_token.json")),
        )
    ).expanduser()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    credentials = None
    if token_path.is_file():
        credentials = Credentials.from_authorized_user_file(str(token_path), _SCOPES)

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    elif not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(_client_secret_path()), _SCOPES)
        credentials = flow.run_local_server(port=0)

    token_path.write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def _service(api, version):
    from googleapiclient.discovery import build

    return build(api, version, credentials=_credentials(), cache_discovery=False)


def _drive():
    return _service("drive", "v3")


def _gmail():
    return _service("gmail", "v1")


def _sheets():
    return _service("sheets", "v4")


def _tasks():
    return _service("tasks", "v1")


def _email_message(to, subject, body, cc="", bcc="", attachments=None):
    import mimetypes

    if not to.strip():
        raise ValueError("At least one recipient address is required")
    if not subject.strip():
        raise ValueError("An email subject is required")
    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject
    if cc:
        message["Cc"] = cc
    if bcc:
        message["Bcc"] = bcc
    message.set_content(body)
    for file_path in attachments or []:
        path = Path(file_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Email attachment not found: {path}")
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        message.add_attachment(
            path.read_bytes(),
            maintype=content_type.split("/")[0],
            subtype=content_type.split("/")[1],
            filename=path.name,
        )
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


def _decode_gmail_text(part):
    mime_type = part.get("mimeType", "")
    data = part.get("body", {}).get("data")
    if data and mime_type == "text/plain":
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
    return "".join(_decode_gmail_text(child) for child in part.get("parts", []))


def search_drive_files(
    query: str = "",
    page_size: int = 20,
    page_token: str = "",
    operation: Literal["list", "generate_ids", "get_start_page_token"] = "list",
    count: int = 10,
) -> dict:
    """Search/list files, generate IDs, or get a changes start token; operation is list, generate_ids, or get_start_page_token."""
    drive = _drive()
    if operation == "generate_ids":
        return drive.files().generateIds(count=max(1, min(count, 1000))).execute()
    if operation == "get_start_page_token":
        return drive.changes().getStartPageToken().execute()
    if operation != "list":
        raise ValueError("operation must be list, generate_ids, or get_start_page_token")
    params = {
        "pageSize": max(1, min(page_size, 1000)),
        "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink,parents,size)",
        "orderBy": "modifiedTime desc",
    }
    if query:
        params["q"] = query
    if page_token:
        params["pageToken"] = page_token
    return drive.files().list(**params).execute()


def read_drive_file(file_id: str, include_content: bool = False, export_mime_type: str = "text/plain") -> dict:
    """Read Drive file metadata, and optionally its text content or exported Google Workspace content."""
    drive = _drive()
    metadata = drive.files().get(fileId=file_id, fields="*").execute()
    if not include_content:
        return metadata
    mime_type = metadata.get("mimeType", "")
    if mime_type.startswith("application/vnd.google-apps."):
        content = drive.files().export_media(fileId=file_id, mimeType=export_mime_type).execute()
    else:
        content = drive.files().get_media(fileId=file_id).execute()
    if isinstance(content, str):
        content = content.encode("utf-8")
    metadata["content_mime_type"] = export_mime_type if mime_type.startswith(
        "application/vnd.google-apps."
    ) else mime_type
    content_mime_type = metadata["content_mime_type"]
    if content_mime_type.startswith("text/") or content_mime_type in {
        "application/json",
        "application/xml",
    }:
        metadata["content_text"] = content.decode("utf-8", errors="replace")
    else:
        metadata["content_base64"] = base64.b64encode(content).decode("ascii")
    return metadata


def download_export_drive_file(
    file_id: str,
    destination_path: str,
    export_mime_type: str = "application/pdf",
) -> dict:
    """Download a Drive file or export a Google Workspace file to a local destination path."""
    import io

    from googleapiclient.http import MediaIoBaseDownload

    drive = _drive()
    metadata = drive.files().get(fileId=file_id, fields="id,name,mimeType").execute()
    mime_type = metadata.get("mimeType", "")
    request = (
        drive.files().export_media(fileId=file_id, mimeType=export_mime_type)
        if mime_type.startswith("application/vnd.google-apps.")
        else drive.files().get_media(fileId=file_id)
    )
    destination = Path(destination_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as target:
        downloader = MediaIoBaseDownload(target, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    return {"file_id": file_id, "name": metadata.get("name"), "path": str(destination)}


def upload_create_drive_file(
    name: str,
    mime_type: str = "application/octet-stream",
    parent_id: str = "",
    local_file_path: str = "",
    content: str = "",
) -> dict:
    """Create a Drive folder/file or upload a local file; provide local_file_path or text content for file uploads."""
    from googleapiclient.http import MediaFileUpload, MediaInMemoryUpload

    metadata = {"name": name, "mimeType": mime_type}
    if parent_id:
        metadata["parents"] = [parent_id]
    media = None
    if local_file_path:
        path = Path(local_file_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Upload file not found: {path}")
        media = MediaFileUpload(str(path), mimetype=mime_type, resumable=True)
    elif content:
        media = MediaInMemoryUpload(content.encode("utf-8"), mimetype=mime_type, resumable=True)
    return _drive().files().create(
        body=metadata,
        media_body=media,
        fields="id,name,mimeType,webViewLink,parents",
    ).execute()


def update_move_copy_drive_file(
    file_id: str,
    operation: Literal["update", "move", "replace_content", "copy", "list_labels", "modify_labels", "watch"],
    name: str = "",
    add_parent_id: str = "",
    remove_parent_id: str = "",
    local_file_path: str = "",
    destination_parent_id: str = "",
    label_modifications: Optional[dict] = None,
    channel_body: Optional[dict] = None,
) -> dict:
    """Update, move, replace content, copy, list/modify labels, or watch a Drive file; set operation accordingly."""
    drive = _drive()
    if operation == "list_labels":
        return drive.files().listLabels(fileId=file_id).execute()
    if operation == "modify_labels":
        return drive.files().modifyLabels(fileId=file_id, body=label_modifications or {}).execute()
    if operation == "watch":
        return drive.files().watch(fileId=file_id, body=channel_body or {}).execute()
    if operation == "copy":
        body = {"name": name} if name else {}
        if destination_parent_id:
            body["parents"] = [destination_parent_id]
        return drive.files().copy(fileId=file_id, body=body, fields="id,name,mimeType,parents").execute()
    if operation not in {"update", "move", "replace_content"}:
        raise ValueError("operation must be update, move, replace_content, or copy")
    body = {"name": name} if name else {}
    params = {"fileId": file_id, "body": body, "fields": "id,name,mimeType,parents"}
    if operation == "move":
        if not add_parent_id and not destination_parent_id:
            raise ValueError("Provide add_parent_id or destination_parent_id when moving a file")
        params["addParents"] = add_parent_id or destination_parent_id
        if remove_parent_id:
            params["removeParents"] = remove_parent_id
    if operation == "replace_content":
        if not local_file_path:
            raise ValueError("local_file_path is required to replace file content")
        from googleapiclient.http import MediaFileUpload

        path = Path(local_file_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Replacement file not found: {path}")
        params["media_body"] = MediaFileUpload(str(path), resumable=True)
    return drive.files().update(**params).execute()


def delete_restore_drive_file(
    file_id: str = "",
    operation: Literal["trash", "restore", "permanent_delete", "empty_trash"] = "trash",
    confirm_permanent: bool = False,
) -> dict:
    """Trash/restore/delete a file or empty trash; permanent_delete and empty_trash require confirm_permanent=true."""
    drive = _drive()
    if operation == "empty_trash":
        if not confirm_permanent:
            raise ValueError("Set confirm_permanent=true to permanently empty Drive trash")
        drive.files().emptyTrash().execute()
        return {"success": True, "operation": operation}
    if not file_id:
        raise ValueError("file_id is required for trash, restore, or permanent_delete")
    if operation == "trash":
        return drive.files().update(fileId=file_id, body={"trashed": True}, fields="id,name,trashed").execute()
    if operation == "restore":
        return drive.files().update(fileId=file_id, body={"trashed": False}, fields="id,name,trashed").execute()
    if operation == "permanent_delete":
        if not confirm_permanent:
            raise ValueError("Set confirm_permanent=true to permanently delete a Drive file")
        drive.files().delete(fileId=file_id).execute()
        return {"success": True, "file_id": file_id, "operation": operation}
    raise ValueError("operation must be trash, restore, permanent_delete, or empty_trash")


def manage_drive_permissions(
    file_id: str,
    operation: Literal["list", "get", "create", "update", "delete"],
    permission_id: str = "",
    body: Optional[dict] = None,
) -> dict:
    """Manage Drive sharing; operation is list, get, create, update, or delete. Create/update use body as a permission."""
    permissions = _drive().permissions()
    if operation == "list":
        return permissions.list(fileId=file_id, fields="permissions(id,type,emailAddress,role,displayName)").execute()
    if operation == "get":
        return permissions.get(fileId=file_id, permissionId=permission_id, fields="*").execute()
    if operation == "create":
        return permissions.create(fileId=file_id, body=body or {}, fields="id,type,emailAddress,role").execute()
    if operation == "update":
        return permissions.update(
            fileId=file_id, permissionId=permission_id, body=body or {}, fields="id,type,emailAddress,role"
        ).execute()
    if operation == "delete":
        permissions.delete(fileId=file_id, permissionId=permission_id).execute()
        return {"success": True, "permission_id": permission_id}
    raise ValueError("operation must be list, get, create, update, or delete")


def manage_drive_comments(
    file_id: str,
    operation: Literal[
        "list_comments", "create_comment", "get_comment", "update_comment", "delete_comment",
        "list_replies", "create_reply", "get_reply", "update_reply", "delete_reply",
    ],
    comment_id: str = "",
    reply_id: str = "",
    body: Optional[dict] = None,
) -> dict:
    """Manage Drive comments and replies; operation selects list/create/get/update/delete for comments or replies."""
    drive = _drive()
    if operation == "list_comments":
        return drive.comments().list(fileId=file_id, fields="comments(id,content,author,createdTime,modifiedTime)").execute()
    if operation == "create_comment":
        return drive.comments().create(fileId=file_id, body=body or {}, fields="*").execute()
    if operation == "get_comment":
        return drive.comments().get(fileId=file_id, commentId=comment_id, fields="*").execute()
    if operation == "update_comment":
        return drive.comments().update(fileId=file_id, commentId=comment_id, body=body or {}, fields="*").execute()
    if operation == "delete_comment":
        drive.comments().delete(fileId=file_id, commentId=comment_id).execute()
        return {"success": True, "comment_id": comment_id}
    if operation == "list_replies":
        return drive.replies().list(fileId=file_id, commentId=comment_id, fields="replies(id,content,author)").execute()
    if operation == "create_reply":
        return drive.replies().create(fileId=file_id, commentId=comment_id, body=body or {}, fields="*").execute()
    if operation == "get_reply":
        return drive.replies().get(fileId=file_id, commentId=comment_id, replyId=reply_id, fields="*").execute()
    if operation == "update_reply":
        return drive.replies().update(
            fileId=file_id, commentId=comment_id, replyId=reply_id, body=body or {}, fields="*"
        ).execute()
    if operation == "delete_reply":
        drive.replies().delete(fileId=file_id, commentId=comment_id, replyId=reply_id).execute()
        return {"success": True, "reply_id": reply_id}
    raise ValueError("Unsupported comment/reply operation")


def manage_drive_revisions(
    file_id: str,
    operation: Literal["list", "get", "update", "delete"],
    revision_id: str = "",
    body: Optional[dict] = None,
    include_content: bool = False,
) -> dict:
    """List, read, update, or delete Drive file revisions; set include_content to download revision bytes."""
    revisions = _drive().revisions()
    if operation == "list":
        return revisions.list(fileId=file_id, fields="revisions(id,modifiedTime,keepForever,size)").execute()
    if operation == "get":
        if include_content:
            content = revisions.get(fileId=file_id, revisionId=revision_id, alt="media").execute()
            if isinstance(content, str):
                content = content.encode("utf-8")
            return {"file_id": file_id, "revision_id": revision_id, "content_base64": base64.b64encode(content).decode("ascii")}
        return revisions.get(fileId=file_id, revisionId=revision_id, fields="*").execute()
    if operation == "update":
        return revisions.update(
            fileId=file_id, revisionId=revision_id, body=body or {}, fields="*"
        ).execute()
    if operation == "delete":
        revisions.delete(fileId=file_id, revisionId=revision_id).execute()
        return {"success": True, "revision_id": revision_id}
    raise ValueError("operation must be list, get, update, or delete")


def manage_shared_drives_and_access(
    operation: Literal[
        "about", "list_apps", "get_app", "generate_cse_token", "list_drives", "create_drive",
        "get_drive", "update_drive", "delete_drive", "hide_drive", "unhide_drive",
        "list_access_proposals", "get_access_proposal", "resolve_access_proposal",
        "list_approvals", "get_approval", "approve", "decline", "cancel", "comment",
        "reassign", "start_approval", "list_changes", "start_change_watch", "stop_channel",
        "get_operation",
    ],
    drive_id: str = "",
    file_id: str = "",
    proposal_id: str = "",
    approval_id: str = "",
    page_token: str = "",
    body: Optional[dict] = None,
    app_id: str = "",
    operation_name: str = "",
    request_id: str = "",
    confirm_permanent: bool = False,
) -> dict:
    """Manage Drive account/shared-drive resources; operation selects about/apps/drives/access proposals/approvals/changes."""
    drive = _drive()
    if operation == "about":
        return drive.about().get(fields="user,storageQuota,driveId,canCreateDrives").execute()
    if operation == "list_apps":
        return drive.apps().list().execute()
    if operation == "get_app":
        return drive.apps().get(appId=app_id).execute()
    if operation == "generate_cse_token":
        return drive.files().generateCseToken(body=body or {}).execute()
    if operation == "list_drives":
        params = {"pageSize": 100, "fields": "nextPageToken,drives(id,name,hidden,createdTime)"}
        if page_token:
            params["pageToken"] = page_token
        return drive.drives().list(**params).execute()
    if operation == "create_drive":
        return drive.drives().create(
            body=body or {},
            requestId=request_id or uuid.uuid4().hex,
        ).execute()
    if operation in {"get_drive", "update_drive", "delete_drive", "hide_drive", "unhide_drive"}:
        if not drive_id:
            raise ValueError("drive_id is required for this operation")
        if operation == "get_drive":
            return drive.drives().get(driveId=drive_id, fields="*").execute()
        if operation == "update_drive":
            return drive.drives().update(driveId=drive_id, body=body or {}, fields="*").execute()
        if operation == "delete_drive":
            if not confirm_permanent:
                raise ValueError("Set confirm_permanent=true to permanently delete a shared drive")
            drive.drives().delete(driveId=drive_id).execute()
            return {"success": True, "drive_id": drive_id}
        if operation == "hide_drive":
            return drive.drives().hide(driveId=drive_id).execute()
        return drive.drives().unhide(driveId=drive_id).execute()
    if operation == "list_access_proposals":
        return drive.accessproposals().list(fileId=file_id, fields="*").execute()
    if operation == "get_access_proposal":
        return drive.accessproposals().get(fileId=file_id, proposalId=proposal_id).execute()
    if operation == "resolve_access_proposal":
        return drive.accessproposals().resolve(
            fileId=file_id, proposalId=proposal_id, body=body or {}
        ).execute()
    if operation == "list_approvals":
        return drive.approvals().list(fileId=file_id, fields="*").execute()
    if operation in {"get_approval", "approve", "decline", "cancel", "comment", "reassign"}:
        approvals = drive.approvals()
        if operation == "get_approval":
            return approvals.get(fileId=file_id, approvalId=approval_id).execute()
        return getattr(approvals, operation)(
            fileId=file_id, approvalId=approval_id, body=body or {}
        ).execute()
    if operation == "start_approval":
        return drive.approvals().start(fileId=file_id, body=body or {}).execute()
    if operation == "list_changes":
        return drive.changes().list(pageToken=page_token or None, fields="*").execute()
    if operation == "start_change_watch":
        return drive.changes().watch(body=body or {}).execute()
    if operation == "get_operation":
        return drive.operations().get(name=operation_name).execute()
    if operation == "stop_channel":
        return drive.channels().stop(body=body or {}).execute()
    raise ValueError("Unsupported shared-drive/access operation")


def search_emails(
    query: str = "",
    page_size: int = 20,
    page_token: str = "",
    include_spam_trash: bool = False,
    resource: Literal["messages", "threads"] = "messages",
) -> dict:
    """Search Gmail messages or threads with Gmail query syntax; resource is messages or threads."""
    params = {"userId": "me", "maxResults": max(1, min(page_size, 500)), "includeSpamTrash": include_spam_trash}
    if query:
        params["q"] = query
    if page_token:
        params["pageToken"] = page_token
    if resource == "messages":
        return _gmail().users().messages().list(**params).execute()
    if resource == "threads":
        return _gmail().users().threads().list(**params).execute()
    raise ValueError("resource must be messages or threads")


def read_email(
    message_id: str = "",
    thread_id: str = "",
    format: Literal["full", "metadata", "minimal"] = "full",
    attachment_id: str = "",
) -> dict:
    """Read a Gmail message/thread or an attachment; provide exactly one message_id or thread_id (message_id for attachments)."""
    if attachment_id:
        if not message_id:
            raise ValueError("message_id is required to read an attachment")
        return _gmail().users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()
    if bool(message_id) == bool(thread_id):
        raise ValueError("Provide exactly one of message_id or thread_id")
    gmail = _gmail()
    if message_id:
        result = gmail.users().messages().get(userId="me", id=message_id, format=format).execute()
        result["body_text"] = _decode_gmail_text(result.get("payload", {}))
        return result
    result = gmail.users().threads().get(userId="me", id=thread_id, format=format).execute()
    for message in result.get("messages", []):
        message["body_text"] = _decode_gmail_text(message.get("payload", {}))
    return result


def send_email(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    attachments: Optional[list] = None,
) -> dict:
    """Send an email through Gmail, optionally with comma-separated Cc/Bcc recipients and local file attachments."""
    raw = _email_message(to, subject, body, cc, bcc, attachments)
    return _gmail().users().messages().send(userId="me", body={"raw": raw}).execute()


def manage_email_drafts(
    operation: Literal["create", "list", "get", "update", "delete", "send"],
    draft_id: str = "",
    to: str = "",
    subject: str = "",
    body: str = "",
    cc: str = "",
    bcc: str = "",
) -> dict:
    """Create, list, read, update, delete, or send Gmail drafts; operation selects the draft action."""
    gmail = _gmail().users().drafts()
    if operation == "list":
        return gmail.list(userId="me").execute()
    if operation == "get":
        return gmail.get(userId="me", id=draft_id).execute()
    if operation in {"create", "update"}:
        raw = _email_message(to, subject, body, cc, bcc)
        draft = {"message": {"raw": raw}}
        if operation == "create":
            return gmail.create(userId="me", body=draft).execute()
        return gmail.update(userId="me", id=draft_id, body=draft).execute()
    if operation == "delete":
        gmail.delete(userId="me", id=draft_id).execute()
        return {"success": True, "draft_id": draft_id}
    if operation == "send":
        return gmail.send(userId="me", body={"id": draft_id}).execute()
    raise ValueError("operation must be create, list, get, update, delete, or send")


def manage_email_labels(
    operation: Literal["create", "list", "get", "update", "patch", "delete"],
    label_id: str = "",
    body: Optional[dict] = None,
) -> dict:
    """Create, list, read, update, patch, or delete Gmail labels; operation selects the label action."""
    labels = _gmail().users().labels()
    if operation == "list":
        return labels.list(userId="me").execute()
    if operation == "create":
        return labels.create(userId="me", body=body or {}).execute()
    if operation == "get":
        return labels.get(userId="me", id=label_id).execute()
    if operation in {"update", "patch"}:
        method = labels.update if operation == "update" else labels.patch
        return method(userId="me", id=label_id, body=body or {}).execute()
    if operation == "delete":
        labels.delete(userId="me", id=label_id).execute()
        return {"success": True, "label_id": label_id}
    raise ValueError("operation must be create, list, get, update, patch, or delete")


def manage_email_messages(
    operation: Literal[
        "modify", "trash", "untrash", "delete", "batch_modify", "batch_delete",
        "thread_modify", "thread_trash", "thread_untrash", "thread_delete", "import", "insert",
    ],
    message_id: str = "",
    message_ids: Optional[list] = None,
    add_label_ids: Optional[list] = None,
    remove_label_ids: Optional[list] = None,
    thread_id: str = "",
    raw_message: str = "",
    never_mark_spam: bool = False,
    process_for_calendar: bool = False,
    internal_date_source: str = "",
    confirm_permanent: bool = False,
) -> dict:
    """Modify/trash/restore/delete messages or threads, batch-update messages, or import/insert raw mail; permanent deletes require confirmation."""
    users = _gmail().users()
    gmail = users.messages()
    if operation == "modify":
        return gmail.modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": add_label_ids or [], "removeLabelIds": remove_label_ids or []},
        ).execute()
    if operation == "trash":
        return gmail.trash(userId="me", id=message_id).execute()
    if operation == "untrash":
        return gmail.untrash(userId="me", id=message_id).execute()
    if operation == "delete":
        if not confirm_permanent:
            raise ValueError("Set confirm_permanent=true to permanently delete a Gmail message")
        gmail.delete(userId="me", id=message_id).execute()
        return {"success": True, "message_id": message_id}
    if operation == "batch_modify":
        return gmail.batchModify(
            userId="me",
            body={"ids": message_ids or [], "addLabelIds": add_label_ids or [], "removeLabelIds": remove_label_ids or []},
        ).execute()
    if operation == "batch_delete":
        if not confirm_permanent:
            raise ValueError("Set confirm_permanent=true to permanently delete Gmail messages")
        gmail.batchDelete(userId="me", body={"ids": message_ids or []}).execute()
        return {"success": True, "message_ids": message_ids or []}
    if operation in {"thread_modify", "thread_trash", "thread_untrash", "thread_delete"}:
        threads = users.threads()
        if operation == "thread_modify":
            return threads.modify(
                userId="me",
                id=thread_id,
                body={"addLabelIds": add_label_ids or [], "removeLabelIds": remove_label_ids or []},
            ).execute()
        if operation == "thread_trash":
            return threads.trash(userId="me", id=thread_id).execute()
        if operation == "thread_untrash":
            return threads.untrash(userId="me", id=thread_id).execute()
        if not confirm_permanent:
            raise ValueError("Set confirm_permanent=true to permanently delete a Gmail thread")
        threads.delete(userId="me", id=thread_id).execute()
        return {"success": True, "thread_id": thread_id}
    if operation in {"import", "insert"}:
        if not raw_message:
            raise ValueError("raw_message must contain the URL-safe base64 RFC 2822 email")
        body = {"raw": raw_message}
        if operation == "import":
            return gmail.import_(
                userId="me",
                body=body,
                neverMarkSpam=never_mark_spam,
                processForCalendar=process_for_calendar,
                internalDateSource=internal_date_source or None,
            ).execute()
        return gmail.insert(userId="me", body=body).execute()
    raise ValueError("Unsupported Gmail message/thread operation")


def get_mailbox_activity(
    operation: Literal["profile", "history", "stop_watch", "watch"] = "profile",
    start_history_id: str = "",
    history_types: Optional[list] = None,
    watch_body: Optional[dict] = None,
) -> dict:
    """Get mailbox profile/history or start/stop Gmail push notifications; watch requires watch_body with a topic."""
    users = _gmail().users()
    if operation == "profile":
        return users.getProfile(userId="me").execute()
    if operation == "history":
        params = {"userId": "me", "startHistoryId": start_history_id}
        if history_types:
            params["historyTypes"] = history_types
        return users.history().list(**params).execute()
    if operation == "stop_watch":
        return users.stop(userId="me").execute()
    if operation == "watch":
        return users.watch(userId="me", body=watch_body or {}).execute()
    raise ValueError("operation must be profile, history, stop_watch, or watch")


def manage_gmail_settings(
    operation: Literal[
        "list_filters", "create_filter", "get_filter", "delete_filter",
        "list_forwarding", "create_forwarding", "get_forwarding", "delete_forwarding",
        "list_send_as", "create_send_as", "get_send_as", "update_send_as", "patch_send_as",
        "delete_send_as", "verify_send_as", "list_delegates", "create_delegate", "get_delegate",
        "delete_delegate", "get_setting", "update_setting", "list_smime", "insert_smime",
        "get_smime", "delete_smime", "set_default_smime", "list_cse_identities",
        "create_cse_identity", "get_cse_identity", "patch_cse_identity", "delete_cse_identity",
        "list_cse_keypairs", "create_cse_keypair", "get_cse_keypair", "enable_cse_keypair",
        "disable_cse_keypair", "obliterate_cse_keypair",
    ],
    item_id: str = "",
    body: Optional[dict] = None,
    setting_type: str = "",
    email_address: str = "",
    key_pair_id: str = "",
    smime_id: str = "",
) -> dict:
    """Manage Gmail settings; operation explicitly selects filters, forwarding, aliases, delegates, IMAP/POP, S/MIME, or CSE."""
    settings = _gmail().users().settings()
    if operation in {"list_filters", "create_filter", "get_filter", "delete_filter"}:
        filters = settings.filters()
        if operation == "list_filters":
            return filters.list(userId="me").execute()
        if operation == "create_filter":
            return filters.create(userId="me", body=body or {}).execute()
        if operation == "get_filter":
            return filters.get(userId="me", id=item_id).execute()
        filters.delete(userId="me", id=item_id).execute()
        return {"success": True, "filter_id": item_id}
    if operation in {"list_forwarding", "create_forwarding", "get_forwarding", "delete_forwarding"}:
        forwarding = settings.forwardingAddresses()
        if operation == "list_forwarding":
            return forwarding.list(userId="me").execute()
        if operation == "create_forwarding":
            return forwarding.create(userId="me", body=body or {}).execute()
        if operation == "get_forwarding":
            return forwarding.get(userId="me", forwardingEmail=item_id).execute()
        forwarding.delete(userId="me", forwardingEmail=item_id).execute()
        return {"success": True, "forwarding_email": item_id}
    if operation in {"list_send_as", "create_send_as", "get_send_as", "update_send_as", "patch_send_as", "delete_send_as", "verify_send_as"}:
        send_as = settings.sendAs()
        if operation == "list_send_as":
            return send_as.list(userId="me").execute()
        if operation == "create_send_as":
            return send_as.create(userId="me", body=body or {}).execute()
        if operation == "get_send_as":
            return send_as.get(userId="me", sendAsEmail=item_id).execute()
        if operation in {"update_send_as", "patch_send_as"}:
            method = send_as.update if operation == "update_send_as" else send_as.patch
            return method(userId="me", sendAsEmail=item_id, body=body or {}).execute()
        if operation == "verify_send_as":
            return send_as.verify(userId="me", sendAsEmail=item_id).execute()
        send_as.delete(userId="me", sendAsEmail=item_id).execute()
        return {"success": True, "send_as": item_id}
    if operation in {"list_delegates", "create_delegate", "get_delegate", "delete_delegate"}:
        delegates = settings.delegates()
        if operation == "list_delegates":
            return delegates.list(userId="me").execute()
        if operation == "create_delegate":
            return delegates.create(userId="me", body=body or {}).execute()
        if operation == "get_delegate":
            return delegates.get(userId="me", delegateEmail=item_id).execute()
        delegates.delete(userId="me", delegateEmail=item_id).execute()
        return {"success": True, "delegate_email": item_id}
    setting_methods = {
        "autoForwarding": "AutoForwarding",
        "imap": "Imap",
        "language": "Language",
        "pop": "Pop",
        "vacation": "Vacation",
    }
    if operation in {"get_setting", "update_setting"}:
        suffix = setting_methods.get(setting_type)
        if not suffix:
            raise ValueError("setting_type must be autoForwarding, imap, language, pop, or vacation")
        method = getattr(settings, ("get" if operation == "get_setting" else "update") + suffix)
        params = {"userId": "me"}
        if operation == "update_setting":
            params["body"] = body or {}
        return method(**params).execute()
    if operation in {"list_smime", "insert_smime", "get_smime", "delete_smime", "set_default_smime"}:
        smime = settings.sendAs().smimeInfo()
        params = {"userId": "me", "sendAsEmail": email_address}
        if operation == "list_smime":
            return smime.list(**params).execute()
        if operation == "insert_smime":
            return smime.insert(**params, body=body or {}).execute()
        params["id"] = smime_id
        if operation == "get_smime":
            return smime.get(**params).execute()
        if operation == "delete_smime":
            smime.delete(**params).execute()
            return {"success": True, "smime_id": smime_id}
        return smime.setDefault(**params).execute()
    if operation in {
        "list_cse_identities", "create_cse_identity", "get_cse_identity",
        "patch_cse_identity", "delete_cse_identity",
    }:
        identities = settings.cse().identities()
        if operation == "list_cse_identities":
            return identities.list(userId="me").execute()
        if operation == "create_cse_identity":
            return identities.create(userId="me", body=body or {}).execute()
        params = {"userId": "me", "emailAddress": email_address}
        if operation == "get_cse_identity":
            return identities.get(**params).execute()
        if operation == "patch_cse_identity":
            return identities.patch(**params, body=body or {}).execute()
        identities.delete(**params).execute()
        return {"success": True, "email_address": email_address}
    if operation in {
        "list_cse_keypairs", "create_cse_keypair", "get_cse_keypair",
        "enable_cse_keypair", "disable_cse_keypair", "obliterate_cse_keypair",
    }:
        keypairs = settings.cse().keypairs()
        if operation == "list_cse_keypairs":
            return keypairs.list(userId="me").execute()
        if operation == "create_cse_keypair":
            return keypairs.create(userId="me", body=body or {}).execute()
        params = {"userId": "me", "keyPairId": key_pair_id}
        if operation == "get_cse_keypair":
            return keypairs.get(**params).execute()
        method_name = {
            "enable_cse_keypair": "enable",
            "disable_cse_keypair": "disable",
            "obliterate_cse_keypair": "obliterate",
        }[operation]
        method = getattr(keypairs, method_name)
        return method(**params).execute()
    raise ValueError("Unsupported Gmail settings operation")


def create_read_spreadsheet(
    operation: Literal["create", "get", "get_by_data_filter"],
    spreadsheet_id: str = "",
    title: str = "",
    body: Optional[dict] = None,
    data_filters: Optional[list] = None,
) -> dict:
    """Create a Google spreadsheet or read its metadata; operation is create, get, or get_by_data_filter."""
    spreadsheets = _sheets().spreadsheets()
    if operation == "create":
        request_body = body or {"properties": {"title": title}}
        return spreadsheets.create(body=request_body, fields="spreadsheetId,spreadsheetUrl,properties,sheets").execute()
    if operation == "get":
        return spreadsheets.get(spreadsheetId=spreadsheet_id, includeGridData=False).execute()
    if operation == "get_by_data_filter":
        if not data_filters:
            raise ValueError("data_filters are required for get_by_data_filter")
        return spreadsheets.getByDataFilter(
            spreadsheetId=spreadsheet_id, body={"dataFilters": data_filters}
        ).execute()
    raise ValueError("operation must be create or get")


def read_sheet_values(spreadsheet_id: str, range: str, value_render_option: str = "FORMATTED_VALUE") -> dict:
    """Read values from a Google Sheets A1 range."""
    return _sheets().spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=range, valueRenderOption=value_render_option
    ).execute()


def write_sheet_values(
    spreadsheet_id: str,
    range: str,
    values: list,
    operation: Literal["update", "append"] = "update",
    value_input_option: str = "USER_ENTERED",
) -> dict:
    """Write cell values to a range or append rows; operation is update or append."""
    values_api = _sheets().spreadsheets().values()
    body = {"values": values}
    if operation == "update":
        return values_api.update(
            spreadsheetId=spreadsheet_id, range=range, valueInputOption=value_input_option, body=body
        ).execute()
    if operation == "append":
        return values_api.append(
            spreadsheetId=spreadsheet_id, range=range, valueInputOption=value_input_option, body=body
        ).execute()
    raise ValueError("operation must be update or append")


def clear_sheet_values(
    spreadsheet_id: str,
    range: str = "",
    ranges: Optional[list] = None,
    data_filters: Optional[list] = None,
) -> dict:
    """Clear one A1 range, multiple ranges, or data-filtered ranges without deleting formatting."""
    values = _sheets().spreadsheets().values()
    if data_filters:
        return values.batchClearByDataFilter(
            spreadsheetId=spreadsheet_id, body={"dataFilters": data_filters}
        ).execute()
    if ranges:
        return values.batchClear(spreadsheetId=spreadsheet_id, body={"ranges": ranges}).execute()
    if not range:
        raise ValueError("Provide range, ranges, or data_filters")
    return values.clear(spreadsheetId=spreadsheet_id, range=range, body={}).execute()


def batch_read_sheet_values(
    spreadsheet_id: str,
    ranges: Optional[list] = None,
    value_render_option: str = "FORMATTED_VALUE",
    data_filters: Optional[list] = None,
) -> dict:
    """Read multiple A1 ranges or data-filtered ranges from a Google spreadsheet in one request."""
    values = _sheets().spreadsheets().values()
    if data_filters:
        return values.batchGetByDataFilter(
            spreadsheetId=spreadsheet_id,
            body={"dataFilters": data_filters},
            valueRenderOption=value_render_option,
        ).execute()
    if not ranges:
        raise ValueError("Provide ranges or data_filters")
    return values.batchGet(
        spreadsheetId=spreadsheet_id, ranges=ranges, valueRenderOption=value_render_option
    ).execute()


def batch_update_sheet(
    spreadsheet_id: str,
    body: dict,
    value_input_option: str = "USER_ENTERED",
    operation: Literal["values", "values_by_data_filter", "format"] = "values",
) -> dict:
    """Batch update cell values, data-filtered values, or spreadsheet formatting/properties."""
    spreadsheets = _sheets().spreadsheets()
    if operation == "values":
        return spreadsheets.values().batchUpdate(
            spreadsheetId=spreadsheet_id, body={**body, "valueInputOption": value_input_option}
        ).execute()
    if operation == "values_by_data_filter":
        return spreadsheets.values().batchUpdateByDataFilter(
            spreadsheetId=spreadsheet_id,
            body={**body, "valueInputOption": value_input_option},
        ).execute()
    if operation == "format":
        return spreadsheets.batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()
    raise ValueError("operation must be values, values_by_data_filter, or format")


def manage_sheets_and_metadata(
    spreadsheet_id: str,
    operation: Literal[
        "add_sheet", "delete_sheet", "rename_sheet", "copy_sheet", "get_metadata",
        "search_metadata", "create_metadata", "update_metadata", "delete_metadata",
    ],
    sheet_id: int = 0,
    title: str = "",
    body: Optional[dict] = None,
    metadata_id: int = 0,
) -> dict:
    """Manage spreadsheet tabs and developer metadata; operation selects tab or metadata create/get/search/update/delete."""
    spreadsheets = _sheets().spreadsheets()
    if operation == "add_sheet":
        return spreadsheets.batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
        ).execute()
    if operation in {"delete_sheet", "rename_sheet"}:
        request = (
            {"deleteSheet": {"sheetId": sheet_id}}
            if operation == "delete_sheet"
            else {"updateSheetProperties": {"properties": {"sheetId": sheet_id, "title": title}, "fields": "title"}}
        )
        return spreadsheets.batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": [request]}).execute()
    if operation == "copy_sheet":
        return spreadsheets.sheets().copyTo(
            spreadsheetId=spreadsheet_id, sheetId=sheet_id, body=body or {}
        ).execute()
    metadata = spreadsheets.developerMetadata()
    if operation == "get_metadata":
        return metadata.get(spreadsheetId=spreadsheet_id, metadataId=metadata_id).execute()
    if operation == "search_metadata":
        return metadata.search(
            spreadsheetId=spreadsheet_id, body=body or {}
        ).execute()
    metadata_requests = {
        "create_metadata": "createDeveloperMetadata",
        "update_metadata": "updateDeveloperMetadata",
        "delete_metadata": "deleteDeveloperMetadata",
    }
    request_name = metadata_requests.get(operation)
    if request_name:
        return spreadsheets.batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{request_name: body or {}}]},
        ).execute()
    raise ValueError("Unsupported sheet/metadata operation")


def create_tasklist(title: str) -> dict:
    """Create a Google Tasks task list with the requested title."""
    return _tasks().tasklists().insert(body={"title": title}).execute()


def manage_tasklists(
    operation: Literal["list", "get", "update", "delete"],
    tasklist_id: str = "",
    title: str = "",
    page_token: str = "",
    confirm_delete: bool = False,
) -> dict:
    """List, read, rename, or delete a task list; delete requires confirm_delete=true because its tasks are also removed."""
    tasklists = _tasks().tasklists()
    if operation == "list":
        params = {"maxResults": 100}
        if page_token:
            params["pageToken"] = page_token
        return tasklists.list(**params).execute()
    if operation == "get":
        return tasklists.get(tasklist=tasklist_id).execute()
    if operation == "update":
        return tasklists.patch(tasklist=tasklist_id, body={"title": title}).execute()
    if operation == "delete":
        if not confirm_delete:
            raise ValueError("Set confirm_delete=true to delete the task list and all its tasks")
        tasklists.delete(tasklist=tasklist_id).execute()
        return {"success": True, "tasklist_id": tasklist_id}
    raise ValueError("operation must be list, get, update, or delete")


def add_task(
    tasklist_id: str,
    title: str,
    notes: str = "",
    due: str = "",
    parent_task_id: str = "",
    previous_task_id: str = "",
) -> dict:
    """Add a task to a Google Tasks list, optionally with notes, due date, and parent/order placement."""
    body = {"title": title}
    if notes:
        body["notes"] = notes
    if due:
        body["due"] = due
    params = {"tasklist": tasklist_id, "body": body}
    if parent_task_id:
        params["parent"] = parent_task_id
    if previous_task_id:
        params["previous"] = previous_task_id
    return _tasks().tasks().insert(**params).execute()


def list_tasks(
    tasklist_id: str,
    show_completed: bool = True,
    show_hidden: bool = False,
    page_token: str = "",
) -> dict:
    """List tasks in a Google Tasks list, including optional completed/hidden tasks and pagination."""
    params = {"tasklist": tasklist_id, "showCompleted": show_completed, "showHidden": show_hidden, "maxResults": 100}
    if page_token:
        params["pageToken"] = page_token
    return _tasks().tasks().list(**params).execute()


def update_complete_task(
    tasklist_id: str,
    task_id: str,
    operation: Literal["complete", "reopen", "update"] = "complete",
    title: str = "",
    notes: str = "",
    due: str = "",
) -> dict:
    """Complete, reopen, or update a Google Tasks task; operation is complete, reopen, or update."""
    if operation not in {"complete", "reopen", "update"}:
        raise ValueError("operation must be complete, reopen, or update")
    body = {}
    if operation == "complete":
        body["status"] = "completed"
    elif operation == "reopen":
        body["status"] = "needsAction"
    if title:
        body["title"] = title
    if notes:
        body["notes"] = notes
    if due:
        body["due"] = due
    return _tasks().tasks().patch(tasklist=tasklist_id, task=task_id, body=body).execute()


def delete_task(tasklist_id: str, task_id: str, confirm_delete: bool = False) -> dict:
    """Permanently delete a Google Tasks task; requires confirm_delete=true."""
    if not confirm_delete:
        raise ValueError("Set confirm_delete=true to permanently delete this task")
    _tasks().tasks().delete(tasklist=tasklist_id, task=task_id).execute()
    return {"success": True, "task_id": task_id}
