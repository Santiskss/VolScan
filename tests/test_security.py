import json

import pytest

from volscan import security as sec


def test_users_roles_and_password_hashing(tmp_path):
    f = tmp_path / "users.json"
    sec.add_user("ana", "tecnico", "contraseña-larga", f)
    assert "contraseña" not in f.read_text()
    assert sec.check_password("ana", "contraseña-larga", f) == dict(name="ana", role="tecnico")
    assert sec.check_password("ana", "otra-cosa-larga", f) is None
    assert sec.check_password("nadie", "contraseña-larga", f) is None
    with pytest.raises(ValueError):
        sec.add_user("x", "jefe", "contraseña-larga", f)
    with pytest.raises(ValueError):
        sec.add_user("x", "lector", "corta", f)
    assert sec.role_at_least("admin", "tecnico") and not sec.role_at_least("lector", "tecnico")


def test_audit_chain_detects_tampering(tmp_path):
    f = tmp_path / "audit.jsonl"
    for k in range(5):
        sec.audit(dict(user="ana", path=f"/api/x/{k}", status=200), f)
    assert sec.verify_audit(f) == dict(ok=True, lines=5)
    lines = f.read_text().splitlines()
    rec = json.loads(lines[2]); rec["user"] = "otro"
    lines[2] = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
    f.write_text("\n".join(lines) + "\n")
    v = sec.verify_audit(f)
    assert not v["ok"] and v["broken_at"] == 4          # the line after the edited one no longer matches
    assert sec.read_audit(2, f)[0]["path"] == "/api/x/4"


def test_api_requires_login_and_role_when_enabled(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from volscan.api import app as A
    monkeypatch.setenv("VOLSCAN_AUTH", "on")
    monkeypatch.setattr(sec, "USERS", tmp_path / "u.json")
    monkeypatch.setattr(sec, "AUDIT", tmp_path / "a.jsonl")
    sec.add_user("lucia", "lector", "una-contraseña-larga", tmp_path / "u.json")
    c = TestClient(A.app)
    assert c.get("/api/canarias/zones").status_code == 401
    assert c.get("/api/auth/config").json()["enabled"] is True
    assert c.post("/api/login", json=dict(name="lucia", password="mal-mal-mal-mal")).status_code == 401
    tok = c.post("/api/login", json=dict(name="lucia", password="una-contraseña-larga")).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert c.get("/api/reports/months", headers=h).status_code == 200
    assert c.post("/api/canarias/refresh", headers=h).status_code == 403      # lector can't refresh
    assert c.get("/api/audit", headers=h).status_code == 403
    log = [json.loads(x) for x in (tmp_path / "a.jsonl").read_text().splitlines()]
    login_entries = [e for e in log if e["path"] == "/api/login"]
    assert len(login_entries) == 2 and all(e.get("event") in ("login_failed", "login_ok") for e in login_entries)
    assert any(e["status"] == 403 for e in log)
    sec.audit(dict(user="lucia", path="/api/long", query="q=" + "x" * 6000, status=200), tmp_path / "a.jsonl")
    sec.audit(dict(user="lucia", path="/api/after_long", query="", status=200), tmp_path / "a.jsonl")
    assert sec.verify_audit(tmp_path / "a.jsonl")["ok"]
