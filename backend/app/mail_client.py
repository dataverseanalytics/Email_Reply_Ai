"""IMAP fetching and SMTP sending.

Note: incoming mail is read over IMAP; SMTP is only used to send replies.
"""
import imaplib
import re
import smtplib
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr, parsedate_to_datetime
from html import unescape

MAX_BODY_CHARS = 20000


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", html)
    text = unescape(re.sub(r"<[^>]+>", "", html))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _extract_body(msg) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    content = part.get_content()
    if part.get_content_type() == "text/html":
        content = _html_to_text(content)
    return content.strip()[:MAX_BODY_CHARS]


def _imap(account: dict) -> imaplib.IMAP4:
    if account["imap_port"] == 143:
        conn = imaplib.IMAP4(account["imap_host"], 143, timeout=30)
        conn.starttls()
    else:
        conn = imaplib.IMAP4_SSL(account["imap_host"], account["imap_port"], timeout=30)
    conn.login(account["username"], account["password"])
    return conn


def test_connection(account: dict) -> None:
    """Raises on failure."""
    conn = _imap(account)
    conn.logout()
    with _smtp(account) as smtp:
        smtp.noop()


def fetch_recent(account: dict, known_uids: set[str]) -> list[dict]:
    """Return the newest `fetch_limit` INBOX messages that aren't already stored. Does not mark them read."""
    conn = _imap(account)
    try:
        conn.select("INBOX", readonly=True)
        _, data = conn.uid("search", None, "ALL")
        uids = [u.decode() for u in data[0].split()][-account["fetch_limit"]:]
        results = []
        for uid in uids:
            if uid in known_uids:
                continue
            _, msg_data = conn.uid("fetch", uid, "(BODY.PEEK[])")
            raw = next((p[1] for p in msg_data if isinstance(p, tuple)), None)
            if not raw:
                continue
            msg = message_from_bytes(raw, policy=policy.default)
            name, addr = parseaddr(str(msg.get("From", "")))
            try:
                received = parsedate_to_datetime(str(msg.get("Date"))).isoformat()
            except (TypeError, ValueError):
                received = ""
            results.append({
                "imap_uid": uid,
                "message_id": str(msg.get("Message-ID", "")).strip(),
                "references_hdr": str(msg.get("References", "")).strip(),
                "from_name": name,
                "from_address": addr,
                "subject": str(msg.get("Subject", "")),
                "received_at": received,
                "body": _extract_body(msg),
            })
        return results
    finally:
        conn.logout()


def _smtp(account: dict) -> smtplib.SMTP:
    if account["smtp_port"] == 465:
        smtp = smtplib.SMTP_SSL(account["smtp_host"], 465, timeout=30)
    else:
        smtp = smtplib.SMTP(account["smtp_host"], account["smtp_port"], timeout=30)
        smtp.starttls()
    smtp.login(account["username"], account["password"])
    return smtp


def send_reply(account: dict, sender_name: str, original: dict, body: str) -> None:
    subject = original["subject"] or ""
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    msg = EmailMessage()
    msg["From"] = f"{sender_name} <{account['from_address']}>"
    msg["To"] = original["from_address"]
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    if original["message_id"]:
        msg["In-Reply-To"] = original["message_id"]
        msg["References"] = f"{original['references_hdr']} {original['message_id']}".strip()
    msg.set_content(body)
    with _smtp(account) as smtp:
        smtp.send_message(msg)
