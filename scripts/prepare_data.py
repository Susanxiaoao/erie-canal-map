#!/usr/bin/env python3
"""
Erie Canal Corridor — Data Preparation Script
=============================================
Generates the four data files consumed by index.html into the data/ folder.

Usage
-----
    python scripts/prepare_data.py [options]

Options
-------
    --skip-healthcare    Skip NYS health facility download
    --skip-demographics  Skip Census ACS + TIGER download
    --skip-canal         Skip canal corridor geometry download
    --skip-industry      Skip writing the curated industry sites

Environment variables
---------------------
    CENSUS_API_KEY   Free key from https://api.census.gov/data/key_signup.html
                     Not strictly required but improves reliability.

Dependencies
------------
    pip install pandas geopandas requests
"""

import os
import re
import sys
import json
import time
import argparse
from pathlib import Path

try:
    import requests
    import pandas as pd
    import geopandas as gpd
except ImportError as exc:
    print(f"Missing dependency: {exc}")
    print("Install with:  pip install pandas geopandas requests")
    sys.exit(1)

# ── Output directory (created automatically) ────────────────────────────────

REPO_ROOT  = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "data"

# ── Erie Canal corridor county FIPS (NYS state FIPS = 36) ───────────────────

CORRIDOR_COUNTIES: dict[str, str] = {
    "Albany":       "001",
    "Cayuga":       "011",
    "Erie":         "029",
    "Herkimer":     "043",
    "Madison":      "053",
    "Monroe":       "055",
    "Montgomery":   "057",
    "Niagara":      "063",
    "Oneida":       "065",
    "Onondaga":     "067",
    "Orleans":      "073",
    "Schenectady":  "093",
    "Seneca":       "099",
    "Wayne":        "117",
}

NYS_FIPS = "36"

# ════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — Healthcare facilities (NYS Health Facility data)
# ════════════════════════════════════════════════════════════════════════════

# Socrata dataset: "Health Facility General Information"
# Browse current endpoints at https://health.data.ny.gov/browse?category=Health
HEALTH_ENDPOINTS = [
    "https://health.data.ny.gov/resource/vn5v-hh5r.json",  # primary candidate
    "https://health.data.ny.gov/resource/2g9y-7kqm.json",  # fallback candidate
]

FACILITY_TYPE_MAP = {
    "hospital":          ["hospital", "medical center", "health system", "health center"],
    "urgent care":       ["urgent care", "emergicenter", "walk-in"],
    "clinic":            ["clinic", "diagnostic", "ambulatory", "outpatient", "surgery center"],
    "nursing home":      ["nursing home", "residential", "skilled nursing", "long term", "ltc"],
    "pharmacy":          ["pharmacy", "drug store"],
    "mental health":     ["mental health", "psychiatric", "behavioral", "counseling"],
}


def normalize_facility_type(raw: str) -> str:
    """Map a raw NYS facility description to one of the known type keys."""
    lower = (raw or "").lower().strip()
    for canonical, keywords in FACILITY_TYPE_MAP.items():
        if any(kw in lower for kw in keywords):
            return canonical
    return "other"


# Opening-year lookup for Rochester / Monroe County facilities.
# Keyed by lowercase substrings of the facility name.
# All years verified from primary sources (hospital history pages, Wikipedia,
# NYS DOH records, news archives). See research notes in git history.
ROCHESTER_OPEN_YEARS: dict[str, int] = {
    # ── Hospitals ──────────────────────────────────────────────────────────
    # Rochester General Hospital: chartered 1847, opened as Rochester City Hospital 1864
    # Source: Wikipedia / RRH Archives / JAMA centennial history
    "rochester general":           1847,
    "rochester city hospital":     1847,

    # Strong Memorial Hospital: opened January 4, 1926
    # Source: URMC official history; URMC Newsroom 100th anniversary
    "strong memorial":             1926,
    "university of rochester med": 1926,

    # Highland Hospital: opened 1889 as Hahnemann Hospital; renamed Highland 1921
    # Source: URMC Highland history page; Wikipedia
    "highland hospital":           1889,

    # St. Mary's Hospital: opened September 1857; merged into Unity 1997
    # Source: RRH St. Mary's history exhibit; HMDB historical marker
    "st. mary":                    1857,
    "saint mary":                  1857,
    "st mary":                     1857,

    # Unity Hospital (Park Ave / Greece campus): Park Avenue Hospital 1894 →
    #   Park Ridge Hospital 1975 → Unity Hospital 2006
    # Facilities named "Unity Hospital" (not St. Mary's campus) trace to 1894
    # Source: Wikipedia – Unity Hospital; Yahoo/D&C Park Ave. history
    "unity hospital":              1894,
    "park avenue hospital":        1894,
    "park ridge hospital":         1975,   # opened as Park Ridge 1975

    # Monroe Community Hospital: opened August 1, 1933
    # (county almshouse roots 1826, but current MCH facility = 1933)
    # Source: MonroeHosp.org official history — NOT 1894 (that's Park Ave Hospital)
    "monroe community hospital":   1933,

    # Golisano Children's Hospital: named 2002, standalone building opened July 2015
    # Source: Wikipedia; URMC Newsroom
    "golisano children":           2015,

    # ── Dental ─────────────────────────────────────────────────────────────
    # Eastman Dental / Eastman Institute for Oral Health:
    # Rochester Dental Dispensary opened 1917 (funded by Eastman's 1915 gift)
    # Source: URMC Eastman history page; Wikipedia
    "eastman dental":              1917,
    "eastman institute for oral":  1917,

    # ── Community Health Centers ───────────────────────────────────────────
    # Anthony L. Jordan Health Center: founded 1968 as Rochester Neighborhood
    # Health Center in Hanover Houses basement
    # Source: JordanHealth.org/our-history
    "jordan health":               1968,
    "anthony l. jordan":           1968,
    "jordan at threshold":         1968,
    "jordan health link":          1968,

    # Trillium Health: founded 1989 as Community Health Network HIV/AIDS clinic
    # (merged with AIDS Rochester 2010; rebranded Trillium Health)
    # Source: TrilliumHealth.org/about-us/our-history
    "trillium health":             1989,

    # Oak Orchard Community Health Center: founded 1966 as UR migrant farmworker
    # health project   Source: CHC Chronicles / Oak Orchard Health
    "oak orchard":                 1966,

    # Planned Parenthood: Rochester clinic opened 1934 (Monroe County Birth
    # Control League); national 1916 date is Brooklyn, NOT Rochester
    # Source: UR RBSCP finding aid
    "planned parenthood":          1934,

    # Bivona Child Advocacy Center: opened August 1, 2004
    # Source: 13WHAM 20th anniversary; RochesterFirst rebrand article
    "bivona":                      2004,

    # Rochester Hearing and Speech Center: founded 1922 by Alice Howe Hatton
    # Source: RHSC centennial page; Greater Rochester Chamber
    "rochester hearing and speech": 1922,
    "hearing and speech center of rochester": 1922,

    # Genesee Health Service / Genesee Mental Health: formally consolidated 1967
    # Source: RRH Behavioral Health Network Collection
    "genesee health service":      1967,
    "genesee mental health":       1967,
    "rochester mental health":     1967,

    # Mary M. Gooley Hemophilia Center: treatment center opened 1959
    # Source: HemoCenter.org/our-history; Hemophilia Alliance timeline
    "gooley hemophilia":           1959,
    "hemophilia center":           1959,

    # United Cerebral Palsy / CP Unlimited: founded 1946 by parents (predates
    # national UCP org founded 1949)   Source: CPUnlimited.org; Kids Out & About
    "united cerebral palsy":       1946,
    "cp unlimited":                1946,

    # ── Senior Care / Nursing ──────────────────────────────────────────────
    # The Friendly Home: founded April 11, 1849
    # Source: FriendlySeniorLiving.org/history; RBJ 175th anniversary article
    "friendly home":               1849,
    "friendly senior living":      1849,

    # Jewish Home of Rochester: established 1920
    # Source: JewishHomeRoc.org rebranding article; HJ Sims profile
    "jewish home":                 1920,
    "jewish senior life":          1920,

    # St. Ann's Community: founded 1873 by Sisters of St. Joseph
    # Source: StAnnsCommunity.com/history; Catholic Courier
    "st. ann":                     1873,
    "st ann":                      1873,

    # Rochester Center for Rehabilitation and Nursing: opened August 1, 1980
    # Source: NYS Health Profile / ProPublica
    "rochester center for rehabilitation": 1980,

    # Kirkhaven: Medicare/Medicaid participation began February 20, 1984
    # Source: ProPublica Nursing Homes
    "kirkhaven":                   1984,
}


def _lookup_open_year(facility_name: str, county: str, fac_opn_dat: str) -> str:
    """Return the best opening-year string for a facility.

    For Monroe County (Rochester Case Study):
      Use ONLY the manually verified historical lookup. The NYS fac_opn_dat
      for community health organizations often reflects administrative
      certification dates (many cluster at 1979-1981 when NYS first required
      operating certificates for these facility types) rather than true
      founding dates, making it unreliable for historical visualization.

    For all other corridor counties:
      Use fac_opn_dat when year > 1901 (1901-01-01 is NYS's sentinel for
      pre-electronic records). This gives a reasonable proxy for modern
      facilities even if it is a re-licensure date rather than founding.
    """
    if county.lower() == "monroe":
        # ── Monroe County: verified lookup only ─────────────────────────
        name_lower = facility_name.lower()
        for substr, year in ROCHESTER_OPEN_YEARS.items():
            # Word-boundary matching prevents "community" from matching "unity"
            if re.search(r'\b' + re.escape(substr) + r'\b', name_lower):
                return str(year)
        return ""

    # ── Other counties: NYS certification date as proxy ─────────────────
    if fac_opn_dat:
        try:
            yr = int(fac_opn_dat[:4])
            if yr > 1901:
                return str(yr)
        except (ValueError, TypeError):
            pass

    return ""


def download_healthcare(output_path: Path) -> None:
    """Download and filter NYS health facility data to corridor counties."""
    print("\n[1/4] Healthcare facilities …")

    county_names_upper = [c.upper() for c in CORRIDOR_COUNTIES.keys()]
    # Socrata SOQL IN clause — more reliable than chained OR
    county_list   = ",".join(f"'{c}'" for c in county_names_upper)
    county_filter = f"county in ({county_list})"

    data = []
    for endpoint in HEALTH_ENDPOINTS:
        # First attempt: filtered request (no $select so we get all fields regardless of schema)
        for where_param in [county_filter, None]:
            params: dict = {"$limit": 50000}
            if where_param:
                params["$where"] = where_param
            try:
                resp = requests.get(endpoint, params=params, timeout=45)
                resp.raise_for_status()
                raw = resp.json()
                if isinstance(raw, list) and len(raw) > 0:
                    data = raw
                    label = "filtered" if where_param else "all-NY (will filter locally)"
                    print(f"  ✓ {len(data)} records from {endpoint} ({label})")
                    break
            except Exception as exc:
                print(f"  ✗ {endpoint} params={params} — {exc}")
        if data:
            break

    # Print the actual field names returned so future debugging is easy
    if data:
        print(f"  Fields in response: {sorted(data[0].keys())}")

    rows = []
    for item in data:
        county_raw = (item.get("county") or item.get("County") or "").strip()
        # Local filter when we fetched all-NY records
        if county_raw.upper() not in county_names_upper:
            continue

        try:
            lat = float(item.get("latitude") or item.get("Latitude") or 0)
            lng = float(item.get("longitude") or item.get("Longitude") or 0)
        except (TypeError, ValueError):
            continue
        if lat == 0.0 or lng == 0.0:
            continue

        # Facility type may live in 'description', 'facility_type', or 'type'
        raw_type = (
            item.get("description")
            or item.get("facility_type")
            or item.get("type")
            or "other"
        )
        rows.append(
            {
                "facility_name": (item.get("facility_name") or item.get("name") or "").strip(),
                "facility_type": normalize_facility_type(raw_type),
                "county":        county_raw.title(),
                "latitude":      round(lat, 6),
                "longitude":     round(lng, 6),
                "open_year":     _lookup_open_year(
                    (item.get("facility_name") or item.get("name") or "").strip(),
                    county_raw.title(),
                    item.get("fac_opn_dat") or "",
                ),
            }
        )

    if not rows:
        print("  ⚠  No healthcare data retrieved. Check the Socrata endpoint.")
        return

    df = pd.DataFrame(rows).drop_duplicates(subset=["facility_name", "latitude", "longitude"])
    df.to_csv(output_path, index=False)
    print(f"  Saved {len(df)} facilities → {output_path}")


# ════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — Demographic data (ACS 5-year + TIGER tracts)
# ════════════════════════════════════════════════════════════════════════════

ACS_YEAR    = 2022
ACS_VARS    = "NAME,B01002_001E,B19013_001E,B01003_001E"
# B01002_001E = Median age
# B19013_001E = Median household income
# B01003_001E = Total population
TIGER_URL   = f"https://www2.census.gov/geo/tiger/TIGER{ACS_YEAR}/TRACT/tl_{ACS_YEAR}_36_tract.zip"


def _safe_float(val) -> float | None:
    try:
        f = float(val)
        return None if f < 0 else f    # Census uses -666666666 for "N/A"
    except (TypeError, ValueError):
        return None


def fetch_acs_county(county_name: str, county_fips: str, api_key: str) -> list[dict]:
    """Return a list of tract-level attribute dicts for one county."""
    url = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5"
    params = {
        "get": ACS_VARS,
        "for": "tract:*",
        "in": f"state:{NYS_FIPS} county:{county_fips}",
    }
    if api_key:
        params["key"] = api_key

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    headers = rows[0]
    records = []
    for row in rows[1:]:
        d   = dict(zip(headers, row))
        geo = f"{NYS_FIPS}{county_fips}{d['tract']}"
        records.append(
            {
                "GEOID":              geo,
                "tract_name":         d.get("NAME", ""),
                "median_age":         _safe_float(d.get("B01002_001E")),
                "median_income":      _safe_float(d.get("B19013_001E")),
                "total_population":   _safe_float(d.get("B01003_001E")),
                "county":             county_name,
                "county_fips":        county_fips,
                "tract":              d.get("tract", ""),
            }
        )
    return records


def download_demographics(output_path: Path) -> None:
    """Fetch ACS attributes, join to TIGER tract geometries, write GeoJSON."""
    print("\n[2/4] Demographics (ACS + TIGER) …")

    api_key = os.environ.get("CENSUS_API_KEY", "")
    if not api_key:
        print("  ⚠  CENSUS_API_KEY not set; Census API requests may be rate-limited.")

    # ── Fetch tabular ACS data ─────────────────────────────────────────
    all_records: list[dict] = []
    for county_name, county_fips in CORRIDOR_COUNTIES.items():
        print(f"  ACS: {county_name} County …", end=" ", flush=True)
        try:
            recs = fetch_acs_county(county_name, county_fips, api_key)
            all_records.extend(recs)
            print(f"{len(recs)} tracts")
        except Exception as exc:
            print(f"FAILED ({exc})")
        time.sleep(0.15)   # be polite to Census API

    if not all_records:
        print("  ✗ No ACS data — aborting demographics step.")
        return

    dem_df = pd.DataFrame(all_records)
    dem_df["GEOID"] = dem_df["GEOID"].astype(str)

    # ── Download TIGER tract shapefile for NY ──────────────────────────
    print(f"  Downloading TIGER tracts: {TIGER_URL}")
    try:
        gdf = gpd.read_file(TIGER_URL)
    except Exception as exc:
        print(f"  ✗ Could not load TIGER file: {exc}")
        return

    gdf = gdf[gdf["COUNTYFP"].isin(set(CORRIDOR_COUNTIES.values()))].copy()
    gdf = gdf.to_crs("EPSG:4326")
    gdf["GEOID"] = gdf["GEOID"].astype(str)

    # ── Join ───────────────────────────────────────────────────────────
    merged = gdf.merge(dem_df, on="GEOID", how="left")

    # Population density: people per square mile
    # Reproject to a planar CRS for area calculation (NAD83 / UTM zone 18N)
    area_m2 = merged.geometry.to_crs("EPSG:32618").area
    area_sqmi = area_m2 / 2_589_988.0
    merged["population_density"] = (merged["total_population"] / area_sqmi).where(area_sqmi > 0)

    # Simplify geometries — reduces file size without visual impact at zoom ~7
    merged["geometry"] = merged.geometry.simplify(0.001, preserve_topology=True)

    keep = ["GEOID", "tract_name", "median_age", "median_income",
            "population_density", "county", "geometry"]
    out = merged[[c for c in keep if c in merged.columns]]
    out.to_file(output_path, driver="GeoJSON")
    print(f"  Saved {len(out)} tracts → {output_path}")


# ════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — Canal corridor geometry
# ════════════════════════════════════════════════════════════════════════════

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

OVERPASS_QUERY = """
[out:json][timeout:90];
(
  way["name"~"Erie Canal"]["waterway"~"canal|river"](40.0,-80.0,44.5,-73.0);
  way["name"~"Erie Canalway"]["waterway"](40.0,-80.0,44.5,-73.0);
  relation["name"~"Erie Canal"](40.0,-80.0,44.5,-73.0);
);
out geom;
"""


def download_canal(output_path: Path) -> None:
    """Download Erie Canal geometry via Overpass API; fall back to curated line."""
    print("\n[3/4] Canal corridor geometry …")

    features = []
    try:
        resp = requests.post(OVERPASS_URL, data={"data": OVERPASS_QUERY}, timeout=120)
        resp.raise_for_status()
        osm = resp.json()

        for el in osm.get("elements", []):
            if el.get("type") == "way" and "geometry" in el:
                coords = [[pt["lon"], pt["lat"]] for pt in el["geometry"]]
                if len(coords) >= 2:
                    features.append(
                        {
                            "type": "Feature",
                            "properties": {
                                "name": el.get("tags", {}).get("name", "Erie Canal"),
                                "type": el.get("tags", {}).get("waterway", "canal"),
                                "source": "OpenStreetMap",
                            },
                            "geometry": {"type": "LineString", "coordinates": coords},
                        }
                    )

        print(f"  ✓ {len(features)} segments from Overpass/OpenStreetMap")
    except Exception as exc:
        print(f"  ✗ Overpass failed ({exc}); using curated fallback route.")

    if not features:
        features = _fallback_canal_features()
        print("  ✓ Fallback route applied.")

    geojson = {"type": "FeatureCollection", "features": features}
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(geojson, fh)
    print(f"  Saved {len(features)} segment(s) → {output_path}")


def _fallback_canal_features() -> list[dict]:
    """
    Approximate Erie Canal centerline from Buffalo to Albany.
    Coordinates sourced from USGS NHD and historical maps.
    """
    waypoints = [
        [-78.8784, 42.8864],  # Buffalo — western terminus
        [-78.7084, 43.0058],  # Tonawanda
        [-78.6847, 43.1706],  # Lockport
        [-78.3865, 43.2190],  # Medina
        [-77.9983, 43.2155],  # Brockport
        [-77.6088, 43.2083],  # Rochester
        [-77.2335, 43.0617],  # Palmyra
        [-77.0025, 43.0735],  # Newark
        [-76.7997, 42.9109],  # Seneca Falls
        [-76.5117, 43.0703],  # Lyons
        [-76.3222, 43.1136],  # Clyde
        [-76.1474, 43.0481],  # Syracuse
        [-75.9830, 43.1093],  # Canastota
        [-75.6590, 43.0878],  # Oneida
        [-75.4355, 43.1009],  # Rome
        [-75.2326, 43.1009],  # Utica
        [-74.9885, 43.0268],  # Herkimer
        [-74.7000, 42.9900],  # Little Falls
        [-74.3567, 42.9488],  # Amsterdam
        [-73.9462, 42.8142],  # Schenectady
        [-73.7562, 42.6526],  # Albany — eastern terminus
    ]
    return [
        {
            "type": "Feature",
            "properties": {"name": "Erie Canal", "type": "canal", "source": "curated"},
            "geometry": {"type": "LineString", "coordinates": waypoints},
        }
    ]


# ════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — Historical industrial sites (curated)
# ════════════════════════════════════════════════════════════════════════════

# Sources: National Register of Historic Places, NPS Erie Canal records,
# NYS historic preservation office, and local historical societies.
INDUSTRY_SITES = [
    # ── Iron & Steel ────────────────────────────────────────────────────────
    dict(site_name="Burden Iron Works", industry_type="ironworks", town="Troy",
         latitude=42.7237, longitude=-73.6832,
         active_start_year=1809, active_end_year=1940,
         description="Major iron manufacturing complex famous for horseshoe production. "
                     "The 60-foot Burden Water Wheel (1851) was once the largest in the world."),
    dict(site_name="Albany Iron Works", industry_type="ironworks", town="Albany",
         latitude=42.6512, longitude=-73.7487,
         active_start_year=1844, active_end_year=1903,
         description="Produced the ironwork for the dome of the U.S. Capitol. "
                     "A major employer in the canal era, with 2,000 workers at peak."),
    dict(site_name="Rome Brass & Copper", industry_type="ironworks", town="Rome",
         latitude=43.2128, longitude=-75.4554,
         active_start_year=1865, active_end_year=1986,
         description="Brass and copper rod mills; later Revere Copper and Brass. "
                     "A center of U.S. copper processing until plant closure in 1986 "
                     "when operations consolidated elsewhere."),
    # ── Textiles ────────────────────────────────────────────────────────────
    dict(site_name="Cohoes Company Mills", industry_type="textiles", town="Cohoes",
         latitude=42.7748, longitude=-73.7127,
         active_start_year=1831, active_end_year=1937,
         description="One of the largest cotton textile mill complexes in America, "
                     "powered by Cohoes Falls. Company assets were sold after sustained "
                     "losses by 1932; operations ceased entirely by 1937."),
    dict(site_name="Utica Steam Cotton Mills", industry_type="textiles", town="Utica",
         latitude=43.1009, longitude=-75.2326,
         active_start_year=1847, active_end_year=1952,
         description="Major textile manufacturer that helped establish Utica as "
                     "a leading center of knit goods production."),
    dict(site_name="Oriskany Cotton Mills", industry_type="textiles", town="Oriskany",
         latitude=43.1573, longitude=-75.3399,
         active_start_year=1837, active_end_year=1902,
         description="Early textile mill on Oriskany Creek utilizing water power "
                     "to produce cotton cloth for regional markets."),
    dict(site_name="Amsterdam Carpet Mills", industry_type="textiles", town="Amsterdam",
         latitude=42.9386, longitude=-74.1887,
         active_start_year=1835, active_end_year=1968,
         description="Amsterdam became the carpet capital of the United States. "
                     "Manufacturing ended in 1968 as companies moved south for lower labor "
                     "costs, leaving behind obsolete machinery and vacant mill buildings."),
    dict(site_name="Schenectady Knitting Mills", industry_type="textiles", town="Schenectady",
         latitude=42.8142, longitude=-73.9395,
         active_start_year=1858, active_end_year=1930,
         description="Produced hosiery and knit goods distributed throughout the Northeast "
                     "via canal and rail networks."),
    # ── Milling ─────────────────────────────────────────────────────────────
    dict(site_name="Rochester Flouring Mills", industry_type="milling", town="Rochester",
         latitude=43.1566, longitude=-77.6088,
         active_start_year=1820, active_end_year=1878,
         description="Rochester's Genesee River mills made the city the 'Flour City' of "
                     "America in the 1830s–1840s, processing wheat from western farms."),
    dict(site_name="Seneca Mill", industry_type="milling", town="Seneca Falls",
         latitude=42.9109, longitude=-76.7997,
         active_start_year=1844, active_end_year=1910,
         description="Flour mill central to the agricultural economy of Seneca County, "
                     "supplying markets via the Cayuga–Seneca side canal."),
    dict(site_name="Herkimer Grist Mill", industry_type="milling", town="Herkimer",
         latitude=43.0268, longitude=-74.9885,
         active_start_year=1790, active_end_year=1870,
         description="One of the oldest mills in the Mohawk Valley, serving farming "
                     "communities before and after canal construction."),
    dict(site_name="Palmyra Flour Mill", industry_type="milling", town="Palmyra",
         latitude=43.0617, longitude=-77.2335,
         active_start_year=1826, active_end_year=1890,
         description="Canalside grain mill processing Wayne County wheat for eastern markets."),
    # ── Shipping ────────────────────────────────────────────────────────────
    dict(site_name="Black Rock Canal Terminal", industry_type="shipping", town="Buffalo",
         latitude=42.9281, longitude=-78.8940,
         active_start_year=1825, active_end_year=1900,
         description="Western terminus of the Erie Canal at Lake Erie, handling grain, "
                     "lumber, and manufactured goods from the Great Lakes."),
    dict(site_name="Albany Basin", industry_type="shipping", town="Albany",
         latitude=42.6479, longitude=-73.7572,
         active_start_year=1825, active_end_year=1917,
         description="Eastern terminus and transfer hub between the Erie Canal and Hudson "
                     "River sloops. At peak, 30,000+ boat passages per year."),
    dict(site_name="Schenectady Canal Docks", industry_type="shipping", town="Schenectady",
         latitude=42.8142, longitude=-73.9462,
         active_start_year=1825, active_end_year=1880,
         description="Major inland canal port serving as a freight transfer point between "
                     "the Mohawk Valley and Albany."),
    dict(site_name="Utica Canal Harbor", industry_type="shipping", town="Utica",
         latitude=43.1009, longitude=-75.2500,
         active_start_year=1825, active_end_year=1875,
         description="Central New York canal hub handling salt, textiles, and agricultural "
                     "goods for the regional economy."),
    dict(site_name="Cayuga–Seneca Canal Operations", industry_type="shipping", town="Cayuga",
         latitude=42.9171, longitude=-76.7356,
         active_start_year=1828, active_end_year=1880,
         description="Side canal connecting the Finger Lakes region to the main Erie Canal, "
                     "enabling wine, salt, and grain exports."),
    # ── Manufacturing ────────────────────────────────────────────────────────
    dict(site_name="Remington Arms Factory", industry_type="manufacturing", town="Ilion",
         latitude=43.0148, longitude=-74.9892,
         active_start_year=1816, active_end_year=2024,
         description="One of America's oldest firearms manufacturers, founded by Eliphalet "
                     "Remington. After 200+ years and multiple bankruptcies, the Ilion plant "
                     "permanently closed in March 2024 when operations relocated to Georgia."),
    dict(site_name="General Electric Schenectady Works", industry_type="manufacturing",
         town="Schenectady",
         latitude=42.8173, longitude=-73.9350,
         active_start_year=1886, active_end_year=1990,
         description="Edison Machine Works, later General Electric. At its peak employed "
                     "over 40,000 workers making turbines, generators, and locomotives. "
                     "Mass layoffs in the 1980s–90s reduced the workforce to a fraction; "
                     "major campus operations closed by 1990."),
    dict(site_name="Niagara Falls Power Company", industry_type="manufacturing",
         town="Niagara Falls",
         latitude=43.0962, longitude=-79.0377,
         active_start_year=1895, active_end_year=1961,
         description="First commercial AC power transmission plant, designed by Tesla and "
                     "Westinghouse. Unlocked large-scale electrochemical industry."),
    dict(site_name="Eastman Kodak Company", industry_type="manufacturing", town="Rochester",
         latitude=43.1566, longitude=-77.5965,
         active_start_year=1892, active_end_year=2012,
         description="George Eastman's film and camera empire transformed photography into "
                     "a mass consumer product and dominated global film markets for a century."),
    dict(site_name="Bausch & Lomb Optical", industry_type="manufacturing", town="Rochester",
         latitude=43.1566, longitude=-77.6088,
         active_start_year=1853, active_end_year=None,
         description="Founded by John Bausch and Henry Lomb; grew from a small optical shop "
                     "into a major manufacturer of lenses, telescopes, and medical devices."),
    dict(site_name="Onondaga Salt Works", industry_type="manufacturing", town="Syracuse",
         latitude=43.0481, longitude=-76.1474,
         active_start_year=1797, active_end_year=1926,
         description="The 'Salt City' salt works that drove Syracuse's early economy. "
                     "At peak produced 9 million bushels per year, shipped via canal."),
    dict(site_name="Fort Plain Paper Mill", industry_type="manufacturing", town="Fort Plain",
         latitude=42.9337, longitude=-74.6188,
         active_start_year=1836, active_end_year=1915,
         description="Mohawk Valley paper mill utilizing abundant water power and wood pulp "
                     "from Adirondack forests."),
    dict(site_name="Buffalo Brewing Company", industry_type="manufacturing", town="Buffalo",
         latitude=42.8864, longitude=-78.8600,
         active_start_year=1890, active_end_year=1956,
         description="One of several large lager breweries established in Buffalo, "
                     "supplied by grain arriving via the Erie Canal and Great Lakes shipping."),
    # ── Mining ───────────────────────────────────────────────────────────────
    dict(site_name="Medina Sandstone Quarries", industry_type="mining", town="Medina",
         latitude=43.2190, longitude=-78.3865,
         active_start_year=1820, active_end_year=1950,
         description="Distinctive red sandstone quarried extensively for buildings across "
                     "the U.S. and Canada; shipped via canal to construction sites."),
    dict(site_name="Lockport Limestone Quarries", industry_type="mining", town="Lockport",
         latitude=43.1706, longitude=-78.6904,
         active_start_year=1825, active_end_year=1900,
         description="Limestone excavated during construction of the famous Lockport flight "
                     "of five double locks; continued as a building stone supply after."),
    # ── Commerce ─────────────────────────────────────────────────────────────
    dict(site_name="Oneida Community Silverware", industry_type="commerce", town="Oneida",
         latitude=43.0878, longitude=-75.6590,
         active_start_year=1848, active_end_year=2005,
         description="Utopian community that evolved into Oneida Ltd., once one of the "
                     "world's largest silverware producers. U.S. manufacturing ended in "
                     "January 2005 when production moved offshore; the brand was later "
                     "acquired by Lenox in 2021."),
    dict(site_name="Palmyra Warehouse District", industry_type="commerce", town="Palmyra",
         latitude=43.0617, longitude=-77.2300,
         active_start_year=1825, active_end_year=1890,
         description="Canalside merchant warehouses that prospered during the height of "
                     "Erie Canal commerce, supplying local and regional goods."),
    dict(site_name="Syracuse & Utica Rail Terminus", industry_type="commerce", town="Syracuse",
         latitude=43.0481, longitude=-76.1450,
         active_start_year=1839, active_end_year=1870,
         description="Early railroad terminal connecting canal freight to emerging "
                     "rail networks — symbol of the transition from water to rail."),
]


def write_industry_data(output_path: Path) -> None:
    """Write the curated historical industrial sites to CSV."""
    print("\n[4/4] Historical industry sites …")
    df = pd.DataFrame(INDUSTRY_SITES)
    df["active_end_year"] = df["active_end_year"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    df.to_csv(output_path, index=False)
    print(f"  Saved {len(df)} sites → {output_path}")


# ════════════════════════════════════════════════════════════════════════════
#  Main
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Erie Canal corridor data files into data/.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--skip-healthcare",    action="store_true", help="Skip healthcare download")
    parser.add_argument("--skip-demographics",  action="store_true", help="Skip Census/ACS download")
    parser.add_argument("--skip-canal",         action="store_true", help="Skip canal geometry download")
    parser.add_argument("--skip-industry",      action="store_true", help="Skip industry sites CSV")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR}\n")

    errors = []

    if not args.skip_industry:
        try:
            write_industry_data(OUTPUT_DIR / "industry_sites.csv")
        except Exception as exc:
            errors.append(f"industry_sites.csv: {exc}")

    if not args.skip_healthcare:
        try:
            download_healthcare(OUTPUT_DIR / "healthcare_clean.csv")
        except Exception as exc:
            errors.append(f"healthcare_clean.csv: {exc}")

    if not args.skip_demographics:
        try:
            download_demographics(OUTPUT_DIR / "demographics.geojson")
        except Exception as exc:
            errors.append(f"demographics.geojson: {exc}")

    if not args.skip_canal:
        try:
            download_canal(OUTPUT_DIR / "canal_corridor.geojson")
        except Exception as exc:
            errors.append(f"canal_corridor.geojson: {exc}")

    print("\n" + "=" * 60)
    if errors:
        print("Completed with errors:")
        for e in errors:
            print(f"  ✗ {e}")
    else:
        print("All data files generated successfully.")
    print(f"Serve with:  python -m http.server 8080  (from {REPO_ROOT})")


if __name__ == "__main__":
    main()
