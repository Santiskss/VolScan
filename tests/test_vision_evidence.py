import numpy as np
from volscan.grid import Grid
from volscan.ai.ports import ThermalScene
from volscan.ai.sam3_adapter import MetaSAM3Adapter

def scene():
 g=Grid(np.full((5,5),100.),0,125,25)
 return ThermalScene(g,np.full((5,5),.8),np.full((5,5),700.),(62.5,62.5),'2021-09-20T00:00:00Z')

def test_checkpoint_file_is_not_claimed_as_executed(tmp_path):
 checkpoint=tmp_path/'weights.pt';checkpoint.write_bytes(b'not real weights')
 adapter=MetaSAM3Adapter(endpoint='',checkpoint=str(checkpoint))
 assert adapter.status()['checkpoint_implemented'] is False
 r=adapter.segment(scene())
 assert r.mode=='physics_prompt_seeded'
 assert r.model=='deterministic-geodesic'

def test_failed_remote_response_reports_actual_fallback(monkeypatch):
 adapter=MetaSAM3Adapter(endpoint='https://example.invalid/segment')
 monkeypatch.setattr(adapter,'_call_remote_api',lambda *a:None)
 r=adapter.segment(scene())
 assert r.mode=='physics_prompt_seeded'
 assert r.model=='deterministic-geodesic'
