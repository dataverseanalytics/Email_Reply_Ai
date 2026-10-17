import json
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import BackgroundTasks, Cookie, Depends, FastAPI, HTTPException, Response  # noqa: E402
from pydantic import BaseModel, EmailStr, Field  # noqa: E402

from . import ai, mail_client  # noqa: E402
from .db import connect, get_db, init_db  # noqa: E402
from .security import (  # noqa: E402
    SESSION_COOKIE, SESSION_DAYS, create_session, current_user, decrypt, encrypt,
    hash_password, verify_password,
)

app = FastAPI(title="AI Email Reply")
init_db()

DEFAULT_PRESETS = [
    ("More formal", "Make the tone more formal and polished."),
    ("Shorter", "Make it shorter, three or four sentences at most."),
    ("Decline politely", "Politely decline the request while keeping the relationship warm."),
    ("Ask for a call", "Suggest a short call to discuss and ask for their availability."),
]
AUTOMATED_SENDER = re.compile(r"no-?reply|do-?not-?reply|mailer-daemon|notifications?@", re.I)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- Auth ----------

class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def public_user(u) -> dict:
    return {k: u[k] for k in ("id", "email", "name", "signature", "tone", "about")}


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax",
                        max_age=SESSION_DAYS * 86400)


@app.post("/api/auth/register")
def register(body: RegisterIn, response: Response, conn=Depends(get_db)):
    email = body.email.lower()
    if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        raise HTTPException(409, "An account with this email already exists")
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, name, signature) VALUES (?, ?, ?, ?)",
        (email, hash_password(body.password), body.name.strip(), f"Best regards,\n{body.name.strip()}"),
    )
    user_id = cur.lastrowid
    conn.executemany("INSERT INTO prompt_presets (user_id, label, text) VALUES (?, ?, ?)",
                     [(user_id, label, text) for label, text in DEFAULT_PRESETS])
    _set_cookie(response, create_session(conn, user_id))
    return public_user(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


@app.post("/api/auth/login")
def login(body: LoginIn, response: Response, conn=Depends(get_db)):
    user = conn.execute("SELECT * FROM users WHERE email = ?", (body.email.lower(),)).fetchone()
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    _set_cookie(response, create_session(conn, user["id"]))
    return public_user(user)


@app.post("/api/auth/logout")
def logout(response: Response, session: str | None = Cookie(default=None), conn=Depends(get_db)):
    if session:
        conn.execute("DELETE FROM sessions WHERE token = ?", (session,))
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return public_user(user)


# ---------- Profile ----------

class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    signature: str = Field(default="", max_length=1000)
    tone: str = Field(default="friendly and professional", max_length=200)
    about: str = Field(default="", max_length=4000)


@app.put("/api/profile")
def update_profile(body: ProfileIn, user=Depends(current_user), conn=Depends(get_db)):
    conn.execute("UPDATE users SET name = ?, signature = ?, tone = ?, about = ? WHERE id = ?",
                 (body.name, body.signature, body.tone, body.about, user["id"]))
    return public_user(conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone())


# ---------- Mail account ----------

class MailAccountIn(BaseModel):
    imap_host: str
    imap_port: int = 993
    smtp_host: str
    smtp_port: int = 465
    username: str
    password: str | None = None  # omitted on update = keep existing
    from_address: EmailStr
    auto_draft: bool = True
    fetch_limit: int = Field(default=25, ge=1, le=200)


def load_account(conn, user_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM mail_accounts WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return None
    acc = dict(row)
    acc["password"] = decrypt(acc.pop("password_enc"))
    return acc


@app.get("/api/mail-account")
def get_mail_account(user=Depends(current_user), conn=Depends(get_db)):
    acc = load_account(conn, user["id"])
    if not acc:
        return None
    acc.pop("password")
    acc["auto_draft"] = bool(acc["auto_draft"])
    return acc


@app.put("/api/mail-account")
def save_mail_account(body: MailAccountIn, user=Depends(current_user), conn=Depends(get_db)):
    existing = load_account(conn, user["id"])
    password = body.password or (existing and existing["password"])
    if not password:
        raise HTTPException(400, "Password is required")
    acc = body.model_dump() | {"password": password}
    try:
        mail_client.test_connection(acc)
    except Exception as e:
        raise HTTPException(400, f"Could not connect: {e}")
    conn.execute(
        """INSERT INTO mail_accounts (user_id, imap_host, imap_port, smtp_host, smtp_port, username,
               password_enc, from_address, auto_draft, fetch_limit)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET imap_host=excluded.imap_host, imap_port=excluded.imap_port,
               smtp_host=excluded.smtp_host, smtp_port=excluded.smtp_port, username=excluded.username,
               password_enc=excluded.password_enc, from_address=excluded.from_address,
               auto_draft=excluded.auto_draft, fetch_limit=excluded.fetch_limit""",
        (user["id"], body.imap_host, body.imap_port, body.smtp_host, body.smtp_port, body.username,
         encrypt(password), body.from_address, int(body.auto_draft), body.fetch_limit),
    )
    return {"ok": True}


# ---------- Knowledge base (predefined Q&A) ----------

class KnowledgeIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=5000)


@app.get("/api/knowledge")
def list_knowledge(user=Depends(current_user), conn=Depends(get_db)):
    rows = conn.execute("SELECT id, question, answer FROM knowledge WHERE user_id = ? ORDER BY id DESC",
                        (user["id"],)).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/knowledge")
def add_knowledge(body: KnowledgeIn, user=Depends(current_user), conn=Depends(get_db)):
    cur = conn.execute("INSERT INTO knowledge (user_id, question, answer) VALUES (?, ?, ?)",
                       (user["id"], body.question, body.answer))
    return {"id": cur.lastrowid, **body.model_dump()}


@app.put("/api/knowledge/{kid}")
def update_knowledge(kid: int, body: KnowledgeIn, user=Depends(current_user), conn=Depends(get_db)):
    cur = conn.execute("UPDATE knowledge SET question = ?, answer = ? WHERE id = ? AND user_id = ?",
                       (body.question, body.answer, kid, user["id"]))
    if not cur.rowcount:
        raise HTTPException(404, "Not found")
    return {"id": kid, **body.model_dump()}


@app.delete("/api/knowledge/{kid}")
def delete_knowledge(kid: int, user=Depends(current_user), conn=Depends(get_db)):
    conn.execute("DELETE FROM knowledge WHERE id = ? AND user_id = ?", (kid, user["id"]))
    return {"ok": True}


# ---------- Prompt presets ----------

class PresetIn(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=500)


@app.get("/api/presets")
def list_presets(user=Depends(current_user), conn=Depends(get_db)):
    rows = conn.execute("SELECT id, label, text FROM prompt_presets WHERE user_id = ? ORDER BY id",
                        (user["id"],)).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/presets")
def add_preset(body: PresetIn, user=Depends(current_user), conn=Depends(get_db)):
    cur = conn.execute("INSERT INTO prompt_presets (user_id, label, text) VALUES (?, ?, ?)",
                       (user["id"], body.label, body.text))
    return {"id": cur.lastrowid, **body.model_dump()}


@app.delete("/api/presets/{pid}")
def delete_preset(pid: int, user=Depends(current_user), conn=Depends(get_db)):
    conn.execute("DELETE FROM prompt_presets WHERE id = ? AND user_id = ?", (pid, user["id"]))
    return {"ok": True}


# ---------- Emails ----------

def email_out(row, full: bool = False) -> dict:
    d = dict(row)
    d["suggested_prompts"] = json.loads(d["suggested_prompts"] or "[]")
    d.pop("references_hdr", None)
    if not full:
        d["preview"] = d.pop("body")[:160]
        d.pop("draft_body")
    return d


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
        run_draft(user_id, eid)


@app.post("/api/emails/sync")
def sync_emails(background: BackgroundTasks, user=Depends(current_user), conn=Depends(get_db)):
    acc = load_account(conn, user["id"])
    if not acc:
        raise HTTPException(400, "Connect your mailbox in Settings first")
    known = {r["imap_uid"] for r in conn.execute("SELECT imap_uid FROM emails WHERE user_id = ?",
                                                 (user["id"],))}
    try:
        fetched = mail_client.fetch_recent(acc, known)
    except Exception as e:
        raise HTTPException(502, f"Mail server error: {e}")

    to_draft = []
    for m in fetched:
        own = m["from_address"].lower() == acc["from_address"].lower()
        automated = bool(AUTOMATED_SENDER.search(m["from_address"]))
        auto = acc["auto_draft"] and not own and not automated
        cur = conn.execute(
            """INSERT OR IGNORE INTO emails (user_id, imap_uid, message_id, references_hdr, from_name,
                   from_address, subject, received_at, body, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user["id"], m["imap_uid"], m["message_id"], m["references_hdr"], m["from_name"],
             m["from_address"], m["subject"], m["received_at"], m["body"],
             "drafting" if auto else ("ignored" if own or automated else "new")),
        )
        if auto and cur.rowcount:
            to_draft.append(cur.lastrowid)
    conn.commit()
    if to_draft:
        background.add_task(run_drafts, user["id"], to_draft)
    return {"fetched": len(fetched), "drafting": len(to_draft)}


@app.get("/api/emails")
def list_emails(status: str | None = None, user=Depends(current_user), conn=Depends(get_db)):
    sql = "SELECT * FROM emails WHERE user_id = ?"
    args: list = [user["id"]]
    if status:
        sql += " AND status = ?"
        args.append(status)
    rows = conn.execute(sql + " ORDER BY received_at DESC, id DESC", args).fetchall()
    return [email_out(r) for r in rows]


def get_email_row(conn, user_id: int, email_id: int):
    row = conn.execute("SELECT * FROM emails WHERE id = ? AND user_id = ?", (email_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, "Email not found")
    return row


@app.get("/api/emails/{email_id}")
def get_email(email_id: int, user=Depends(current_user), conn=Depends(get_db)):
    return email_out(get_email_row(conn, user["id"], email_id), full=True)


class DraftIn(BaseModel):
    instruction: str = Field(default="", max_length=1000)
    revise: bool = False  # True = refine the current draft instead of starting over


@app.post("/api/emails/{email_id}/draft")
def draft_email(email_id: int, body: DraftIn, user=Depends(current_user), conn=Depends(get_db)):
    get_email_row(conn, user["id"], email_id)
    conn.execute("UPDATE emails SET status = 'drafting' WHERE id = ?", (email_id,))
    conn.commit()
    run_draft(user["id"], email_id, body.instruction.strip(), body.revise)
    return email_out(get_email_row(conn, user["id"], email_id), full=True)


class DraftSaveIn(BaseModel):
    draft_body: str = Field(max_length=20000)


@app.put("/api/emails/{email_id}/draft")
def save_draft(email_id: int, body: DraftSaveIn, user=Depends(current_user), conn=Depends(get_db)):
    get_email_row(conn, user["id"], email_id)
    conn.execute("UPDATE emails SET draft_body = ?, status = CASE WHEN status IN ('new','ignored') "
                 "THEN 'drafted' ELSE status END WHERE id = ?", (body.draft_body, email_id))
    return email_out(get_email_row(conn, user["id"], email_id), full=True)


@app.post("/api/emails/{email_id}/send")
def send_email(email_id: int, body: DraftSaveIn, user=Depends(current_user), conn=Depends(get_db)):
    row = get_email_row(conn, user["id"], email_id)
    if not body.draft_body.strip():
        raise HTTPException(400, "Reply is empty")
    acc = load_account(conn, user["id"])
    if not acc:
        raise HTTPException(400, "Connect your mailbox in Settings first")
    try:
        mail_client.send_reply(acc, user["name"], dict(row), body.draft_body)
    except Exception as e:
        raise HTTPException(502, f"Could not send: {e}")
    conn.execute("UPDATE emails SET draft_body = ?, status = 'sent', sent_at = ? WHERE id = ?",
                 (body.draft_body, now(), email_id))
    return email_out(get_email_row(conn, user["id"], email_id), full=True)


class StatusIn(BaseModel):
    status: str = Field(pattern="^(new|ignored)$")


@app.patch("/api/emails/{email_id}")
def set_status(email_id: int, body: StatusIn, user=Depends(current_user), conn=Depends(get_db)):
    get_email_row(conn, user["id"], email_id)
    # "new" means back in the inbox; keep it in review if a draft already exists.
    conn.execute("UPDATE emails SET status = CASE WHEN ? = 'new' AND draft_body != '' THEN 'drafted' "
                 "ELSE ? END WHERE id = ?", (body.status, body.status, email_id))
    return email_out(get_email_row(conn, user["id"], email_id), full=True)


@app.get("/api/stats")
def stats(user=Depends(current_user), conn=Depends(get_db)):
    rows = conn.execute("SELECT status, COUNT(*) c FROM emails WHERE user_id = ? GROUP BY status",
                        (user["id"],)).fetchall()
    counts = {r["status"]: r["c"] for r in rows}
    kb = conn.execute("SELECT COUNT(*) FROM knowledge WHERE user_id = ?", (user["id"],)).fetchone()[0]
    has_account = bool(conn.execute("SELECT 1 FROM mail_accounts WHERE user_id = ?", (user["id"],)).fetchone())
    return {"counts": counts, "knowledge": kb, "has_account": has_account}
