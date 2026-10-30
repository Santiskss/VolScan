from volscan import pdfexport as X

REP = dict(title="Tenerife · septiembre de 2026", partial=False, generated_at="2026-10-27T10:00:00", zone=dict(key="tenerife", note="", name="Tenerife"),
           month="2026-09", summary="Resumen con ≥ y –.", stats=dict(n=3, max_mag=2.4, n_m3=0, depth_median=10.0, shallow_lt5=1),
           prev=dict(n=5, max_mag=3.0, n_m3=1, depth_median=12.0, shallow_lt5=0), rate_ratio=0.5, unrest_end=dict(index=0.0),
           b=None, daily=[1, 0, 2] + [0] * 27, daily_depth=[10.0, None, 9.0] + [None] * 27, deformation=None, so2=None,
           top_events=[dict(t="2026-09-02T04:37:00+00:00", mag=2.4, mag_type="mbLg", depth=27.0, int_max=None, place="SW EL ROSARIO", id="es1")],
           sources=["IGN"])


def test_report_pdf_and_csv():
    pdf = X.report_pdf(REP)
    assert pdf[:5] == b"%PDF-" and len(pdf) > 2000
    csv = X.report_csv(REP).decode("utf-8-sig")
    assert csv.splitlines()[0] == "zona,mes,dia,terremotos,profundidad_mediana_km" and "SW EL ROSARIO" in csv


def test_impact_pdf_handles_missing_values():
    fac = [dict(kind="Colegio", name="CEIP X", lon=-17.9, lat=28.6, p=0.4, already_lost=False, eta_h=[10.0, 30.0, None])]
    pdf = X.impact_pdf("t", "s", [("Edificios", "10", "5–20")], fac, [], [dict(name="A", p=0.2)], "m", "f")
    assert pdf[:5] == b"%PDF-"
    assert "CEIP X" in X.impact_csv(fac, []).decode("utf-8-sig")


def test_api_export_endpoints_handle_pre_cems_and_invalid_inputs():
    from fastapi.testclient import TestClient
    from volscan.api.app import app

    c = TestClient(app)
    r_pdf = c.get("/api/export/impact/lapalma2021/2021-09-19.pdf")
    assert r_pdf.status_code == 200 and r_pdf.content[:5] == b"%PDF-"
    assert c.get("/api/export/impact/lapalma2021/2021-09-19.xlsx").status_code == 404
    assert c.get("/api/export/impact/lapalma2021/not-a-date.pdf").status_code == 400
    assert c.get("/api/export/report/tenerife/bad-month.pdf").status_code == 400

