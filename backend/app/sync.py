"""Fetching new mail, drafting replies, and the background auto-sync scheduler."""
import json
import logging
import re
import threading
from datetime import datetime, timezone

from . import ai, mail_client
from .db import connect
from .security import decrypt

log = logging.getLogger("replydesk.sync")

AUTOMATED_SENDER = re.compile(r"no-?reply|do-?not-?reply|mailer-daemon|notifications?@", re.I)
SCHEDULER_TICK_SECONDS = 30

# One lock per user so a manual check and an automatic one never fetch the same mailbox at once.
_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()
_stop = threading.Event()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def user_lock(user_id: int) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(user_id, threading.Lock())


def load_account(conn, user_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM mail_accounts WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return None
    acc = dict(row)
    acc["password"] = decrypt(acc.pop("password_enc"))
    return acc


class NoMailAccount(Exception):
    pass


def sync_account(user_id: int) -> dict:
    """Fetch new mail for one user and store it. Caller must hold user_lock(user_id).

    Returns {"fetched": n, "to_draft": [email ids]}. Raises NoMailAccount, or the mail
    server's error (which is also recorded on the account as last_sync_error).
    """
    conn = connect()
    try:
        acc = load_account(conn, user_id)
        if not acc:
            raise NoMailAccount()
        known = {r["imap_uid"] for r in conn.execute(
            "SELECT imap_uid FROM emails WHERE user_id = ?", (user_id,))}
        try:
            fetched = mail_client.fetch_recent(acc, known)
        except Exception as e:
            # Recording the attempt time also makes the scheduler wait a full interval before retrying.
            conn.execute("UPDATE mail_accounts SET last_synced_at = ?, last_sync_error = ? WHERE user_id = ?",
                         (now(), str(e), user_id))
            conn.commit()
            raise

        to_draft = []
        for m in fetched:
            own = m["from_address"].lower() == acc["from_address"].lower()
            automated = bool(AUTOMATED_SENDER.search(m["from_address"]))
            auto = acc["auto_draft"] and not own and not automated
            cur = conn.execute(
                """INSERT OR IGNORE INTO emails (user_id, imap_uid, message_id, references_hdr, from_name,
                       from_address, subject, received_at, body, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, m["imap_uid"], m["message_id"], m["references_hdr"], m["from_name"],
                 m["from_address"], m["subject"], m["received_at"], m["body"],
                 "drafting" if auto else ("ignored" if own or automated else "new")),
            )
            if auto and cur.rowcount:
                to_draft.append(cur.lastrowid)
        conn.execute("UPDATE mail_accounts SET last_synced_at = ?, last_sync_error = '' WHERE user_id = ?",
                     (now(), user_id))
        conn.commit()
        return {"fetched": len(fetched), "to_draft": to_draft}
    finally:
        conn.close()


def run_draft(user_id: int, email_id: int, instruction: str = "", revise: bool = False) -> None:
    """Generate a draft and store it. Uses its own connection so it can run in the background."""
    conn = connect()
    try:
        user = dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
        email = dict(conn.execute("SELECT * FROM emails WHERE id = ? AND user_id = ?",
                                  (email_id, user_id)).fetchone())
        knowledge = [dict(r) for r in conn.execute(
            "SELECT question, answer FROM knowledge WHERE user_id = ? ORDER BY id", (user_id,))]
        try:
            result = ai.draft_reply(user, knowledge, email, instruction,
                                    previous_draft=email["draft_body"] if revise else "")
            conn.execute(
                """UPDATE emails SET status = 'drafted', draft_body = ?, draft_note = ?, draft_prompt = ?,
                       suggested_prompts = ?, draft_error = '', drafted_at = ? WHERE id = ?""",
                (result["reply"], result["note"], instruction, json.dumps(result["suggested_prompts"]),
                 now(), email_id),
            )
        except ai.DraftError as e:
            conn.execute(
                "UPDATE emails SET status = CASE WHEN draft_body = '' THEN 'new' ELSE 'drafted' END, "
                "draft_error = ? WHERE id = ?", (str(e), email_id))
        conn.commit()
    finally:
        conn.close()


def run_drafts(user_id: int, email_ids: list[int]) -> None:
    for eid in email_ids:
        try:
            run_draft(user_id, eid)
        except Exception:
            log.exception("Drafting email %s failed", eid)


# ---------- Scheduler ----------

def _resume_interrupted_drafts() -> None:
    """Emails left in 'drafting' by a server restart get drafted again."""
    conn = connect()
    try:
        rows = conn.execute("SELECT id, user_id FROM emails WHERE status = 'drafting' ORDER BY id").fetchall()
    finally:
        conn.close()
    for r in rows:
        run_drafts(r["user_id"], [r["id"]])


def _due_accounts() -> list[int]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT user_id, sync_interval, last_synced_at FROM mail_accounts WHERE sync_interval > 0").fetchall()
    finally:
        conn.close()
    t = datetime.now(timezone.utc)
    return [r["user_id"] for r in rows
            if not r["last_synced_at"]
            or (t - datetime.fromisoformat(r["last_synced_at"])).total_seconds() >= r["sync_interval"] * 60]


def run_due_syncs() -> None:
    for user_id in _due_accounts():
        if _stop.is_set():
            return
        lock = user_lock(user_id)
        if not lock.acquire(blocking=False):
            continue  # a manual check is already running for this user
        try:
            result = sync_account(user_id)
        except Exception as e:
            log.warning("Auto-sync failed for user %s: %s", user_id, e)
            continue
        finally:
            lock.release()
        if result["fetched"]:
            log.info("Auto-sync user %s: %s new, drafting %s", user_id, result["fetched"], len(result["to_draft"]))
        run_drafts(user_id, result["to_draft"])


def _scheduler_loop() -> None:
    _resume_interrupted_drafts()
    while not _stop.is_set():
        try:
            run_due_syncs()
        except Exception:
            log.exception("Auto-sync tick failed")
        _stop.wait(SCHEDULER_TICK_SECONDS)


def start_scheduler() -> None:
    _stop.clear()
    threading.Thread(target=_scheduler_loop, name="auto-sync", daemon=True).start()


def stop_scheduler() -> None:
    _stop.set()
