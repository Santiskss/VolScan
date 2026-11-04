# How to read VolScan: the official traffic light versus our own indices

## Volcanic traffic light (official)
In the Canary Islands, volcanic alerts to the public are run by **PEVOLCA** (Government of the Canary Islands), advised by its scientific committee (IGN, INVOLCAN and others). Island councils have their own island plans (PAIV). The traffic light has four colours (green, yellow, orange and red), from normal to imminent or ongoing eruption. **VolScan does not issue alert levels.**

## Unrest index (VolScan)
It runs from 0 to 10 and compares the last 7 days of each zone with that zone's own previous year (leaving a 30-day gap). It only counts earthquakes above the **common magnitude of completeness** (Mc by maximum curvature over both periods), so a denser network does not look like more activity:
- **Rate**: how unlikely the week's number of earthquakes is under the baseline rate (Poisson test): 0 if normal, 1 if the probability is 1 in 10 billion.
- **Energy**: the week's seismic energy against the most energetic week of the previous year (0 = equal, 1 = a hundred times more).
- **Shallowing**: how many km shallower the median depth is (10 km count as 1). It needs 20 located earthquakes in each period.
Rate and energy do not score with fewer than 5 earthquakes above Mc in the week. The index is the mean of the available components × 10. **It is not an eruption probability.**

### Track record (2011–2026)
Computed every 2 days in the 7 zones (each island with its sea out to 25 km, without overlap). With the previous index (ratios without Mc) there were 84 episodes above 4, most in zones with almost no earthquakes. With the current one:

| Index ≥ | Episodes | Preceded an eruption | Lead time |
|---|---|---|---|
| 3 | 34 | 2 of 2 | El Hierro 80 days · La Palma 6 days |
| 4 | 15 | 2 of 2 | El Hierro 80 days · La Palma 6 days |
| 5 | 14 | 2 of 2 | El Hierro 12 days · La Palma 6 days |
| 6 | 7 | 2 of 2 | El Hierro 10 days · La Palma 6 days |
| 7 | 3 | 1 of 2 | La Palma 6 days |

The other episodes were real unrest without an eruption (deep swarms under La Palma 2017–2020, El Hierro 2013). Two eruptions are not enough to compute a probability. The table is a base rate, recomputed every week in the “Canary Islands Live” tab.

## Deformation (GNSS)
Public GNSS stations processed by the Nevada Geodetic Laboratory, with the African plate fixed. For each station the trend of the previous 3 years is fitted and we measure how far the median of the last 30 days departs from it (in mm), compared with its own scatter (z): |z| < 3 normal, 3–6 watch, > 6 anomalous. Antenna changes are corrected.
- El Hierro 2011: FRON (La Frontera) was anomalous from 20 August, 7 weeks before the submarine eruption.
- La Palma 2021: MAZO and LPAL (10 and 17 km away) record the subsidence during the eruption (MAZO −44 mm by December) but **not** the earlier uplift: the IGN measured that with stations next to the vent that are not public. Seeing it would need an agreement with IGN or GRAFCAN.
- The final series arrives about 4 weeks late; VolScan shows the date of the last data point.

## Gas (satellite SO2)
SO2 visible from space over the archipelago, from NASA's OMPS instrument (lower troposphere), in kilotonnes above 1 DU. Over two quiet years (2024–2026) the daily maximum was 0.13 kt; VolScan flags “SO2 detected” from 1 kt. On La Palma 2021: 0 before 19 September, tens of kt during the eruption and 0 from mid-December. It detects eruptions and strong degassing, not the diffuse degassing (CO2, helium) that INVOLCAN measures on the ground, which would need an agreement.

## b-value
Slope of the Gutenberg-Richter law (Aki-Utsu, with Mc by maximum curvature + 0.2). In volcanic zones, a high b (>1.3) can point to fluids or fracturing. It is not computed with fewer than 50 earthquakes above Mc.

## Tides and Moon
For each earthquake, VolScan computes the phase of the Earth tide (~12.42 h cycle) and of the Moon, and applies the Schuster test. If p < 0.05, the phases are not uniform. That **does not prove causation**, and swarms inflate significance, so we also show the result after declustering (one earthquake per 6 h window).

## Lava flow forecast
An ensemble of hundreds of steepest-descent paths over the pre-eruption terrain, with uncertainty in the vent, length, width and viscosity. They are reweighted with every Copernicus map **already delivered** (assumed to arrive 24 h after the image; Copernicus takes between 7 h and 48 h). The result is the **probability** of coverage and the quantiles (P10/P50/P90) of arrival time at neighbourhoods and the sea. When the front stalls for days, the time estimate widens. That happened from 22 to 26 September 2021.

## Impact with a clock, and validation
The ensemble gives the where; the how much comes from the area growth rate of the maps already delivered, counted from the date of the latest map. The P10–P90 range is calibrated with the real errors of earlier forecasts whose outcome was already known, and its upper end covers the case where 30 % of the new area fills ground hemmed in by the flow. In 2021 the real value fell inside the range on 67 of 83 days (81 %, for a nominal 80 %) and the total was 11 % low.

The burst of 25–28 October (about 10 buildings per new hectare, in a very dense area) is still out of range. We tried three ways to forecast where that growth goes (overflows from the margins over already covered ground, closeness to active margins, and infill between flow arms). None improved the count, so they are not used for counting. They are used for the **watch list**: buildings hemmed in by the flow caught an extra 21 % of what was lost in the next 72 h.
