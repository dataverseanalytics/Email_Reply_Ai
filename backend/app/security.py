import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
from cryptography.fernet import Fernet
from fastapi import Cookie, Depends, HTTPException

from .db import get_db

SESSION_COOKIE = "session"
SESSION_DAYS = 7
_KEY_FILE = Path(__file__).resolve().parent.parent / "data" / "secret.key"


def _load_fernet() -> Fernet:
    """Key for encrypting stored mailbox passwords. APP_SECRET_KEY wins; else a local key file."""
    key = os.getenv("APP_SECRET_KEY")
    if not key:
        _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not _KEY_FILE.exists():
            _KEY_FILE.write_bytes(Fernet.generate_key())
        key = _KEY_FILE.read_bytes().decode()
    return Fernet(key)


_fernet = _load_fernet()


def encrypt(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _fernet.decrypt(value.encode()).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_session(conn, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires.isoformat()),
    )
    return token


def current_user(session: str | None = Cookie(default=None), conn=Depends(get_db)):
    if not session:
        raise HTTPException(401, "Not logged in")
    row = conn.execute(
        "SELECT u.*, s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
        (session,),
    ).fetchone()
    if not row or datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
        raise HTTPException(401, "Session expired")
    return row
