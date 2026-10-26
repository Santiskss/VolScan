# Data provenance

Every dataset that VolScan uses is public. Each entry lists its source, licence
and date of retrieval. Reproduce everything with `python scripts/fetch_lapalma_2021.py`.
Exact URLs and SHA256 hashes: `data/lapalma2021/manifest.json`.

## La Palma 2021 (Tajogaite) — `data/lapalma2021/`

| File | Source | Licence / attribution | Notes |
|---|---|---|---|
| `dem_utm25.npz` | Copernicus DEM GLO-30, tile N28 W018 (AWS open data) | © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the EU and ESA | Pre-eruption surface (TanDEM-X 2011-2015). Bilinear resampling to a 25 m UTM 28N grid; ocean from the WBM water mask set to NaN. DSM: includes buildings and vegetation. |
| `lava_extents.geojson` | Copernicus EMS EMSR546, 63 lava-flow observations (20 Sep – 17 Dec 2021), served by IGME | Copernicus Emergency Management Service (© 2021 European Union), EMSR546 | Photo-interpretation of satellite imagery. Coordinates rounded to 6 decimals (~0.1 m). Rasterised areas match the reported areas within 0.5 %. |
| `seismic_emsc.csv` | EMSC-CSEM FDSN event service, La Palma box, Aug 2021 – Jan 2022 | EMSC; event locations authored by IGN (MDD) where stated | FDSN text format, unmodified. |

Retrieved: 2026-10-26.
