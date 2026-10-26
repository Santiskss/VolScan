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
| Lava flow ensemble engine + arrival times | in progress |
| Seismic unrest analytics (IGN catalogue) | in progress |
| Backtest vs. CEMS EMSR546 lava extents | planned |
| SAM 3.1 lava segmentation | planned |
| Assimilation (reweighting ensemble members) | planned |
| Muse Spark briefing agent | planned |

## Honesty rules

- A forecast is a probability, not a line.
- Historical observations, simulations and live data are always labelled as such.
- We never put a missing value in as zero, and we never invent certainty.
- VolScan supports decisions. It does not replace official alerts.

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## License

Code: Apache-2.0 (see `LICENSE`). Data: see `data/PROVENANCE.md`.
