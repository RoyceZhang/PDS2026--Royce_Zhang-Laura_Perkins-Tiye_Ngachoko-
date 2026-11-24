"""
Download and clean BLS LAUS county unemployment data (annual averages).

BLS posts one Excel file per year with a fixed naming pattern:
    https://www.bls.gov/lau/laucnty{yy}.xlsx      (yy = 06, 07, ..., 15)
so the script loops over the years, downloads each file once into a raw folder
(never edited afterwards), and stacks them into one tidy table.

Output: laus_county_year.parquet -> one row per county x year
    fips | state_fips | county_fips | county_name | state | year |
    labor_force | employed | unemployed | unemployment_rate

Note: bls.gov rejects downloads that don't look like they come from a browser.
If you get HTTP 403, set an environment variable BLS_USER_AGENT to something like
"Mozilla/5.0 (Duke MIDS student project; your-email)" and run again, or download
the files by hand into the raw folder (the script uses files already there).

Usage:
  python clean_laus.py --raw-dir data/raw/laus --out-dir data/intermediate
"""

import argparse
import os
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

YEARS = range(2006, 2016)
URL_PATTERN = "https://www.bls.gov/lau/laucnty{yy}.xlsx"
DROP_STATES = {"AK"}
COLUMNS = ["laus_code", "state_fips", "county_fips", "county_state", "year",
           "labor_force", "employed", "unemployed", "unemployment_rate"]


def save(df, path: Path) -> None:
    try:
        df.to_parquet(path, index=False)
    except ImportError:
        path = path.with_suffix(".csv")
        df.to_csv(path, index=False)
    print(f"  wrote {path} ({len(df):,} rows)")


def download(year: int, raw_dir: Path) -> Path:
    url = URL_PATTERN.format(yy=f"{year % 100:02d}")
    dest = raw_dir / Path(url).name
    if dest.exists():  # already downloaded -> don't hit the site again
        return dest
    # bls.gov blocks requests that don't look like a full browser request
    headers = {
        "User-Agent": os.environ.get(
            "BLS_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.bls.gov/lau/tables.htm",
        "Connection": "keep-alive",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            dest.write_bytes(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(
            f"\nBLS refused the download of {url} (HTTP {e.code}).\n"
            "Fix options:\n"
            "  1. In a terminal, set BLS_USER_AGENT to a string with your email, e.g.\n"
            '     PowerShell:  $env:BLS_USER_AGENT = "Duke student project your.email@duke.edu"\n'
            "     then run the script again from that same terminal.\n"
            f"  2. Or open the link in your browser, save the file into\n"
            f"     {raw_dir.resolve()}\n"
            "     and re-run; files already there are not downloaded again."
        )
    print(f"  downloaded {url}")
    return dest


def read_one_year(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, header=None, dtype=str)
    # data rows start with a LAUS code like "CN0100100000000";
    # everything else is title rows and footnotes
    data = raw[raw[0].fillna("").str.strip().str.startswith("CN")]
    data = data.dropna(axis=1, how="all")  # BLS leaves an empty spacer column
    if data.shape[1] != len(COLUMNS):
        raise ValueError(f"{path.name}: expected {len(COLUMNS)} columns, got {data.shape[1]}")
    data.columns = COLUMNS

    df = data.copy()
    for c in ["labor_force", "employed", "unemployed", "unemployment_rate", "year"]:
        df[c] = pd.to_numeric(df[c].str.replace(",", "").str.strip(), errors="coerce")  # "(N.A.)" -> NaN
    df["state_fips"] = df["state_fips"].str.strip().str.zfill(2)
    df["county_fips"] = df["county_fips"].str.strip().str.zfill(3)
    df["fips"] = df["state_fips"] + df["county_fips"]
    # "Autauga County, AL" -> name + state ("District of Columbia" has a state code too)
    parts = df["county_state"].str.rsplit(",", n=1)
    df["county_name"] = parts.str[0].str.strip()
    df["state"] = parts.str[-1].str.strip()
    df["year"] = df["year"].astype("Int64")
    return df[["fips", "state_fips", "county_fips", "county_name", "state", "year",
               "labor_force", "employed", "unemployed", "unemployment_rate"]]


def main(raw_dir: Path, out_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    pieces = []
    for year in YEARS:  # loop over the formulaic links
        df = read_one_year(download(year, raw_dir))
        print(f"  {year}: {len(df):,} counties")
        pieces.append(df)

    laus = pd.concat(pieces, ignore_index=True)
    laus = laus[~laus["state"].isin(DROP_STATES)]
    laus = laus.drop_duplicates(["fips", "year"]).sort_values(["state", "fips", "year"])
    save(laus, out_dir / "laus_county_year.parquet")
    print(f"  missing unemployment_rate: {laus['unemployment_rate'].isna().mean():.1%}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", type=Path, default=Path("data/raw/laus"))
    ap.add_argument("--out-dir", type=Path, default=Path("data/intermediate"))
    args = ap.parse_args()
    main(args.raw_dir, args.out_dir)
