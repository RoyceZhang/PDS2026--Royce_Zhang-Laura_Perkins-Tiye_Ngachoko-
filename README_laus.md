# BLS LAUS unemployment cleaning (`clean_laus.py`)

Downloads and cleans BLS county-level unemployment data (annual averages, 2006–2015) into one tidy table: one row per county per year.

## Requirements

- Python 3.10+
- Packages: `pandas`, `openpyxl` (reads Excel), `pyarrow` (writes parquet)

```bash
conda install -c conda-forge pandas openpyxl pyarrow
# or: pip install pandas openpyxl pyarrow
```

## How to run

Run from the repo root in a terminal (not the Code Runner button):

```bash
# bls.gov blocks anonymous scripts, so identify yourself with an email
export BLS_USER_AGENT="Duke student project your.email@duke.edu"   # bash / Git Bash
# $env:BLS_USER_AGENT = "Duke student project your.email@duke.edu" # PowerShell

python clean_laus.py
```

Optional arguments:

| Argument    | Default             | What it is                          |
|-------------|---------------------|-------------------------------------|
| `--raw-dir` | `data/raw/laus`     | Where the downloaded Excel files go |
| `--out-dir` | `data/intermediate` | Where the cleaned file is written   |

### If the download is blocked (HTTP 403)

Download the files by hand from your browser and save them into `data/raw/laus/`:

`https://www.bls.gov/lau/laucnty06.xlsx` … `https://www.bls.gov/lau/laucnty15.xlsx`

Then run `python clean_laus.py` again. Files already in the raw folder are never downloaded again.

## What it does

1. Loops over 2006–2015 and builds each download link from the year (`laucnty{yy}.xlsx`).
2. Saves the raw files unchanged in `data/raw/laus/`.
3. Keeps only county data rows (drops the title rows and footnotes).
4. Converts numbers ("23,987" → 23987). Missing values such as "(N.A.)" become NaN; no rows are dropped.
5. Builds a 5-digit `fips` code (state + county, leading zeros kept, e.g. `01001`).
6. Drops Alaska, as the assignment instructs.

## Output

`data/intermediate/laus_county_year.parquet`

| Column              | Description                              |
|---------------------|------------------------------------------|
| `fips`              | 5-digit county FIPS code (string)        |
| `state_fips`        | 2-digit state FIPS                       |
| `county_fips`       | 3-digit county FIPS                      |
| `county_name`       | e.g. "Autauga County"                    |
| `state`             | 2-letter abbreviation                    |
| `year`              | 2006–2015                                |
| `labor_force`       | Annual average labor force               |
| `employed`          | Annual average employed                  |
| `unemployed`        | Annual average unemployed                |
| `unemployment_rate` | Percent (e.g. 5.5 = 5.5%)                |

**Merging:** join to the other county-year files on `fips` + `year`. Keep `fips` as a string so the leading zeros aren't lost.

## Notes

- Keep `data/raw/` out of git (add it to `.gitignore`). Track the parquet output with git-lfs.
- If BLS ever changes the file layout, the script stops with "expected 9 columns". Check the header of the new file.
