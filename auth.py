"""Admin sign-in: one account, signed session cookie, simple brute-force throttle.

Credentials come from environment variables or a local admin.env file (not committed):
    QL_ADMIN_USER=...
    QL_ADMIN_PASS=...
"""
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

from fastapi import HTTPException, Request


def _load_env_file(path: Path) -> dict:
    if not path.exists():
        return {}
    pairs = (line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if "=" in line and not line.lstrip().startswith("#"))
    return {k.strip(): v.strip() for k, v in pairs}


_file = _load_env_file(Path(__file__).parent / "admin.env")
ADMIN_USER = os.environ.get("QL_ADMIN_USER") or _file.get("QL_ADMIN_USER", "")
ADMIN_PASS = os.environ.get("QL_ADMIN_PASS") or _file.get("QL_ADMIN_PASS", "")
if not (ADMIN_USER and ADMIN_PASS):
    print("  ! Admin sign-in is disabled: copy admin.env.example to admin.env and set a username and password.")
COOKIE = "ql_admin"
SESSION_SECONDS = 12 * 3600
_SECRET = secrets.token_bytes(32)
_fails: dict[str, list[float]] = {}


def _sign(msg: str) -> str:
    return hmac.new(_SECRET, msg.encode(), hashlib.sha256).hexdigest()


def make_token() -> str:
    exp = str(int(time.time()) + SESSION_SECONDS)
    return f"{exp}.{_sign(exp)}"


def valid_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    exp, sig = token.split(".", 1)
    return hmac.compare_digest(sig, _sign(exp)) and exp.isdigit() and int(exp) > time.time()


def check_login(ip: str, username: str, password: str) -> bool:
    if not (ADMIN_USER and ADMIN_PASS):
        raise HTTPException(503, "Admin sign-in is not configured on this server")
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < 300]
    if len(recent) >= 5:
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
    ok = hmac.compare_digest(username.encode(), ADMIN_USER.encode()) & hmac.compare_digest(password.encode(), ADMIN_PASS.encode())
    if not ok:
        recent.append(now)
    _fails[ip] = recent if not ok else []
    return ok


def require_admin(request: Request):
    if not valid_token(request.cookies.get(COOKIE)):
        raise HTTPException(401, "Admin sign-in required")
