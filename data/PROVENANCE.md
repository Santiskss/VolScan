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

## Canarias — `data/canarias/`

| File | Source | Licence / attribution | Notes |
|---|---|---|---|
| `ign/ign_YYYY_MM.csv` | IGN, Catálogo de terremotos, box 26.5–30 N, 19–12.5 W, Jan 2010 – today | Instituto Geográfico Nacional (IGN). Catálogo de terremotos. doi:10.7419/162.03.2022 | Downloaded month by month from the public form (`volscan.sources.ign_catalog`). The current month is refreshed live. Empty fields are kept empty. |
| `terrain_lapalma_100m.npz`, `terrain_archipelago_500m.npz` | Copernicus DEM GLO-30 (AWS open data) | © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the EU and ESA | Pre-2021 surface, bilinear to UTM 28N, ocean from WBM = NaN. `scripts/fetch_terrain_canarias.py`. |
| `lapalma2021/places.json` | OpenStreetMap via Nominatim | © OpenStreetMap contributors (ODbL) | Point locations of neighbourhoods. |

## La Palma 2021 exposure — `data/lapalma2021/exposure/` (`scripts/fetch_exposure_lapalma.py`)

| File | Source | Licence / attribution | Notes |
|---|---|---|---|
| `cems_builtup_grading.geojson` | Copernicus EMS EMSR546, Grading Monitoring 63 (17 Dec 2021), via IGME | © 2021 European Union, CEMS | 8,879 building points in the activation area; 2,988 graded "Destroyed". Used as exposure and as ground truth. |
| `cems_transport_grading.geojson` | idem | idem | 6,747 road segments; damage grade per segment. |
| `osm_facilities_places_20210901.json` | OpenStreetMap, Overpass attic query as of 2021-09-01 | © OpenStreetMap contributors (ODbL) | Services, places, irrigation reservoirs, substations. |
| `osm_roads_20210901.json` | idem | idem | Road network before the eruption, for the isolation analysis. |

## Deformation and gas — `data/canarias/gnss/`, `data/canarias/so2_omps_daily.csv` (`scripts/fetch_gnss_so2.py`)

| File | Source | Licence / attribution | Notes |
|---|---|---|---|
| `gnss/{STATION}.csv.gz` | Nevada Geodetic Laboratory, IGS20 daily solutions, Nubia-fixed ("AF") tenv3 series, 28 Canary Islands stations | Blewitt, G., W. C. Hammond, and C. Kreemer (2018), Harnessing the GPS data explosion for interdisciplinary science, Eos, 99, doi:10.1029/2018EO104623. Openly available. | Daily east/north/up in mm relative to the first epoch. Equipment-change steps (NGL `steps.txt`, type 1) removed by the difference of 20-day medians. Final series lag ~4 weeks. |
| `so2_omps_daily.csv` | NASA OMPS SO2, lower troposphere (Suomi-NPP; NOAA-20 for days NPP lacks), served as imagery by NASA GIBS | NASA EOSDIS GIBS / Worldview. NASA data are open (no restrictions). | Colours decoded to DU with the published GIBS colour map; mass above 1 DU in the box 25.5–31.5 N, 20.5–11 W, in kt. Saturates at 32 DU, so it is a lower bound. Days: Aug 2021 – Jan 2022 and the last two years. |

Retrieved: 2026-10-27.

## Tenerife scenarios — `data/tenerife/` (`scripts/fetch_terrain_canarias.py`, `scripts/fetch_exposure_tenerife.py`)

| File | Source | Licence / attribution | Notes |
|---|---|---|---|
| `dem_utm25.npz` | Copernicus DEM GLO-30 (AWS open data) | © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the EU and ESA | 25 m UTM 28N grid over Teide–Pico Viejo, both rifts and the slopes they drain to (not Anaga). |
| `../canarias/terrain_tenerife_100m.npz` | idem | idem | 3D view of the whole island. |
| `exposure/osm_buildings_20261027.json.gz` | OpenStreetMap via Overpass, 27 Oct 2026 | © OpenStreetMap contributors (ODbL) | ~100,000 building centroids. Coverage varies by municipality: a lower bound of what is exposed. |
| `exposure/osm_facilities_places_20261027.json.gz` | idem | idem | Services, places, water infrastructure, substations. |
| `exposure/osm_roads_20261027.json.gz` | idem | idem | Road network (motorway → residential) for the isolation analysis. |
| Historical vents | OpenStreetMap `natural=volcano/peak` positions | idem | Arenas Negras (1706), Chinyero (1909), Chahorra (1798), Fasnia and Arafo (1705). |

Retrieved: 2026-10-27.
