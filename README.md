# VolScan

**A volcanic hazard twin for the Canary Islands that corrects itself with what it sees.**
Built by TephraLabs for the Meta Global AI Developer Hackathon 2026 (Startup track).

VolScan doesn't promise to predict *when* a volcano will erupt. Nobody can do
that reliably, and in Spain the official alert levels come from PEVOLCA. What
VolScan does:

1. **Reads seismic unrest.** It follows the rate, depth migration, b-value and
   energy release of the public IGN earthquake catalogue, and shows them over
   the real terrain.
2. **Forecasts where lava will go and when.** An ensemble of stochastic
   steepest-descent flows runs over the IGN digital terrain model. It produces
   a *probability of inundation* map, plus estimated arrival times at
   neighbourhoods.
3. **Corrects the forecast with observations.** SAM 3.1 segments lava flows in
   satellite, webcam and drone imagery. Ensemble members that disagree with
   what is observed lose weight.
4. **Briefs the people in charge.** A Muse Spark agent turns all of this into
   an operational briefing that states its uncertainty explicitly.

The first case study is the **Tajogaite eruption (La Palma, Sept–Dec 2021)**.
We validate against the near-daily lava extents mapped by Copernicus EMS
(activation EMSR546).

## Built during the hackathon

Everything in this repository was written during the hackathon (Oct 26 – Nov 4,
2026). The team also builds [PyroScan](https://www.instagram.com/pyroscan_oficial),
a wildfire-detection network (winner of El Talentón 2026). No PyroScan code is
part of this submission. Public datasets are listed with their licences in
[`data/PROVENANCE.md`](data/PROVENANCE.md).

| Component | Status |
|---|---|
| Lava flow ensemble engine + arrival times (`volscan.lava`) | ✅ |
| Assimilation of observed extents (`volscan.assimilation`) | ✅ |
| La Palma 2021 day-by-day replay, using only what was known each day (`volscan.replay`) | ✅ |
| IGN earthquake catalogue for the whole archipelago, 2010 → today, live refresh | ✅ |
| Seismic unrest index per zone, above a common Mc, with its 2011–2026 track record (`volscan.calibration`) | ✅ |
| Deformation: 28 public GNSS stations (NGL), anomaly vs 3-year trend (`volscan.deformation`) | ✅ |
| Gas: satellite SO2 over the archipelago (NASA OMPS via GIBS) (`volscan.sources.gibs_so2`) | ✅ |
| Impact with a clock: buildings, roads, services, isolated neighbourhoods (`volscan.impact`) | ✅ |
| Day-by-day validation against Copernicus, with map delivery delay and calibrated ranges | ✅ |
| Tenerife: prepared impact scenarios per volcanic system + one from current seismicity (`volscan.tenerife`) | ✅ |
| Monthly reports per zone: seismicity, deformation, gas | ✅ |
| Solunar: tidal / lunar phase per quake, Schuster + robust shift-null test | ✅ |
| RAG over curated sources + data-derived summaries, local LLM (Ollama) → Meta Muse | ✅ |
| Volcano Atlas web app (3D terrain, quakes at depth, lava probability, impact, validation, reports) | ✅ |
| SAM 3.1 lava/plume segmentation (satellite, webcams) | next |
| Muse Spark agent with tools | next |

### Results (honest)
- **Impact, 2021 validation** (83 daily 72 h forecasts, maps assumed known 24 h after acquisition): the real number of newly reached buildings fell inside the calibrated P10–P90 on **61/83 days**; total bias **−11 %**. Bursts of lateral growth (9–12 and 25–28 Oct) stay out of range. A watch list of buildings reachable *or hemmed in by the flow* held **54 %** of the buildings lost in the following 72 h.
- **Unrest index, 2011–2026**: index ≥ 4 happened in **15 episodes** archipelago-wide; **both eruptions** were preceded (El Hierro 80 days, La Palma 6 days). The rest were real unrest without eruption. It is a base rate, not a probability.
- **Deformation**: El Hierro 2011, station FRON anomalous from 20 Aug (7 weeks before the eruption). La Palma 2021: public stations see the co-eruptive deflation (MAZO −44 mm), not the near-vent pre-eruptive uplift (those IGN stations are not public).
- **SO2**: 0 before 19 Sep 2021, tens of kt during the eruption; quiet maximum over 2024–2026: 0.13 kt.

### First results (v0.1)
- **20 Sep 2021, day 1** (with only the first Copernicus map): VolScan gave a **67 % probability that the lava would reach Todoque** (destroyed on 21 Sep) and **36 % that it would reach the sea**.
- **27 Sep 2021**: estimated sea arrival P50 = **+26 h**, with P10–P90 between +1 h and +78 h. It actually reached the sea **+22 h** later (28 Sep, 22:02 UTC).
- While the front stalled (22–26 Sep), the ETA widened. VolScan flags "front stalled · area growing", but it doesn't model effusion pulses.
- **Tides**: the classic Schuster test comes out "significant" in every zone. With the catalogue declustered and the time-shift null hypothesis, **no tidal or lunar modulation** is detected in La Palma, El Hierro or Tenerife (2010–2026). We report it as it is.

## Honesty rules

- A forecast is a probability, not a line.
- Historical observations, simulations and live data are always labelled as such.
- We never put a missing value in as zero, and we never invent certainty.
- VolScan supports decisions. It does not replace official alerts.

## Quick start

Mac (one click): `./VolScan.command`. It creates the venv, builds the web app and opens http://localhost:8200.

Manually:
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[server,dev]"
(cd web && npm ci && npm run build)
uvicorn volscan.api.app:app --port 8200
pytest -q
```

AI: by default a local model through Ollama (`ollama pull qwen3:8b`, `ollama pull nomic-embed-text`).
With credits for the Meta Model API, set `META_API_KEY` in `.env` (see `.env.example`). Without a model,
everything else still works, and the AI panels say so explicitly.

Reproduce the data: `pip install -e ".[data]"`, then `python scripts/fetch_lapalma_2021.py`,
`python scripts/fetch_terrain_canarias.py`, `python scripts/fetch_exposure_lapalma.py`,
`python scripts/fetch_exposure_tenerife.py`, `python scripts/fetch_gnss_so2.py`, `python scripts/validate_lapalma.py`, and `python -c "import datetime as d; from volscan.sources.ign_catalog import sync_monthly as s; s('data/canarias/ign', d.date(2010,1,1), d.date.today())"`.

## License

Code: Apache-2.0 (see `LICENSE`). Data: see `data/PROVENANCE.md`.
