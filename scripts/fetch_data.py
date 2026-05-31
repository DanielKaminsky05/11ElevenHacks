#!/usr/bin/env python3
"""Fetch TransitRL open-data sources into ``data/``.

The ``data/`` folder is git-ignored (too large for GitHub — ~7 GB, with files
over the 100 MB limit). Instead of committing the data, commit this script and
regenerate the folder anywhere (e.g. clone the repo on the ASUS backend and run
``python scripts/fetch_data.py``).

Everything here comes from public open-data APIs / direct URLs:
  * City of Toronto Open Data  (CKAN API)
  * Statistics Canada / open.canada.ca
  * Metrolinx (GO Transit)     (OGL-Ontario)
  * Geospatial Ontario (LIO)   (OGL-Ontario)
  * Public Health Ontario      (ON-Marg, research/non-commercial)

Pure standard library — no ``pip install`` needed (works on Linux/ARM too).

Usage:
    python scripts/fetch_data.py              # download everything missing
    python scripts/fetch_data.py --check      # validate every source, download nothing
    python scripts/fetch_data.py --force      # re-download even if present
    python scripts/fetch_data.py --only NAME  # fetch a single entry by name
    python scripts/fetch_data.py --jobs 8     # parallel downloads (default 4)
    python scripts/fetch_data.py --list       # list manifest entries and exit
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ARCHIVES = DATA / "_archives"

UA = "TransitRL-fetch/1.0 (open-data reproducibility script)"
TORONTO_API = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_show?id="
CANADA_API = "https://open.canada.ca/data/en/api/3/action/package_show?id="

STATCAN_PROFILE = (
    "https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/"
    "download-telecharger/comp/getFile.cfm?LANG=E&GEONO={geono}&FILETYPE=CSV"
)

# --- manifest -------------------------------------------------------------
# Each entry:
#   name     unique id for --only / logging
#   dest     path under data/ (a file, or a directory when archive=True)
#   archive  True -> source is a .zip, extract its contents into dest dir
#   ckan     (portal, slug) — resolve the download URL from a CKAN API
#   match    how to pick the resource: {"name_re": ...} or {"format": ...}
#   url      direct download URL (used instead of ckan)
#   license  short note
MANIFEST: list[dict] = [
    # ---- City of Toronto: transit ----
    {"name": "ttc-gtfs", "dest": "transit/ttc-routes-schedules-gtfs", "archive": True,
     "ckan": ("toronto", "ttc-routes-and-schedules"),
     "match": {"name_re": r"^TTC Routes and Schedules Data$"}, "license": "Open Toronto"},
    {"name": "go-transit-gtfs", "dest": "transit/go-transit-gtfs", "archive": True,
     "url": "https://assets.metrolinx.com/raw/upload/v1683228856/Documents/Metrolinx/Open%20Data/GO-GTFS.zip",
     "license": "Metrolinx / OGL-Ontario"},

    # ---- City of Toronto: geospatial ----
    {"name": "toronto-centreline", "dest": "geospatial/toronto-centreline.geojson",
     "ckan": ("toronto", "toronto-centreline-tcl"),
     "match": {"name_re": r"Centreline - Version 2 - 4326\.geojson$"}, "license": "Open Toronto"},
    {"name": "neighbourhoods-158", "dest": "geospatial/neighbourhoods-158.geojson",
     "ckan": ("toronto", "neighbourhoods"),
     "match": {"name_re": r"^Neighbourhoods - 4326\.geojson$"}, "license": "Open Toronto"},
    {"name": "pedestrian-network", "dest": "geospatial/pedestrian-network.geojson",
     "ckan": ("toronto", "pedestrian-network"),
     "match": {"name_re": r"4326\.geojson$"}, "license": "Open Toronto"},
    {"name": "intersection-file", "dest": "geospatial/intersection-file.geojson",
     "ckan": ("toronto", "intersection-file-city-of-toronto"),
     "match": {"name_re": r"4326\.geojson$"}, "license": "Open Toronto"},
    {"name": "address-points", "dest": "geospatial/address-points.geojson",
     "ckan": ("toronto", "address-points-municipal-toronto-one-address-repository"),
     "match": {"name_re": r"4326\.geojson$"}, "license": "Open Toronto (~562 MB)"},
    {"name": "neighbourhood-improvement-areas", "dest": "geospatial/neighbourhood-improvement-areas.geojson",
     "ckan": ("toronto", "neighbourhood-improvement-areas"),
     "match": {"name_re": r"4326\.geojson$"}, "license": "Open Toronto"},
    {"name": "priority-investment-neighbourhoods", "dest": "geospatial/priority-investment-neighbourhoods", "archive": True,
     "ckan": ("toronto", "priority-investment-neighbourhoods"),
     "match": {"format": "ZIP"}, "license": "Open Toronto"},
    {"name": "red-light-cameras", "dest": "geospatial/red-light-cameras.geojson",
     "ckan": ("toronto", "red-light-cameras"),
     "match": {"name_re": r"Red Light Cameras Data - 4326\.geojson$"}, "license": "Open Toronto"},
    {"name": "pedestrian-crossovers", "dest": "geospatial/pedestrian-crossovers.geojson",
     "ckan": ("toronto", "traffic-signals-tabular"),
     "match": {"name_re": r"^Pedestrian Crossover - 4326\.geojson$"}, "license": "Open Toronto"},
    {"name": "traffic-beacons", "dest": "geospatial/traffic-beacons.geojson",
     "ckan": ("toronto", "traffic-signals-tabular"),
     "match": {"name_re": r"^Traffic Beacon - 4326\.geojson$"}, "license": "Open Toronto"},
    {"name": "ontario-road-network", "dest": "geospatial/ontario-road-network", "archive": True,
     "url": "https://ws.gisetl.lrc.gov.on.ca/fmedatadownload/Packages/fgdb/ORNELEM.zip",
     "license": "Geospatial Ontario / OGL-Ontario (~1.1 GB)"},

    # ---- City of Toronto: traffic ----
    {"name": "traffic-signals", "dest": "traffic/traffic-signals.csv",
     "ckan": ("toronto", "traffic-signals-tabular"),
     "match": {"name_re": r"^Traffic Signal - 4326\.csv$"}, "license": "Open Toronto"},
    {"name": "traffic-signals-readme", "dest": "traffic/traffic-signals-readme.xlsx",
     "ckan": ("toronto", "traffic-signals-tabular"),
     "match": {"name_re": r"Readme"}, "license": "Open Toronto"},

    # ---- City of Toronto: census / surveys ----
    {"name": "neighbourhood-profiles-2021", "dest": "census-demographics/neighbourhood-profiles-2021.xlsx",
     "ckan": ("toronto", "neighbourhood-profiles"),
     "match": {"name_re": r"2021-158-model"}, "license": "Open Toronto"},
    {"name": "ward-profiles-census-2011-2021", "dest": "census-demographics/ward-profiles-census-2011-2021.xlsx",
     "ckan": ("toronto", "ward-profiles-25-ward-model"),
     "match": {"name_re": r"2011-2021-CensusData"}, "license": "Open Toronto"},
    {"name": "ward-profiles-geographic-areas", "dest": "census-demographics/ward-profiles-geographic-areas.xlsx",
     "ckan": ("toronto", "ward-profiles-25-ward-model"),
     "match": {"name_re": r"GeographicAreas"}, "license": "Open Toronto"},
    {"name": "wellbeing-civics-equity-indicators", "dest": "census-demographics/wellbeing-civics-equity-indicators.xlsx",
     "ckan": ("toronto", "wellbeing-toronto-civics-equity-indicators"),
     "match": {"format": "XLSX"}, "license": "Open Toronto"},
    {"name": "employment-survey-2025", "dest": "surveys/employment-survey-2025.xlsx",
     "ckan": ("toronto", "toronto-employment-survey-summary-tables"),
     "match": {"name_re": r"2025$"}, "license": "Open Toronto"},
    {"name": "seniors-survey-2017", "dest": "surveys/seniors-survey-2017.xlsx",
     "ckan": ("toronto", "seniors-survey-2017"),
     "match": {"format": "XLSX"}, "license": "Open Toronto"},

    # ---- City of Toronto: bikeshare ----
    {"name": "bikeshare-2025", "dest": "bikeshare/ridership-2025", "archive": True,
     "ckan": ("toronto", "bike-share-toronto-ridership-data"),
     "match": {"name_re": r"bikeshare-ridership-2025\.zip$"}, "license": "Open Toronto"},

    # ---- Federal: Statistics Canada ----
    {"name": "census-profile-2021-census-tracts", "dest": "census-demographics/census-profile-2021-census-tracts", "archive": True,
     "url": STATCAN_PROFILE.format(geono="007"), "license": "StatCan Open Licence (~2.5 GB extracted)"},
    {"name": "census-profile-2021-cma", "dest": "census-demographics/census-profile-2021-cma", "archive": True,
     "url": STATCAN_PROFILE.format(geono="002"), "license": "StatCan Open Licence"},
    {"name": "statcan-2021-da-boundaries", "dest": "census-demographics/statcan-2021-da-boundaries", "archive": True,
     "url": "https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/files-fichiers/lda_000a21a_e.zip",
     "license": "StatCan Open Licence"},
    {"name": "spatial-access-measures-2024", "dest": "census-demographics/spatial-access-measures-2024", "archive": True,
     "url": "https://www150.statcan.gc.ca/n1/pub/27-26-0001/2023001/zip/sam-msa2024-eng.zip",
     "license": "StatCan Open Licence"},

    # ---- Provincial: Public Health Ontario (ON-Marg) ----
    {"name": "on-marg-2021-ontario-DA", "dest": "census-demographics/on-marg-2021-ontario-DA.xlsx",
     "url": "https://www.publichealthontario.ca/-/media/Data-Files/index-on-marg.xlsx",
     "license": "PHO — research/non-commercial"},
    {"name": "on-marg-2021-toronto-n158", "dest": "census-demographics/on-marg-2021-toronto-n158.xlsx",
     "url": "https://www.ontariohealthprofiles.ca/loaddataON/MARG/neighb/N158_ONMarg_2021_Quintiles_LHIN_7.xlsx",
     "license": "PHO — research/non-commercial"},
]

# Files whose original open-data source could not be confirmed. Document them
# so a fresh checkout knows they must be supplied manually.
MANUAL_NOTES = [
    "geospatial/areas.geojson — 37 transit-related area polygons; original source unconfirmed.",
    "geospatial/transit-stations.geojson — station points; original source unconfirmed.",
]


# --- helpers --------------------------------------------------------------
# Set by --insecure: skip TLS verification for hosts with broken cert chains
# (some government open-data servers omit intermediate certs). Off by default.
SSL_CONTEXT: ssl.SSLContext | None = None


def _open(url: str, method: str = "GET", range_head: bool = False):
    headers = {"User-Agent": UA}
    if range_head:
        headers["Range"] = "bytes=0-0"
    return urlopen(Request(url, headers=headers, method=method), timeout=120, context=SSL_CONTEXT)


def resolve_url(entry: dict) -> str:
    """Return the concrete download URL for an entry."""
    if "url" in entry:
        return entry["url"]
    portal, slug = entry["ckan"]
    api = TORONTO_API if portal == "toronto" else CANADA_API
    with _open(api + slug) as resp:
        pkg = json.load(resp)
    resources = pkg["result"]["resources"]
    match = entry.get("match", {})
    for r in resources:
        if "name_re" in match and not re.search(match["name_re"], r.get("name", "")):
            continue
        if "format" in match and r.get("format", "").upper() != match["format"].upper():
            continue
        if r.get("url"):
            return r["url"]
    raise LookupError(f"no resource matched {match} in '{slug}' "
                      f"(available: {[r.get('name') for r in resources]})")


def is_present(entry: dict) -> bool:
    dest = DATA / entry["dest"]
    if entry.get("archive"):
        return dest.is_dir() and any(dest.iterdir())
    return dest.is_file() and dest.stat().st_size > 0


def _download(url: str, out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".part")
    total = 0
    with _open(url) as resp, open(tmp, "wb") as fh:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            total += len(chunk)
    tmp.replace(out)
    return total


def fetch(entry: dict, force: bool) -> str:
    name = entry["name"]
    dest = DATA / entry["dest"]
    if not force and is_present(entry):
        return f"SKIP  {name} (already present)"
    url = resolve_url(entry)
    if entry.get("archive"):
        ARCHIVES.mkdir(parents=True, exist_ok=True)
        zpath = ARCHIVES / f"{name}.zip"
        size = _download(url, zpath)
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(dest)
        return f"OK    {name} -> {entry['dest']}/ ({size/1e6:.1f} MB zip, extracted)"
    size = _download(url, dest)
    return f"OK    {name} -> {entry['dest']} ({size/1e6:.1f} MB)"


def check(entry: dict) -> str:
    name = entry["name"]
    try:
        url = resolve_url(entry)
    except Exception as exc:  # noqa: BLE001
        return f"FAIL  {name}: resolve: {exc}"
    try:
        with _open(url, range_head=True) as resp:
            clen = resp.headers.get("Content-Range") or resp.headers.get("Content-Length") or "?"
        return f"OK    {name}: reachable ({clen})  {url[:90]}"
    except (HTTPError, URLError) as exc:
        # Some hosts reject Range/HEAD; a resolvable URL is still a useful signal.
        return f"WARN  {name}: resolved but probe failed ({exc}); url={url[:90]}"


# --- main -----------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch TransitRL open-data into data/")
    ap.add_argument("--check", action="store_true", help="validate sources, download nothing")
    ap.add_argument("--force", action="store_true", help="re-download even if present")
    ap.add_argument("--only", metavar="NAME", help="fetch a single entry by name")
    ap.add_argument("--jobs", type=int, default=4, help="parallel workers (default 4)")
    ap.add_argument("--list", action="store_true", help="list entries and exit")
    ap.add_argument("--insecure", action="store_true",
                    help="skip TLS verification (for gov hosts with broken cert chains)")
    args = ap.parse_args()

    if args.insecure:
        global SSL_CONTEXT
        SSL_CONTEXT = ssl._create_unverified_context()
        print("WARNING: TLS certificate verification disabled (--insecure).")

    entries = MANIFEST
    if args.only:
        entries = [e for e in MANIFEST if e["name"] == args.only]
        if not entries:
            print(f"no entry named '{args.only}'. Known: {[e['name'] for e in MANIFEST]}")
            return 2

    if args.list:
        for e in MANIFEST:
            src = e.get("url") or f"ckan:{e['ckan'][1]}"
            print(f"{e['name']:38} -> data/{e['dest']:52} [{src[:60]}]")
        if MANUAL_NOTES:
            print("\nManual (source unconfirmed):")
            for n in MANUAL_NOTES:
                print(f"  - {n}")
        return 0

    worker = check if args.check else (lambda e: fetch(e, args.force))
    fails = 0
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futs = {pool.submit(worker, e): e for e in entries}
        for fut in as_completed(futs):
            try:
                line = fut.result()
            except Exception as exc:  # noqa: BLE001
                line = f"FAIL  {futs[fut]['name']}: {exc}"
            if line.startswith("FAIL"):
                fails += 1
            print(line, flush=True)

    if not args.check and MANUAL_NOTES:
        print("\nNote — supply these manually (source unconfirmed):")
        for n in MANUAL_NOTES:
            print(f"  - {n}")
    print(f"\n{'Checked' if args.check else 'Fetched'} {len(entries)} entries, {fails} failure(s).")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
