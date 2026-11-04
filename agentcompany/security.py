"""Password hashing and session tokens. Session cookie is opaque, random, and HttpOnly."""
import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from .db import now, new_id, transaction, row

SESSION_DAYS = 7

def password_hash(password: str) -> str:
    if not (12 <= len(password) <= 256):
        raise ValueError("Password must have 12 to 256 characters")
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, digest = stored.split("$")
        if kind != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(actual, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def new_session(con, user_id: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(36)
    csrf = secrets.token_urlsafe(28)
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
    con.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)", (
        hashlib.sha256(token.encode()).hexdigest(), user_id, csrf, expires,
    ))
    return token, csrf


def session_user(con, token: str) -> dict | None:
    if not token or len(token) > 200:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    return row(con, """SELECT users.id,users.email,sessions.csrf,sessions.expires_at
      FROM sessions JOIN users ON sessions.user_id=users.id WHERE sessions.token_hash=?
      AND sessions.expires_at>?""", (digest, now()))


def revoke_session(con, token: str):
    con.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
