# Erie Canal Corridor — Healthcare & Industry Through Time

A single-page web application exploring the distribution of industry and
healthcare along the Erie Canal corridor (upstate New York) from 1820 to 2024.
Built with vanilla HTML/CSS/JS and Mapbox GL JS — no bundler, no build step.

---

## Quick start

### 1 · Install Python dependencies

```bash
pip install pandas geopandas requests
```

### 2 · Generate the data files

The `data/` folder is git-ignored. Generate it locally before opening the app:

```bash
python scripts/prepare_data.py
```

This produces four files in `data/`:

| File | Description | Source |
|------|-------------|--------|
| `industry_sites.csv` | 30 curated historical industrial sites | NPS / NRHP / local history |
| `healthcare_clean.csv` | NYS health facilities in corridor counties | [health.data.ny.gov](https://health.data.ny.gov/) |
| `demographics.geojson` | Census tract polygons + ACS attributes | [Census ACS 5-yr](https://www.census.gov/programs-surveys/acs) + TIGER |
| `canal_corridor.geojson` | Erie Canal centerline | OpenStreetMap / Overpass API |

#### Optional: Census API key

Demographic data is pulled from the U.S. Census Bureau API. A free key
improves reliability (unauthenticated requests are rate-limited).

1. Register at <https://api.census.gov/data/key_signup.html>
2. Export the key before running the script:

```bash
export CENSUS_API_KEY=your_key_here
python scripts/prepare_data.py
```

#### Selective generation

Skip any step with a flag:

```bash
python scripts/prepare_data.py --skip-demographics   # fastest; skips large TIGER download
python scripts/prepare_data.py --skip-healthcare      # skip Socrata API call
python scripts/prepare_data.py --skip-canal           # skip Overpass query
```

### 3 · Serve locally

Because `index.html` uses `fetch()` to load data files, you need a local
HTTP server (browsers block `file://` CORS):

```bash
# Python 3 (recommended)
python -m http.server 8080

# Node.js
npx serve .

# VS Code
# Install the "Live Server" extension and click "Go Live"
```

Then open **<http://localhost:8080>** in your browser.

---

## Deploy to GitHub Pages

1. Push the repository to GitHub (the `data/` folder is git-ignored and
   will **not** be included).
2. In **Settings → Pages**, set Source to the `main` branch, root directory.
3. GitHub will serve `index.html` at `https://<user>.github.io/<repo>`.

> **Note on data for live deployments:** The generated `data/` files are
> large (the demographics GeoJSON is typically 15–30 MB) and contain data
> aggregated from public sources.  To serve them from GitHub Pages, either:
>
> - Temporarily remove `data/` from `.gitignore`, commit the files, then
>   restore the ignore rule, **or**
> - Host the files on a separate CDN/bucket and update the `DATA_PATHS`
>   object at the top of `js/app.js`.

---

## Application features

### Industry Mode
- Historical industrial sites plotted as colored circles
- Color-coded by industry type (manufacturing, shipping, milling, textiles, etc.)
- **Hover** → tooltip showing site name, type, and active years
- **Click** → draggable panel with full details and historical description
- Legend in the lower-right corner

### Healthcare Mode
- NYS health facilities plotted as colored circles
- Color-coded by facility type (hospital, clinic, urgent care, etc.)
- Census tract **choropleth** underneath the facility layer, shaded by:
  - Median Age *(default)*
  - Median Household Income
  - Population Density
- Use the "Shade by" dropdown (upper-left) to switch choropleth field
- **Hover** → tooltip showing facility name, type, and county
- **Click** → draggable panel with facility details + census tract demographics
- Combined legend for facility types and choropleth color scale

### Timeline slider (always visible)
- Drag to select any year from **1820** to **2024**
- Industry mode: shows sites whose `active_start_year` ≤ selected year
- Healthcare mode: shows facilities whose `open_year` ≤ selected year
- Switching tabs resets the map view but preserves the selected year

### Canal corridor
- Subtle blue line always visible across both modes

---

## Project structure

```
erie-canal-map/
├── index.html              Main HTML entry point
├── css/
│   └── style.css           All styles (no preprocessor)
├── js/
│   └── app.js              All application logic (~350 lines, no framework)
├── scripts/
│   └── prepare_data.py     Data download and preparation
├── data/                   ← git-ignored; generate with prepare_data.py
│   ├── industry_sites.csv
│   ├── healthcare_clean.csv
│   ├── demographics.geojson
│   └── canal_corridor.geojson
├── .gitignore
└── README.md
```

---

## Data sources

| Dataset | License | Notes |
|---------|---------|-------|
| NYS Health Facility data | [NY Open Data ToS](https://data.ny.gov/download/77gx-ii52/application/pdf) | Socrata API |
| U.S. Census ACS 5-Year | Public domain | 2022 5-year estimates |
| TIGER/Line tract boundaries | Public domain | 2022 shapefiles |
| OpenStreetMap canal geometry | ODbL | Via Overpass API |
| Historical industrial sites | Curated — public historical record | NPS, NRHP, local histories |

---

## Mapbox

Access token and style are configured in `js/app.js` → `CONFIG`.  To use
your own token, replace the `token` value with one from
<https://account.mapbox.com>.
