import datetime as dt
import os
import time

import pytest

from volscan import catalog_store as store
from volscan.sources import emsc_fdsn, ign_catalog as ign

EMSC = """#EventID|Time|Latitude|Longitude|Depth/km|Author|Catalog|Contributor|ContributorID|MagType|Magnitude|MagAuthor|EventLocationName
20261025_0000165|2026-10-25T11:19:32.79Z|27.8078|-16.1823|0.0|IGN|EMSC-RTS|IGN|2080383|ml|1.9|IGN|CANARY ISLANDS, SPAIN REGION
bad|line
"""


def test_emsc_parse_marks_source():
    ev = emsc_fdsn.parse_text(EMSC)
    assert len(ev) == 1 and ev[0].evid == "emsc:20261025_0000165" and ev[0].mag == 1.9
    assert ev[0].time_utc.tzinfo is not None and "EMSC" in ev[0].location


class FakeResp:
    def __init__(self, text):
        self.text, self.status_code = text, 200

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, text):
        self.t = text

    def post(self, *a, **k):
        return FakeResp(self.t)


def test_ign_format_change_is_detected_not_read_as_empty():
    d = dt.date(2026, 10, 1)
    with pytest.raises(ign.IgnFormatChanged):
        ign.fetch_range(d, d, session=FakeSession("<html><div>nuevo portal</div></html>"))
    assert ign.fetch_range(d, d, session=FakeSession("<p>No se han encontrado registros, según…</p>")) == []
    with pytest.raises(ign.IgnFormatChanged):
        ign.fetch_range(d, d, session=FakeSession("<p>12 terremotos.</p><div>tabla nueva</div>"))


def test_backup_fills_only_after_last_ign_event_and_health_says_so(tmp_path, monkeypatch):
    t0 = dt.datetime(2026, 10, 20, tzinfo=dt.timezone.utc)
    mk = lambda i, t: ign.IgnEvent(i, t, 28.0, -16.5, 10.0, 1.5, "mbLg", "", "X")
    ign.write_csv([mk("a", t0), mk("b", t0 + dt.timedelta(hours=5))], tmp_path / "ign" / "ign_2026_10.csv")
    ign.write_csv([mk("emsc:old", t0 + dt.timedelta(hours=1)), mk("emsc:new", t0 + dt.timedelta(hours=9))], tmp_path / "b.csv")
    monkeypatch.setattr(store, "STORE", tmp_path / "ign")
    monkeypatch.setattr(store, "BACKUP", tmp_path / "b.csv")
    monkeypatch.setitem(store._state, "refresh_error", "ConnectionError: down")
    ev = store.load_events(force=True)
    assert [e.evid for e in ev] == ["a", "b", "emsc:new"]
    h = store.health(now=(t0 + dt.timedelta(hours=10)).timestamp())
    assert h["level"] == "sin conexión con el IGN" and not h["ok"] and h["backup_events"] == 1
    monkeypatch.setitem(store._state, "refresh_error", None)
    old = time.time() - 10 * 3600
    os.utime(tmp_path / "ign" / "ign_2026_10.csv", (old, old))
    assert store.health()["level"] == "retrasado"
    store._state["events"] = None
