from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from volscan.adapters import (
    IgnEmscSeismicAdapter,
    MetaLlamaAdapter,
    MetaMuseSparkAdapter,
    MetaSAM3Adapter,
    NasaOmpsSo2Adapter,
    NglGnssAdapter,
    OasisCap12Adapter,
    OgcGeoJsonAdapter,
    OllamaLocalAdapter,
    ReportLabPdfCsvAdapter,
    Sha256JsonlAuditAdapter,
)
from volscan.ai.agent import VolScanAgent
from volscan.ai.vision_service import sam3_scene_for_date, sam3_validation_benchmark
from volscan. api.app import app
from volscan.application import VolScanContainer
from volscan.domain import AssimParams, Grid, LavaParams, forecast
from volscan.ports import (
    AuditTrailPort,
    EmbeddingPort,
    EmergencyAlertExportPort,
    GeodeticDeformationPort,
    GeospatialFeatureExportPort,
    LanguageModelPort,
    LavaSegmentationPort,
    ModelTurn,
    MultimodalVisionLanguagePort,
    OperationalReportExportPort,
    PromptPoint,
    SegmentationResult,
    SeismicCatalogPort,
    ThermalScene,
    ToolCall,
    VolcanicGasPort,
)


def test_all_hexagonal_ports_and_adapters_conformance():
    """Verify every concrete adapter satisfies its abstract domain Port protocol."""
    assert Grid is not None and LavaParams is not None and AssimParams is not None and callable(forecast)

    muse = MetaMuseSparkAdapter(api_key="test-key")
    llama4 = MetaLlamaAdapter(api_key="test-key")
    ollama = OllamaLocalAdapter()
    sam3 = MetaSAM3Adapter()

    for adapter in (muse, llama4, ollama):
        assert isinstance(adapter, LanguageModelPort)
        assert isinstance(adapter, EmbeddingPort)
        assert isinstance(adapter, MultimodalVisionLanguagePort)

    assert muse.cfg.public()["adapter"] == "MetaMuseSparkAdapter"
    assert llama4.cfg.public()["adapter"] == "MetaLlamaAdapter"
    assert llama4.cfg.model == "Llama-4-Maverick-17B-128E-Instruct"
    assert ollama.cfg.public()["adapter"] == "OllamaLocalAdapter"

    assert isinstance(sam3, LavaSegmentationPort)
    assert isinstance(IgnEmscSeismicAdapter(), SeismicCatalogPort)
    assert isinstance(NglGnssAdapter(), GeodeticDeformationPort)
    assert isinstance(NasaOmpsSo2Adapter(), VolcanicGasPort)
    assert isinstance(OasisCap12Adapter(), EmergencyAlertExportPort)
    assert isinstance(OgcGeoJsonAdapter(), GeospatialFeatureExportPort)
    assert isinstance(ReportLabPdfCsvAdapter(), OperationalReportExportPort)
    assert isinstance(Sha256JsonlAuditAdapter(), AuditTrailPort)


def test_container_hot_swap_between_meta_and_local_adapters():
    container = VolScanContainer()
    st_llama = container.switch_llm_adapter("meta_llama4", api_key="dummy")
    assert st_llama["adapter"] == "MetaLlamaAdapter"
    assert st_llama["model"] == "Llama-4-Maverick-17B-128E-Instruct"

    st_muse = container.switch_llm_adapter("meta_muse", api_key="dummy")
    assert st_muse["adapter"] == "MetaMuseSparkAdapter"
    assert st_muse["model"] == "muse-spark-1.3"

    st_local = container.switch_llm_adapter("ollama_local")
    assert st_local["adapter"] == "OllamaLocalAdapter"

    manifest = container.manifest()
    assert set(manifest["ports"].keys()) == {
        "LanguageModelPort",
        "MultimodalVisionLanguagePort",
        "LavaSegmentationPort",
        "SeismicCatalogPort",
        "GeodeticDeformationPort",
        "VolcanicGasPort",
        "EmergencyAlertExportPort",
        "GeospatialFeatureExportPort",
        "OperationalReportExportPort",
        "AuditTrailPort",
    }


def test_custom_mock_adapters_injected_into_agent():
    """Verify true hexagonal dependency inversion: custom LanguageModelPort & LavaSegmentationPort can be injected."""

    class MockMetaMuseAdapter:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools=None, temperature=0.2, max_tokens=900) -> ModelTurn:
            self.calls += 1
            if self.calls == 1 and tools:
                return ModelTurn(
                    content="",
                    tool_calls=[ToolCall(id="tc_1", name="simulate_tenerife_scenario", arguments={"branch": "dorsal_noroeste"})],
                    provider="meta",
                    model="muse-spark-1.3",
                    adapter="MockMetaMuseAdapter",
                    latency_ms=12.5,
                )
            return ModelTurn(
                content="Respuesta sintetizada con Muse Spark tras ejecutar herramientas.",
                tool_calls=[],
                provider="meta",
                model="muse-spark-1.3",
                adapter="MockMetaMuseAdapter",
                latency_ms=18.0,
            )

        def status(self):
            return dict(ok=True, provider="meta", model="muse-spark-1.3", adapter="MockMetaMuseAdapter")

    class MockSAM3Adapter:
        def segment(self, scene: ThermalScene) -> SegmentationResult:
            m = np.zeros(scene.grid.elev.size, dtype=bool)
            m[:100] = True
            return SegmentationResult(
                mask_flat=m,
                confidence_flat=m.astype(float),
                area_ha=6.25,
                reach_m=500.0,
                prompt_points=[PromptPoint(scene.vent_xy[0], scene.vent_xy[1], 1, "vent")],
                prompt_box_xy=None,
                adapter="MockSAM3Adapter",
                model="meta/sam-3.1-test",
                mode="mock",
                latency_ms=1.2,
            )

        def status(self):
            return dict(port="LavaSegmentationPort", adapter="MockSAM3Adapter", family="Meta SAM 3.1", model="meta/sam-3.1-test", mode="mock", ready=True)

    agent = VolScanAgent(llm_port=MockMetaMuseAdapter(), seg_port=MockSAM3Adapter())
    res = agent.run("¿Qué impacto tendría el escenario Dorsal Noroeste en Tenerife?")
    assert res["ai"] is True
    assert res["model"]["adapter"] == "MockMetaMuseAdapter"
    assert any(tc["name"] == "simulate_tenerife_scenario" for tc in res["tool_calls"])


def test_sam3_day1_assimilation_and_63_scene_benchmark():
    day20 = sam3_scene_for_date("2021-09-20")
    assert day20["available"] is True
    assert day20["cems_already_delivered_at_now"] is False
    assert day20["lead_time_advantage_h"] is None
    assert day20["evidence"]["independent_validation"] is False
    assert day20["evidence"]["input_kind"] == "synthetic_from_cems_reference"
    assert day20["comparison_vs_cems"]["iou"] >= 0.80
    assert day20["assimilated_forecast"]["n_passes_assimilated"] == 1

    bench = sam3_validation_benchmark()
    assert bench["n_scenes"] == 63
    assert bench["summary"]["mean_iou"] >= 0.85
    assert bench["summary"]["lead_time_gain_h"] is None
    assert bench["evidence"]["operational"] is False


def test_api_hexagonal_endpoints():
    c = TestClient(app)
    arch = c.get("/api/ai/architecture")
    assert arch.status_code == 200
    data = arch.json()
    assert data["architecture"] == "hexagonal-ports-and-adapters"
    assert "LavaSegmentationPort" in data["ports"]
    assert len(data["registered_tools"]) == 5

    sw = c.post("/api/ai/adapter", json={"preset": "meta_llama4"})
    assert sw.status_code == 200
    assert sw.json()["llm"]["adapter"] == "MetaLlamaAdapter"

    # Restore default adapter
    c.post("/api/ai/adapter", json={"preset": "auto"})

    s3 = c.get("/api/lapalma2021/sam3/2021-09-20")
    assert s3.status_code == 200
    assert s3.json()["available"] is True

    chat_res = c.post("/api/chat", json={"question": "¿Qué mide Meta SAM 3.1 el 2021-09-20?", "context": "lapalma2021:2021-09-20"})
    assert chat_res.status_code == 200
    body = chat_res.json()
    assert body["answer"] and len(body["tool_calls"]) >= 1
    assert any(t["name"] == "run_sam3_satellite_assimilation" for t in body["tool_calls"])
