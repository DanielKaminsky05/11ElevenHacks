# Data

Toronto open-data sources, organized by theme. Original download filenames are noted in parentheses.

## transit/
- `ttc-bus-delay-2025.csv` — TTC bus delay records, 2025 (was `TTC Bus Delay Data since 2025.csv`)
- `ttc-streetcar-delay-2025.csv` — TTC streetcar delay records, 2025 (was `TTC Streetcar Delay Data since 2025.csv`)
- `ttc-ridership-analysis-1985-2019.xlsx` — ridership analysis 1985–2019 (was `1985-2019 Analysis of ridership (1).xlsx`)
- `ttc-routes-schedules-gtfs/` — TTC routes & schedules, GTFS feed (extracted from `TTC Routes and Schedules Data (1).zip`)

## bikeshare/
- `ridership-2025/` — Bike Share Toronto ridership, 2025 (extracted from `bikeshare-ridership-2025.zip`)

## geospatial/
- `toronto-centreline.geojson` — street/path centreline, EPSG:4326 (was `Centreline - Version 2 - 4326.geojson`)
- `areas.geojson` — area boundaries (was `Areas - 4326.geojson`)
- `pedestrian-crossovers.geojson` — pedestrian crossovers (was `Pedestrian Crossover - 4326.geojson`)
- `red-light-cameras.geojson` — red light camera locations (was `Red Light Cameras Data - 4326.geojson`)
- `transit-stations.geojson` — stations (was `Stations - 4326.geojson`)
- `traffic-beacons.geojson` — traffic beacons (was `Traffic Beacon - 4326.geojson`)

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
