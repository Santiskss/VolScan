"""Users, roles and an audit trail: what a public administration needs before VolScan touches its systems.

ROLES
-----
- lector:  sees everything.
- tecnico: also refreshes data, asks the AI to draft reports, and exports (PDF, CAP, OGC/GeoJSON).
- admin:   also reads the audit trail.

Authentication is OFF by default, so the local demo opens straight away. In
that mode every request acts as the user "local" (role admin), and is STILL
written to the audit trail. Turn it on with VOLSCAN_AUTH=on in .env and create
users from the command line:

    python -m volscan.security add-user ana tecnico      # asks for the password
    python -m volscan.security verify-audit

Passwords are stored as PBKDF2-SHA256 (310,000 iterations, per-user salt) in
config/users.json, which is not in git. Sessions are random tokens held in
memory for 12 hours.

AUDIT TRAIL
-----------
One JSON line per API call (except the status poll and static files), in
out/audit/audit.jsonl: time, user, role, method, path, query, status code,
client address. Each line carries the SHA-256 of the previous line, so
deleting or editing a line breaks the chain, and `verify-audit` says where.
That is the traceability the ENS (Esquema Nacional de Seguridad) asks for. It
does not replace an ENS certification, which covers much more (hosting,
backups, incident handling).
"""
from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USERS = Path(os.environ.get("VOLSCAN_USERS", ROOT / "config" / "users.json"))
AUDIT = Path(os.environ.get("VOLSCAN_AUDIT", ROOT / "out" / "audit" / "audit.jsonl"))
ROLES = ("lector", "tecnico", "admin")
SESSION_S = 12 * 3600
ITER = 310_000
_lock = threading.Lock()
_sessions: dict[str, dict] = {}


def auth_enabled() -> bool:
    from .ai.llm import _load_dotenv
    _load_dotenv()
    return os.environ.get("VOLSCAN_AUTH", "off").strip().lower() in ("on", "1", "true", "yes")


def role_at_least(role: str, needed: str) -> bool:
    return ROLES.index(role) >= ROLES.index(needed)


# ---------------------------------------------------------------- users
def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITER).hex()


def load_users(path: Path | None = None) -> dict:
    path = path or USERS
    if not path.exists():
        return {}
    return {u["name"]: u for u in json.loads(path.read_text())["users"]}


def add_user(name: str, role: str, password: str, path: Path | None = None):
    path = path or USERS
    if role not in ROLES:
        raise ValueError(f"rol desconocido: {role} (use {', '.join(ROLES)})")
    if len(password) < 10:
        raise ValueError("la contraseña debe tener al menos 10 caracteres")
    users = load_users(path)
    salt = secrets.token_bytes(16)
    users[name] = dict(name=name, role=role, salt=salt.hex(), hash=_hash(password, salt), iter=ITER)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(users=list(users.values())), indent=1))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def check_password(name: str, password: str, path: Path | None = None) -> dict | None:
    path = path or USERS
    u = load_users(path).get(name)
    if not u:
        _hash(password, b"\0" * 16)          # same cost whether or not the user exists
        return None
    ok = hmac.compare_digest(_hash(password, bytes.fromhex(u["salt"])), u["hash"])
    return dict(name=u["name"], role=u["role"]) if ok else None


# ---------------------------------------------------------------- sessions
def login(name: str, password: str) -> str | None:
    u = check_password(name, password)
    if not u:
        return None
    token = secrets.token_urlsafe(32)
    with _lock:
        _sessions[token] = dict(**u, expires=time.time() + SESSION_S)
    return token


def logout(token: str):
    with _lock:
        _sessions.pop(token, None)


def public_demo() -> bool:
    """Public web deployment without accounts: visitors can use everything a technician can,
    but cannot administer users or repoint the AI to another server."""
    from .ai.llm import _load_dotenv
    _load_dotenv()
    return os.environ.get("VOLSCAN_PUBLIC_DEMO", "off").strip().lower() in ("on", "1", "true", "yes")


def user_for(token: str | None) -> dict | None:
    if not auth_enabled():
        return dict(name="visitante" if public_demo() else "local", role="tecnico" if public_demo() else "admin")
    if not token:
        return None
    with _lock:
        s = _sessions.get(token)
        if not s or s["expires"] < time.time():
            _sessions.pop(token, None)
            return None
        return dict(name=s["name"], role=s["role"])


# ---------------------------------------------------------------- audit trail
def _last_hash(path: Path) -> str:
    if not path.exists() or path.stat().st_size == 0:
        return "0" * 64
    with open(path, "rb") as fh:
        size = path.stat().st_size
        fh.seek(max(0, size - 65536))
        last = fh.read().splitlines()[-1]
    return hashlib.sha256(last).hexdigest()


def audit(entry: dict, path: Path | None = None):
    path = path or AUDIT
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = dict(t=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **entry, prev=_last_hash(path))
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_audit(limit: int = 200, path: Path | None = None) -> list[dict]:
    path = path or AUDIT
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(x) for x in lines][::-1]


def verify_audit(path: Path | None = None) -> dict:
    """Walk the chain: each line must carry the hash of the line before it."""
    path = path or AUDIT
    if not path.exists():
        return dict(ok=True, lines=0)
    prev, n = "0" * 64, 0
    with open(path, "rb") as fh:
        for n, line in enumerate(fh, start=1):
            line = line.rstrip(b"\n")
            try:
                rec = json.loads(line)
            except ValueError:
                return dict(ok=False, lines=n, broken_at=n)
            if rec.get("prev") != prev:
                return dict(ok=False, lines=n, broken_at=n)
            prev = hashlib.sha256(line).hexdigest()
    return dict(ok=True, lines=n)


def _main(argv):
    if len(argv) >= 3 and argv[0] == "add-user":
        pw = getpass.getpass(f"Contraseña para {argv[1]}: ")
        if pw != getpass.getpass("Repítela: "):
            sys.exit("no coinciden")
        add_user(argv[1], argv[2], pw)
        print(f"usuario {argv[1]} ({argv[2]}) guardado en {USERS}")
    elif argv[:1] == ["verify-audit"]:
        print(json.dumps(verify_audit()))
    else:
        print(__doc__)


if __name__ == "__main__":
    _main(sys.argv[1:])
