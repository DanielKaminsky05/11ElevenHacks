# Data

Toronto open-data sources, organized by theme. Original download filenames are noted in parentheses.

## transit/
- `ttc-bus-delay-2025.csv` — TTC bus delay records, 2025 (was `TTC Bus Delay Data since 2025.csv`)
- `ttc-streetcar-delay-2025.csv` — TTC streetcar delay records, 2025 (was `TTC Streetcar Delay Data since 2025.csv`)
- `ttc-ridership-analysis-1985-2019.xlsx` — ridership analysis 1985–2019 (was `1985-2019 Analysis of ridership (1).xlsx`)
- `ttc-routes-schedules-gtfs/` — TTC routes & schedules, GTFS feed (extracted from `TTC Routes and Schedules Data (1).zip`)
- `go-transit-gtfs/` — Metrolinx / GO Transit regional GTFS feed (Metrolinx Open Data, OGL–Ontario)

## bikeshare/
- `ridership-2025/` — Bike Share Toronto ridership, 2025 (extracted from `bikeshare-ridership-2025.zip`)

## geospatial/
- `toronto-centreline.geojson` — street/path centreline, EPSG:4326 (was `Centreline - Version 2 - 4326.geojson`)
- `areas.geojson` — transit-related area boundaries, 37 features (was `Areas - 4326.geojson`); NOT the 158 neighbourhoods — see `neighbourhoods-158.geojson`
- `pedestrian-crossovers.geojson` — pedestrian crossovers (was `Pedestrian Crossover - 4326.geojson`)
- `red-light-cameras.geojson` — red light camera locations (was `Red Light Cameras Data - 4326.geojson`)
- `transit-stations.geojson` — stations (was `Stations - 4326.geojson`)
- `traffic-beacons.geojson` — traffic beacons (was `Traffic Beacon - 4326.geojson`)
- `neighbourhoods-158.geojson` — City of Toronto Neighbourhoods, 158-model polygons, EPSG:4326 (Toronto Open Data)
- `pedestrian-network.geojson` — pedestrian/walk network graph, EPSG:4326 (Toronto Open Data)
- `intersection-file.geojson` — all road intersections, EPSG:4326 (Toronto Open Data)
- `address-points.geojson` — One Address Repository, ~500k municipal address points, EPSG:4326 (Toronto Open Data; ~562 MB)
- `neighbourhood-improvement-areas.geojson` — equity designation polygons (Toronto Open Data)
- `priority-investment-neighbourhoods/` — Priority Investment Neighbourhoods shapefile (Toronto Open Data)
- `ontario-road-network/` — Ontario Road Network (ORN) Road Net Element, file geodatabase (Geospatial Ontario, OGL–Ontario; ~1.1 GB)

## census-demographics/ (continued)
- `wellbeing-civics-equity-indicators.xlsx` — Wellbeing Toronto civics & equity indicators (Toronto Open Data)
- `on-marg-2021-ontario-DA.xlsx` — Ontario Marginalization Index 2021, all-Ontario DA level (Public Health Ontario; research/non-commercial use)
- `on-marg-2021-toronto-n158.xlsx` — ON-Marg 2021 quintiles for Toronto neighbourhoods (PHO)
- `census-profile-2021-census-tracts/` — StatsCan Census Profile 2021, Census Tract level, CSV (98-401-X2021007; ~2.5 GB extracted)
- `census-profile-2021-cma/` — StatsCan Census Profile 2021, CMA/CA level, CSV (98-401-X2021002)
- `statcan-2021-da-boundaries/` — StatsCan 2021 Dissemination Area cartographic boundary shapefile (lda_000a21a_e)
- `spatial-access-measures-2024/` — StatsCan Spatial Access Measures 2024 (transit peak/offpeak, walking, cycling accessibility CSVs)

## traffic/
- `traffic-signals.csv` — traffic signal locations & attributes, 2,545 point records with `geometry` (was `139e5357-0caf-4c9a-a6be-ce94d38bcfeb.csv`, a CKAN resource UUID)
- `traffic-signals-readme.xlsx` — field definitions for `traffic-signals.csv` (was `Traffic Signal Tabular Readme.xlsx`)

## census-demographics/
- `neighbourhood-profiles-2021.xlsx` — 2021 neighbourhood profiles, 158-model (was `neighbourhood-profiles-2021-158-model (1).xlsx`)
- `ward-profiles-census-2011-2021.xlsx` — 2023 ward profiles, 2011–2021 census data (was `2023-WardProfiles-2011-2021-CensusData.xlsx`)
- `ward-profiles-geographic-areas.xlsx` — ward geographic areas (was `2023-WardProfiles-GeographicAreas.xlsx`)

## surveys/
- `seniors-survey-2017.xlsx` — seniors survey 2017 results (was `seniors-survey-2017-results.xlsx`)
- `employment-survey-2025.xlsx` — Toronto employment survey summary tables 2025 (was `Toronto employment survey summary tables 2025.xlsx`)

## _archives/
Original `.zip` downloads, retained after extraction. Safe to delete once the extracted folders are verified:
- `TTC Routes and Schedules Data (1).zip`
- `bikeshare-ridership-2025.zip`
